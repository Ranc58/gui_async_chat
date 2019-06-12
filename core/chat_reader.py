from aiofile import AIOFile

from core.chat_tool import read_message_from_chat


async def save_messages(log_file, queue):
    message = queue.get_nowait()
    await log_file.write(f'{message}\n')


async def read_stream_chat(reader, messages_queue, history_queue, watchdog_queue, history_log_path):
    async with AIOFile(f'{history_log_path}/history_logs.txt', 'a+') as log_file:
        while True:
            decoded_data = await read_message_from_chat(reader)
            messages_queue.put_nowait(decoded_data)
            history_queue.put_nowait(decoded_data)
            watchdog_queue.put_nowait('Connection is alive. New message in chat')
            await save_messages(log_file, history_queue)



