import asyncio
import json
import logging
import socket
from contextlib import asynccontextmanager
from enum import Enum

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
async def get_open_connection_tools(host, port, attempts):
    try:
        reader, writer = await get_open_connection(host, port, attempts)
        yield reader, writer
    finally:
        writer.close()


async def register(reader, writer, nickname=None):
    await read_message_from_chat(reader)
    await write_message_to_chat(writer)
    await read_message_from_chat(reader)
    await write_message_to_chat(writer, nickname)
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
    else:
        message = message.replace('\n', '').strip()
        message = f'{message}\n'
    message = f'{message}'
    writer.write(message.encode())
    await writer.drain()


async def get_open_connection(host, port, attempts):
    attempts_count = 0
    reader = None
    writer = None
    while not reader:
        try:
            reader, writer = await asyncio.open_connection(host, port)
        except (
                socket.gaierror,
                ConnectionRefusedError,
                ConnectionResetError,
                ConnectionError,
        ):

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
        else:
            success_connect_msg = 'Соединение установлено'
            logging.debug(success_connect_msg)
    return reader, writer


async def send_watchdog_messages(writer, reader, watchdog_queue):
    while True:
        try:
            writer.write(f'\n'.encode())
            await writer.drain()
            async with timeout(5):
                await reader.readline()
            watchdog_queue.put_nowait('Send connection is alive')
            await asyncio.sleep(3)
            # because context manager doesn't work
        except asyncio.TimeoutError:
            continue
