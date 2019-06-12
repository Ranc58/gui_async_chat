import json
import logging

from tkinter import messagebox

from core.chat_tool import read_message_from_chat, write_message_to_chat


class InvalidToken(Exception):
    pass


async def submit_message(writer, message):
    await write_message_to_chat(writer, f'{message}\n\n')


async def send_msgs(queue, writer, watchdog_queue):
    message = await queue.get()
    await submit_message(writer, message)
    logging.debug(message)
    watchdog_queue.put_nowait('Message sent')


async def authorise(reader, writer, token, watchdog_queue):
    await read_message_from_chat(reader)
    await write_message_to_chat(writer, f'{token}\n')
    watchdog_queue.put_nowait('Prompt before auth')
    decoded_data = await read_message_from_chat(reader)
    json_data = json.loads(decoded_data)
    if not json_data:
        messagebox.showinfo("Неверный токен", "Проверьте токен, сервер не узнал его")
        raise InvalidToken()
    nickname = json_data.get("nickname")
    msg = f'Выполнена авторизация. Пользователь {nickname}.'
    logging.debug(msg)
    return nickname


async def write_stream_chat(writer, sending_queue, status_updates_queue):
    while True:
        await send_msgs(sending_queue, writer, status_updates_queue)




