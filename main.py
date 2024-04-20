import telebot
from config import *
from ya_gpt import ask_gpt
from database import *
from vallidators import *
from SpeechKit import *
import logging

bot = telebot.TeleBot(bot_token)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    filename="log_file.txt",
    filemode="w",
)
u_data = {}
@bot.message_handler(commands=['start'])
def start(message):
    u_id = message.chat.id
    if len(u_data) >= MAX_USERS:
        bot.send_message(u_id, 'Достигнут лимит пользователей')
    else:
        if u_id not in u_data:
            u_data[u_id] = {
                'question' :  '',
                'answer' : ''
            }
    bot.send_message(u_id, 'Привет, я твой бот помощник испольщующий ИИ'
                                      ' для поддержания диалога, нахождения ответов на твои '
                                      'вопросы, а также для решение задач которые ты мне кидаешь')

@bot.message_handler(commands=['help'])
def help(message):
    bot.send_message(message.from_user.id, "Чтобы приступить к общению, отправь мне голосовое сообщение или текст")

# обрабатываем команду /debug - отправляем файл с логами
@bot.message_handler(commands=['debug'])
def debug(message):
    with open("logs.txt", "rb") as f:
        bot.send_document(message.chat.id, f)


@bot.message_handler(content_types=['voice'])
def handle_voice(message: telebot.types.Message):
    user_id = message.from_user.id
    try:
        # Проверка на максимальное количество пользователей
        status_check_users, error_message = check_number_of_users(user_id)
        logging.info(f"error_message - {error_message}")
        if not status_check_users:
            bot.send_message(user_id, f"Ошибка - {error_message}")
            bot.register_next_step_handler(handle_voice)

        # Проверка на доступность аудиоблоков
        stt_blocks, error_message = is_stt_block_limit(user_id, message.voice.duration)
        logging.info(f"stt blocks - {stt_blocks}")
        logging.info(f"error_message - {error_message}")
        if error_message:
            bot.send_message(user_id, f"Ошибка - {error_message}. Либо что то пошло не так, либо ты записал[а] пустое "
                                   "аудио сообщение.. Попробуй ещё раз пожалуйста")
            logging.info(f'error_message - {error_message}')
            return

        # Обработка голосового сообщения
        file_id = message.voice.file_id
        file_info = bot.get_file(file_id)
        file = bot.download_file(file_info.file_path)
        status_stt, stt_text = speech_to_text(file)
        logging.info(f"file_id - {file_id}, file_info - {file_info}, status_stt - {status_stt}, stt_text - {stt_text}")
        if not status_stt:
            bot.send_message(user_id, stt_text)
            return

        # Запись в БД
        add_message(user_id=user_id, full_message=[stt_text, 'user', 0, 0, stt_blocks])

        # Проверка на доступность GPT-токенов
        last_messages, total_spent_tokens = select_n_last_messages(user_id, COUNT_LAST_MSG)
        total_gpt_tokens, error_message = is_gpt_token_limit(last_messages, total_spent_tokens)
        if error_message:
            bot.send_message(user_id, error_message)
            return

        # Запрос к GPT и обработка ответа
        status_gpt, answer_gpt, tokens_in_answer = ask_gpt(last_messages)
        if not status_gpt:
            bot.send_message(user_id, answer_gpt)
            return
        total_gpt_tokens += tokens_in_answer

        # Проверка на лимит символов для SpeechKit
        tts_symbols, error_message = is_tts_symbol_limit(user_id, answer_gpt)

        # Запись ответа GPT в БД
        add_message(user_id=user_id, full_message=[answer_gpt, 'assistant', total_gpt_tokens, tts_symbols, 0])

        if error_message:
            bot.send_message(user_id, error_message)
            return

        # Преобразование ответа в аудио и отправка
        status_tts, voice_response = text_to_speech(answer_gpt)
        if status_tts:
            bot.send_voice(user_id, voice_response, reply_to_message_id=message.id)
        else:
            bot.send_message(user_id, answer_gpt, reply_to_message_id=message.id)

    except Exception as e:
        logging.error(e)
        bot.send_message(user_id, "Не получилось ответить. Попробуй записать другое сообщение")

@bot.message_handler(content_types=['text'])
def handle_text(message):
    try:
        user_id = message.from_user.id

        # ВАЛИДАЦИЯ: проверяем, есть ли место для ещё одного пользователя (если пользователь новый)
        status_check_users, error_message = check_number_of_users(user_id)
        if not status_check_users:
            bot.send_message(user_id, error_message)  # мест нет =(
            return

        # БД: добавляем сообщение пользователя и его роль в базу данных
        full_user_message = [message.text, 'user', 0, 0, 0]
        add_message(user_id=user_id, full_message=full_user_message)

        # ВАЛИДАЦИЯ: считаем количество доступных пользователю GPT-токенов
        # получаем последние 4 (COUNT_LAST_MSG) сообщения и количество уже потраченных токенов
        last_messages, total_spent_tokens = select_n_last_messages(user_id, COUNT_LAST_MSG)
        # получаем сумму уже потраченных токенов + токенов в новом сообщении и оставшиеся лимиты пользователя
        total_gpt_tokens, error_message = is_gpt_token_limit(last_messages, total_spent_tokens)
        if error_message:
            # если что-то пошло не так — уведомляем пользователя и прекращаем выполнение функции
            bot.send_message(user_id, error_message)
            return

        # GPT: отправляем запрос к GPT
        status_gpt, answer_gpt, tokens_in_answer = ask_gpt(last_messages)
        # GPT: обрабатываем ответ от GPT
        if not status_gpt:
            # если что-то пошло не так — уведомляем пользователя и прекращаем выполнение функции
            bot.send_message(user_id, answer_gpt)
            return
        # сумма всех потраченных токенов + токены в ответе GPT
        total_gpt_tokens += tokens_in_answer

        # БД: добавляем ответ GPT и потраченные токены в базу данных
        full_gpt_message = [answer_gpt, 'assistant', total_gpt_tokens, 0, 0]
        add_message(user_id=user_id, full_message=full_gpt_message)

        bot.send_message(user_id, answer_gpt, reply_to_message_id=message.id)  # отвечаем пользователю текстом
    except Exception as e:
        logging.error(e)  # если ошибка — записываем её в логи
        bot.send_message(message.from_user.id, "Не получилось ответить. Попробуй написать другое сообщение")

# обрабатываем все остальные типы сообщений
@bot.message_handler(func=lambda: True)
def handler(message):
    bot.send_message(message.from_user.id, "Отправь мне голосовое или текстовое сообщение, и я тебе отвечу")

if __name__ == "__main__":
    logging.info("Бот запущен")
    create_database()
    logging.info("База данных создана")
    bot.infinity_polling()