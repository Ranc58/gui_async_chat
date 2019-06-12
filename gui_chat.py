import argparse
import asyncio
import contextlib
import logging.config
import os
import socket
import sys

import aionursery
from aiofile import AIOFile

import gui
from chat_reader import read_stream_chat
from chat_tool import ReadConnectionStateChanged, SendingConnectionStateChanged, \
    watch_for_output_connection, NicknameReceived, watch_for_input_connection, get_open_connection_tools
from chat_writer import InvalidToken, write_stream_chat, authorise


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
        host, port, attempts, status_updates_queue, messages_queue, history_queue, watchdog_queue, history_log_path):
    reader = None
    while not reader:
        async with get_open_connection_tools(host, port, attempts, status_updates_queue, ReadConnectionStateChanged) as (reader, writer):
            try:
                async with create_handy_nursery() as nursery:
                    nursery.start_soon(
                        read_stream_chat(reader, messages_queue, history_queue, watchdog_queue, history_log_path))
                    nursery.start_soon(watch_for_input_connection(watchdog_queue, status_updates_queue))

            except (
                    socket.gaierror,
                    ConnectionRefusedError,
                    ConnectionResetError,
                    ConnectionError,
            ):
                reader = None
                status_updates_queue.put_nowait(ReadConnectionStateChanged.INITIATED)


async def send_connection(host, port, attempts, status_updates_queue, sending_queue, watchdog_queue, token):
    reader = None
    while not reader:
        async with get_open_connection_tools(host, port, attempts, status_updates_queue,
                                             SendingConnectionStateChanged) as (reader, writer):
            try:
                nickname = await authorise(reader, writer, token, watchdog_queue)
                watchdog_queue.put_nowait('Authorization done')
                status_updates_queue.put_nowait(NicknameReceived(nickname))
                async with create_handy_nursery() as nursery:
                    nursery.start_soon(
                        write_stream_chat(writer, sending_queue, status_updates_queue))
                    nursery.start_soon(watch_for_output_connection(writer, reader, status_updates_queue))
            except (
                    socket.gaierror,
                    ConnectionRefusedError,
                    ConnectionResetError,
                    ConnectionError,
            ):
                reader = None
                status_updates_queue.put_nowait(SendingConnectionStateChanged.INITIATED)


async def handle_connection(host, read_port, send_port, messages_queue, history_queue, watchdog_queue, sending_queue,
                            status_updates_queue, token, attempts,
                            history_log_path):
    async with create_handy_nursery() as nursery:
        nursery.start_soon(
            read_connection(host, read_port, attempts, status_updates_queue, messages_queue, history_queue, watchdog_queue, history_log_path)
        )
        nursery.start_soon(
            send_connection(host, send_port, attempts, status_updates_queue, sending_queue, watchdog_queue, token)
        )


def setup_loggers(main_log=None, watchdog_log=None):
    if main_log:
        main_logger = logging.getLogger('')
        main_logger.setLevel(logging.DEBUG)
    if watchdog_log:
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


async def get_token_from_file():
    async with AIOFile('token.txt') as token_file:
        token = await token_file.read()
        return token


async def main():
    # todo refactor! add write port
    setup_loggers(watchdog_log=True, main_log=True)  # todo  chbange true and false
    user_arguments = create_parser_for_user_arguments()
    history_log_path = user_arguments.history or os.getenv('HISTORY_LOG_DIR_PATH', f'{os.getcwd()}')
    if not os.path.exists(history_log_path):
        logging.error(f'history log path does not exist {history_log_path}')
        sys.exit(2)
    if user_arguments.token_file_path and not os.path.exists(user_arguments.token_file_path):
        logging.error(f'token file path does not exist {user_arguments.token_file_path}')
        sys.exit(2)
    else:
        token_from_file = await get_token_from_file()
    host = user_arguments.host or os.getenv('HOST', 'minechat.dvmn.org')
    read_port = user_arguments.read_port or os.getenv('READ_PORT', 5000)
    send_port = user_arguments.send_port or os.getenv('SEND_PORT', 5050)  # TODO  ADD TO ENV
    attempts = int(user_arguments.attempts or os.getenv('ATTEMPTS_COUNT', 3))
    token = user_arguments.token or os.getenv('TOKEN') or token_from_file  # todo del token!

    messages_queue = asyncio.Queue()
    sending_queue = asyncio.Queue()
    status_updates_queue = asyncio.Queue()
    history_queue = asyncio.Queue()
    watchdog_queue = asyncio.Queue()

    with open(f'{history_log_path}/history_logs.txt') as log_file:
        messages_queue.put_nowait(log_file.read())

    async with create_handy_nursery() as nursery:
        nursery.start_soon(
            gui.draw(messages_queue, sending_queue, status_updates_queue)
        )

        nursery.start_soon(handle_connection(host, read_port, send_port, messages_queue, history_queue,
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
