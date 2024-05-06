import logging
from config import MAX_USERS, MAX_USER_GPT_TOKENS, MAX_USER_STT_BLOCKS, MAX_USER_TTS_SYMBOLS, MAX_TTS_SYMBOLS
from database import *
from ya_gpt import count_gpt_tokens
import math

logging.basicConfig(filename=LOGS, level=logging.ERROR, format="%(asctime)s FILE: %(filename)s IN: %(funcName)s MESSAGE: %(message)s", filemode="w")

def check_number_of_users(user_id):
    count = count_users(user_id)
    if count is None:
        return None, "Ошибка при работе с БД"
    if count > MAX_USERS:
        return None, "Превышено максимальное количество пользователей"
    return True, ""

def is_gpt_token_limit(messages, total_spent_tokens):
    all_tokens = count_gpt_tokens(messages) + total_spent_tokens
    if all_tokens > MAX_USER_GPT_TOKENS:
        return None, f"Превышен общий лимит GPT-токенов {MAX_USER_GPT_TOKENS}"
    return all_tokens, ""

# проверяем, не превысил ли пользователь лимиты на преобразование аудио в текст
def is_stt_block_limit(message, duration):
    user_id = message.from_user.id
    audio_blocks = math.ceil(duration / 15)

    all_blocks = count_all_limits(user_id, limit_type= 'stt_blocks')

    if all_blocks is None:
        all_blocks = 0

    all_blocks += audio_blocks

    if duration >= 30:
        msg = "SpeechKit STT работает с голосовыми сообщениями меньше 30 секунд"
        return msg

    if all_blocks >= MAX_USER_STT_BLOCKS:
        msg = f"Превышен общий лимит SpeechKit STT {MAX_USER_STT_BLOCKS}. Использовано {all_blocks} блоков. Доступно: {MAX_USER_STT_BLOCKS - all_blocks}"
        return msg

    return audio_blocks

# проверяем, не превысил ли пользователь лимиты на преобразование текста в аудио
def is_tts_symbol_limit(message, text):
    user_id = message.from_user.id
    text_symbols = len(text)

    all_symbols = count_all_symbol(user_id) + text_symbols

    if all_symbols >= MAX_USER_TTS_SYMBOLS:
        msg = f"Превышен общий лимит SpeechKit TTS {MAX_USER_TTS_SYMBOLS}. Использовано: {all_symbols} символов. Доступно: {MAX_USER_TTS_SYMBOLS - all_symbols}"
        return msg

    if text_symbols >= MAX_TTS_SYMBOLS:
        msg = f"Превышен лимит SpeechKit TTS на запрос {MAX_TTS_SYMBOLS}, в сообщении {text_symbols} символов"
        return msg
    return len(text)