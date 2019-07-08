import argparse
import asyncio
import contextlib
import logging.config
import os
import socket
import sys
from datetime import datetime
from tkinter import messagebox

import aionursery
from aiofile import AIOFile
from async_timeout import timeout

from core import gui
from core.chat_reader import read_stream_chat, save_messages
from core.chat_tool import (
    ReadConnectionStateChanged,
    SendingConnectionStateChanged,
    register,
    send_watchdog_messages,
    NicknameReceived,
    get_open_connection_tools
)
from core.chat_writer import InvalidToken, authorise, write_stream_chat


@contextlib.asynccontextmanager
async def create_handy_nursery():
    try:
        async with aionursery.Nursery() as nursery:
            yield nursery
    except aionursery.MultiError as e:
        if len(e.exceptions) == 1:
            raise e.exceptions[0]
        raise


async def read_connection(
        reader, messages_queue, history_queue, watchdog_queue, history_log_path
):
    async with contextlib.AsyncExitStack() as stack:
        nursery = await stack.enter_async_context(create_handy_nursery())
        nursery.start_soon(
            read_stream_chat(reader, messages_queue, history_queue, watchdog_queue))
        nursery.start_soon(
            save_messages(history_log_path, history_queue)
        )


async def send_connection(writer, reader, watchdog_queue, sending_queue):
    async with create_handy_nursery() as nursery:
        nursery.start_soon(
            write_stream_chat(writer, sending_queue, watchdog_queue)
        )
        nursery.start_soon(
            send_watchdog_messages(writer, reader, watchdog_queue)
        )


async def watch_for_connection(watchdog_queue):
    logger = logging.getLogger('watchdog_logger')
    while True:
        current_timestamp = datetime.now().timestamp()
        try:
            async with timeout(5):
                message = await watchdog_queue.get()
                logger.info(f'[{current_timestamp}] {message}')
            # because context manager doesn't work
        except asyncio.TimeoutError:
            logger.info(f'[{current_timestamp}] 5s timeout is elapsed')
            raise ConnectionError


async def handle_connection(host, read_port, send_port, messages_queue, history_queue, watchdog_queue, sending_queue,
                            status_updates_queue, token, attempts,
                            history_log_path):
    while True:
        async with contextlib.AsyncExitStack() as stack:

            status_updates_queue.put_nowait(SendingConnectionStateChanged.INITIATED)
            status_updates_queue.put_nowait(ReadConnectionStateChanged.INITIATED)

            (reader, _) = await stack.enter_async_context(get_open_connection_tools(
                host, read_port, attempts)
            )
            (write_reader, write_writer) = await stack.enter_async_context(get_open_connection_tools(
                host, send_port, attempts)
            )

            status_updates_queue.put_nowait(SendingConnectionStateChanged.ESTABLISHED)
            status_updates_queue.put_nowait(ReadConnectionStateChanged.ESTABLISHED)
            try:
                if token:
                    nickname = await authorise(write_reader, write_writer, token, watchdog_queue)
                    msg = f'Выполнена авторизация. Пользователь {nickname}.'
                    logging.debug(msg)
                else:
                    user_data = await register(write_reader, write_writer)
                    nickname = user_data.get('nickname')
                status_updates_queue.put_nowait(NicknameReceived(nickname))
                async with create_handy_nursery() as nursery:
                    nursery.start_soon(
                        read_connection(reader, messages_queue, history_queue, watchdog_queue, history_log_path)
                    )
                    nursery.start_soon(
                        send_connection(write_writer, write_reader, watchdog_queue, sending_queue)
                    )
                    nursery.start_soon(
                        watch_for_connection(watchdog_queue)
                    )
            except (
                    socket.gaierror,
                    ConnectionRefusedError,
                    ConnectionResetError,
                    ConnectionError,
            ):
                continue
            except InvalidToken:
                messagebox.showinfo("Неверный токен", "Проверьте токен, сервер не узнал его")
                raise
            break


def setup_loggers():
    main_logger = logging.getLogger('')
    main_logger.setLevel(logging.DEBUG)

    watchdog_logger = logging.getLogger('watchdog_logger')
    watchdog_logger.setLevel(logging.INFO)


def create_parser_for_user_arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument('--host', required=False,
                        help='chat host',
                        type=str)
    parser.add_argument('--read_port', required=False,
                        help='chat port for reading messages',
                        type=int)
    parser.add_argument('--send_port', required=False,
                        help='chat port for sending messages',
                        type=int)
    parser.add_argument('--history', required=False,
                        help='history log dir path',
                        type=str)
    parser.add_argument('--attempts', required=False,
                        help='connect attempts before timeout',
                        type=str)
    parser.add_argument('--token', required=False,
                        help='user token',
                        type=str)
    parser.add_argument('--token_file_path', required=False,
                        help='file with token path',
                        type=str)
    namespace = parser.parse_args()
    return namespace


async def get_token_from_file(token_file_path=None):
    if not token_file_path:
        token_file_path = './token.txt'
        if not os.path.exists(token_file_path):
            return
    async with AIOFile(token_file_path) as token_file:
        token = await token_file.read()
        return token


async def main():
    setup_loggers()
    user_arguments = create_parser_for_user_arguments()
    history_log_path = user_arguments.history or os.getenv('HISTORY_LOG_DIR_PATH', f'{os.getcwd()}')

    if not os.path.exists(history_log_path):
        logging.error(f'history log path does not exist {history_log_path}')
        sys.exit(2)

    token_file_path = user_arguments.token_file_path or os.getenv('TOKEN_FILE_PATH')
    if user_arguments.token_file_path and not os.path.exists(user_arguments.token_file_path):
        logging.error(f'token file path does not exist {user_arguments.token_file_path}')
        sys.exit(2)
    elif user_arguments.token_file_path:
        token_file_path = user_arguments.token_file_path

    token_from_file = await get_token_from_file(token_file_path)
    host = user_arguments.host or os.getenv('HOST', 'minechat.dvmn.org')
    read_port = user_arguments.read_port or os.getenv('READ_PORT', 5000)
    send_port = user_arguments.send_port or os.getenv('SEND_PORT', 5050)
    attempts = int(user_arguments.attempts or os.getenv('ATTEMPTS_COUNT', 3))
    token = user_arguments.token or os.getenv('TOKEN') or token_from_file
    messages_queue = asyncio.Queue()
    sending_queue = asyncio.Queue()
    status_updates_queue = asyncio.Queue()
    history_queue = asyncio.Queue()
    watchdog_queue = asyncio.Queue()
    if os.path.exists(f'{history_log_path}/history_logs.txt'):
        with open(f'{history_log_path}/history_logs.txt') as log_file:
            messages_queue.put_nowait(log_file.read())

    async with create_handy_nursery() as nursery:
        nursery.start_soon(
            gui.draw(messages_queue, sending_queue, status_updates_queue)
        )

        nursery.start_soon(
            handle_connection(host, read_port, send_port, messages_queue, history_queue,
                              watchdog_queue, sending_queue,
                              status_updates_queue,
                              token, attempts, history_log_path)
        )


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except (
            KeyboardInterrupt,
            gui.TkAppClosed,
            InvalidToken,
            ConnectionError
    ):
        exit()
