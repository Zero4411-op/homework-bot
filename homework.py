import logging
import os
import sys
import time
from http import HTTPStatus

import requests
import telebot
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

handler = logging.StreamHandler(sys.stdout)
formatter = logging.Formatter(
    '%(asctime)s [%(levelname)s] %(message)s'
)
handler.setFormatter(formatter)
logger.addHandler(handler)

PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

RETRY_PERIOD = 600
RETRY_PERIOD_SECONDS = RETRY_PERIOD
ENDPOINT = ('https://practicum.yandex.ru/'
            'api/user_api/homework_statuses/')
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}

HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}


class HomeworkAPIError(Exception):
    """Кастомное исключение для ошибок API Яндекс.Практикума."""


class SendMessageError(Exception):
    """Кастомное исключение для ошибок отправки сообщений."""


def check_tokens():
    """Проверяет наличие всех необходимых токенов."""
    tokens = (
        ('PRACTICUM_TOKEN', PRACTICUM_TOKEN),
        ('TELEGRAM_TOKEN', TELEGRAM_TOKEN),
        ('TELEGRAM_CHAT_ID', TELEGRAM_CHAT_ID)
    )

    for name, token in tokens:
        if not token:
            logger.critical(f'Отсутствует {name}')
            return False
    return True


def send_message(bot, message):
    """Отправляет сообщение в Telegram."""
    try:
        bot.send_message(TELEGRAM_CHAT_ID, message)
    except Exception as error:
        raise SendMessageError(f'Ошибка отправки в Telegram: {error}')

    logger.debug(f'Отправлено сообщение в Telegram: {message}')
    return True


def get_api_answer(timestamp):
    """Делает запрос к API Яндекс.Практикума."""
    params = {'from_date': timestamp}

    try:
        response = requests.get(
            ENDPOINT,
            headers=HEADERS,
            params=params
        )
    except requests.RequestException as error:
        raise HomeworkAPIError(f'Ошибка при запросе к API: {error}')

    if response.status_code != HTTPStatus.OK:
        raise HomeworkAPIError(
            f'Эндпоинт {ENDPOINT} недоступен. '
            f'Код ответа: {response.status_code}.'
        )

    try:
        return response.json()
    except ValueError as error:
        raise HomeworkAPIError(f'Ошибка парсинга JSON: {error}')


def check_response(response):
    """Проверяет структуру ответа API."""
    if not isinstance(response, dict):
        raise TypeError(
            f'Ответ не словарь, получен тип: {type(response).__name__}'
        )

    if 'homeworks' not in response:
        raise KeyError('В ответе API отсутствует ключ "homeworks"')

    homeworks = response['homeworks']

    if not isinstance(homeworks, list):
        raise TypeError(
            f'homeworks не список, получен тип: {type(homeworks).__name__}'
        )

    if 'current_date' not in response:
        raise KeyError('В ответе API отсутствует ключ "current_date"')

    return homeworks


def parse_status(homework):
    """Извлекает статус домашней работы."""
    if 'homework_name' not in homework:
        raise KeyError('В ответе API отсутствует ключ "homework_name"')

    if 'status' not in homework:
        raise KeyError('В ответе API отсутствует ключ "status"')

    homework_name = homework['homework_name']
    status = homework['status']

    if status not in HOMEWORK_VERDICTS:
        raise ValueError(f'Неизвестный статус работы: {status}')

    verdict = HOMEWORK_VERDICTS[status]

    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def process_status_update(homeworks, bot, last_status, response):
    """Обрабатывает обновление статуса домашней работы."""
    if not homeworks:
        logger.debug('Нет новых статусов')
        return last_status, None

    homework = homeworks[0]
    message = parse_status(homework)

    if message != last_status:
        if send_message(bot, message):
            return message, response.get('current_date')

    return last_status, None


def handle_errors(error, bot, last_error):
    """Обрабатывает ошибки в основном цикле."""
    error_message = f'Сбой в работе программы: {error}'
    logger.error(error_message)

    if error_message != last_error:
        try:
            send_message(bot, error_message)
            return error_message
        except SendMessageError:
            return last_error

    return last_error


def main():
    """Основная логика работы бота."""
    if not check_tokens():
        sys.exit(1)

    bot = telebot.TeleBot(token=TELEGRAM_TOKEN)
    timestamp = int(time.time())
    last_error = ''
    last_homework_status = ''

    while True:
        try:
            api_response = get_api_answer(timestamp)
            homeworks = check_response(api_response)

            new_status, new_timestamp = process_status_update(
                homeworks, bot, last_homework_status, api_response
            )
            last_homework_status = new_status
            if new_timestamp:
                timestamp = new_timestamp

            last_error = ''

        except SendMessageError as error:
            logger.error(f'Ошибка отправки сообщения в Telegram: {error}')

        except Exception as error:
            last_error = handle_errors(error, bot, last_error)

        finally:
            time.sleep(RETRY_PERIOD_SECONDS)


if __name__ == '__main__':
    main()
