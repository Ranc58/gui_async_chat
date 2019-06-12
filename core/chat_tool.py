import contextlib
import json
from enum import Enum

import asyncio

from datetime import datetime
import logging
import socket
from contextlib import asynccontextmanager

from async_timeout import timeout




class ReadConnectionStateChanged(Enum):
    INITIATED = 'устанавливаем соединение'
    ESTABLISHED = 'соединение установлено'
    CLOSED = 'соединение закрыто'

    def __str__(self):
        return str(self.value)


class SendingConnectionStateChanged(Enum):
    INITIATED = 'устанавливаем соединение'
    ESTABLISHED = 'соединение установлено'
    CLOSED = 'соединение закрыто'

    def __str__(self):
        return str(self.value)


class NicknameReceived:
    def __init__(self, nickname):
        self.nickname = nickname


@asynccontextmanager
async def get_open_connection_tools(host, port, attempts, status_updates_queue, connection_state):
    try:
        reader, writer = await get_open_connection(host, port, attempts, status_updates_queue, connection_state)
        yield reader, writer
    finally:
        writer.close()


async def register(reader, writer, nickname=None):
    await read_message_from_chat(reader)
    await write_message_to_chat(writer)
    await read_message_from_chat(reader)
    message = None
    if nickname:
        message = f'{nickname}\n'
    await write_message_to_chat(writer, message)
    decoded_data = await read_message_from_chat(reader)
    return json.loads(decoded_data)


async def read_message_from_chat(reader):
    response = await reader.readline()
    decoded_data = response.decode().rstrip('\n\r')
    logging.debug(decoded_data)
    return decoded_data


async def write_message_to_chat(writer, message=None):
    if not message:
        message = '\n'
    message = f'{message}'
    writer.write(message.encode())
    await writer.drain()


async def get_open_connection(host, port, attempts, status_updates_queue, connection_state):
    attempts_count = 0
    reader = None
    writer = None
    while not reader:
        try:
            status_updates_queue.put_nowait(connection_state.INITIATED)
            reader, writer = await asyncio.open_connection(host, port)
            success_connect_msg = 'Соединение установлено'
            logging.debug(success_connect_msg)
            status_updates_queue.put_nowait(connection_state.ESTABLISHED)
        except (
                socket.gaierror,
                ConnectionRefusedError,
                ConnectionResetError,
                ConnectionError,
        ):
            status_updates_queue.put_nowait(connection_state.INITIATED)
            if attempts_count < int(attempts):
                error_msg = 'Нет соединения. Повторная попытка.'
                logging.debug(error_msg)
                attempts_count += 1
                continue
            else:
                error_msg = 'Нет соединения. Повторная попытка через 3 сек.'
                logging.debug(error_msg)
                await asyncio.sleep(3)
                continue
    return reader, writer


async def watch_for_input_connection(input_connections_queue, status_updates_queue):
    logger = logging.getLogger('watchdog_logger')
    while True:
        current_timestamp = datetime.now().timestamp()
        try:
            async with timeout(5):
                message = await input_connections_queue.get()
                logger.info(f'[{current_timestamp}] {message}')
            # because context manager doesn't work
        except asyncio.TimeoutError:
            logger.info(f'[{current_timestamp}] 5s timeout is elapsed')
            status_updates_queue.put_nowait(ReadConnectionStateChanged.CLOSED)
            raise ConnectionError


async def watch_for_output_connection(writer, reader, status_updates_queue):
    while True:
        try:
            writer.write(f'\n'.encode())
            await writer.drain()
            async with timeout(5):
                await reader.readline()
            # because context manager doesn't work
        except asyncio.TimeoutError:
            status_updates_queue.put_nowait(SendingConnectionStateChanged.CLOSED)
            raise ConnectionError
