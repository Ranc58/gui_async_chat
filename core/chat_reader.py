from aiofile import AIOFile

from core.chat_tool import read_message_from_chat


async def save_messages(history_log_path, queue):
    async with AIOFile(f'{history_log_path}/history_logs.txt', 'a+') as log_file:
        while True:
            message = await queue.get()
            await log_file.write(f'{message}\n')


async def read_stream_chat(reader, messages_queue, history_queue, watchdog_queue):
    while True:
        decoded_data = await read_message_from_chat(reader)
        messages_queue.put_nowait(decoded_data)
        history_queue.put_nowait(decoded_data)
        watchdog_queue.put_nowait('Read connection is alive. New message in chat')
