import logging
import os
import sys
import time

import requests
import telebot
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)

logger = logging.getLogger(__name__)

PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

RETRY_PERIOD = 600
ENDPOINT = ('https://practicum.yandex.ru/'
            'api/user_api/homework_statuses/')
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}

HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}


def check_tokens():
    """Проверяет наличие всех необходимых токенов."""
    if not PRACTICUM_TOKEN:
        logger.critical('Отсутствует PRACTICUM_TOKEN')
        return False
    if not TELEGRAM_TOKEN:
        logger.critical('Отсутствует TELEGRAM_TOKEN')
        return False
    if not TELEGRAM_CHAT_ID:
        logger.critical('Отсутствует TELEGRAM_CHAT_ID')
        return False
    return True


def send_message(bot, message):
    """Отправляет сообщение в Telegram."""
    try:
        bot.send_message(TELEGRAM_CHAT_ID, message)
        logger.debug(f'Отправлено: {message}')
        return True
    except Exception as error:
        logger.error(f'Ошибка отправки в Telegram: {error}')
        return False


def get_api_answer(timestamp):
    """Делает запрос к API Яндекс.Практикума."""
    try:
        response = requests.get(
            ENDPOINT,
            headers=HEADERS,
            params={'from_date': timestamp}
        )
        if response.status_code != 200:
            logger.error(f'Код ответа: {response.status_code}')
            raise Exception(f'Код ответа: {response.status_code}')
        return response.json()
    except requests.RequestException as error:
        logger.error(f'Ошибка запроса: {error}')
        return {'homeworks': [], 'current_date': timestamp}
    except Exception as error:
        logger.error(f'Неожиданная ошибка: {error}')
        raise


def check_response(response):
    """Проверяет структуру ответа API."""
    if not isinstance(response, dict):
        logger.error('Ответ не словарь')
        raise TypeError('Ответ не словарь')
    if 'homeworks' not in response:
        logger.error('Нет ключа homeworks')
        raise KeyError('Нет ключа homeworks')
    if not isinstance(response['homeworks'], list):
        logger.error('homeworks не список')
        raise TypeError('homeworks не список')
    if 'current_date' not in response:
        logger.error('Нет ключа current_date')
        raise KeyError('Нет ключа current_date')
    return response['homeworks']


def parse_status(homework):
    """Извлекает статус домашней работы."""
    if 'homework_name' not in homework:
        logger.error('Нет ключа homework_name')
        raise KeyError('Нет ключа homework_name')
    if 'status' not in homework:
        logger.error('Нет ключа status')
        raise KeyError('Нет ключа status')

    homework_name = homework['homework_name']
    status = homework['status']

    if status not in HOMEWORK_VERDICTS:
        logger.error(f'Неизвестный статус: {status}')
        raise ValueError(f'Неизвестный статус: {status}')

    verdict = HOMEWORK_VERDICTS[status]

    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


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
            response = get_api_answer(timestamp)
            homeworks = check_response(response)

            if homeworks:
                homework = homeworks[0]
                message = parse_status(homework)

                if message != last_homework_status:
                    if send_message(bot, message):
                        last_homework_status = message
                        timestamp = response.get('current_date', timestamp)
            else:
                logger.debug('Нет новых статусов')

            last_error = ''

        except Exception as error:
            error_message = f'Сбой в работе программы: {error}'
            logger.error(error_message)

            if error_message != last_error:
                if send_message(bot, error_message):
                    last_error = error_message

        time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    main()
