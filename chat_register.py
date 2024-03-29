import argparse
import asyncio
import contextlib
import logging
import os
import socket
import sys
from contextlib import asynccontextmanager
from json import JSONDecodeError
from tkinter import Tk, Entry, Button, END, messagebox, Frame, Label

from aiofile import AIOFile

from core.chat_tool import get_open_connection_tools, SendingConnectionStateChanged, register
from core.gui import update_tk, TkAppClosed
from gui_chat import create_handy_nursery


class Registered(Exception):
    pass


def get_nickname(nickname_input, register_queue):
    nickname = nickname_input.get()
    register_queue.put_nowait(nickname)
    logging.debug(nickname)
    nickname_input.delete(0, END)


async def save_token(token, token_file_path):
    async with AIOFile(f'{token_file_path}', 'w') as token_file:
        await token_file.write(token)


@asynccontextmanager
async def register_process(reader, writer, register_queue, status_updates_queue):
    nickname = await register_queue.get()
    try:
        result = await register(reader, writer, nickname)
        yield result
    except JSONDecodeError:
        messagebox.showinfo(
            'Неудачная регистрация',
            'Неудачная регистрация. Попробуйте еще раз'
        )
        raise
    except (
            socket.gaierror,
            ConnectionRefusedError,
            ConnectionResetError,
            ConnectionError,
    ):
        yield
    finally:
        status_updates_queue.put_nowait(SendingConnectionStateChanged.CLOSED)


async def register_new_user(host, port, attempts, status_updates_queue, register_queue, token_file_path):
    while True:
        async with contextlib.AsyncExitStack() as stack:
            reader, writer = await stack.enter_async_context(
                get_open_connection_tools(host, port, attempts, status_updates_queue, SendingConnectionStateChanged)
            )
            result = await stack.enter_async_context(
                register_process(reader, writer, register_queue, status_updates_queue)
            )
            if not result:
                continue
            token = result.get('account_hash')
            registered_nickname = result.get('nickname')
            await save_token(token, token_file_path)
            messagebox.showinfo(
                "Успешная регистрация", f"Ваш ник: {registered_nickname}\n"
                f"Ваш токен сохранен в файле: {token_file_path}"
            )
            raise Registered


async def update_status(status_updates_queue, write_label):
    while True:
        msg = await status_updates_queue.get()
        write_label['text'] = f'Статус соединения с сервером: {msg}'


async def draw_register_window(register_queue, status_updates_queue):
    root = Tk()
    root.title = 'Регистрация в чате'
    root_frame = Frame(root)
    nickname_input = Entry(width=20)
    label = Label(bg="grey", width=20, height=1, text="Введите желаемый ник")
    register_button = Button(text="Зарегистрироваться", bd=2)
    register_button.bind('<Button-1>', lambda event: get_nickname(nickname_input, register_queue))

    status_read_label = Label(height=1, fg='grey', font='arial 10', anchor='w')
    status_read_label.pack(side="top")

    root_frame.pack()
    label.pack()
    nickname_input.pack()
    register_button.pack()
    status_read_label.pack()

    async with create_handy_nursery() as nursery:
        nursery.start_soon(update_tk(root_frame))
        nursery.start_soon(update_status(status_updates_queue, status_read_label))


def create_parser_for_user_arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument('--host', required=False,
                        help='chat host',
                        type=str)
    parser.add_argument('--port', required=False,
                        help='chat port for messages',
                        type=int)
    parser.add_argument('--attempts', required=False,
                        help='connect attempts before timeout',
                        type=str)
    parser.add_argument('--token_file_path', required=False,
                        help='file with token dir path',
                        type=str)
    namespace = parser.parse_args()
    return namespace


async def main():
    main_logger = logging.getLogger('')
    main_logger.setLevel(logging.DEBUG)
    user_arguments = create_parser_for_user_arguments()
    host = user_arguments.host or os.getenv('HOST', 'minechat.dvmn.org')
    port = user_arguments.port or os.getenv('SEND_PORT', 5050)
    attempts = int(user_arguments.attempts or os.getenv('ATTEMPTS_COUNT', 3))
    token_file_path = user_arguments.token_file_path
    if token_file_path and not os.path.exists(token_file_path):
        logging.error(f'token file path does not exist {token_file_path}')
        messagebox.showinfo(
            "Файл с токеном не найдем", f"Файл с токеном не найден по пути {token_file_path}"
        )
        sys.exit(2)
    elif not token_file_path:
        token_file_path = './token.txt'
    register_queue = asyncio.Queue()
    status_updates_queue = asyncio.Queue()

    async with create_handy_nursery() as nursery:
        nursery.start_soon(
            draw_register_window(register_queue, status_updates_queue)
        )
        nursery.start_soon(
            register_new_user(host, port, attempts, status_updates_queue, register_queue, token_file_path)
        )


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except (
            Registered,
            KeyboardInterrupt,
            TkAppClosed,
            JSONDecodeError
    ):
        exit()
