import asyncio
import io
import os
import typing
import uuid

import discord

from . import utils
from .cache import SQLiteCache
from .database import Database


class Bot(discord.Client):
    DEFAULT_MAX_SIZE: int = 25 * 1024 * 1024  # 25 MB
    __init_task = None

    async def initialize(self):
        channel_id = int(os.getenv("CHANNEL"))
        self.channel = self.get_channel(channel_id) or await self.fetch_channel(channel_id)

        self.attachments_cache: dict[str, list[tuple[asyncio.Task[bytes], asyncio.Event]]] = {}
        self.db = Database(os.getenv("DB_PATH") or "storage/database.db")
        await self.db.initialize()
        self.file_cache = SQLiteCache(os.getenv("CACHE_PATH") or ".cache/cache.db")
        await self.file_cache.initialize()

        print(f"Logged in as {self.user} (ID: {self.user.id})")

    async def wait_until_ready(self):
        await super().wait_until_ready()
        if self.__init_task is None:
            self.__init_task = asyncio.create_task(self.initialize())
        return await self.__init_task

    async def run(self, token: str):
        asyncio.create_task(self.start(token))
        await self.wait_until_ready()

    async def get_or_fetch_message(self, message_id: int) -> discord.Message:
        return self.get_message(message_id) or await self.channel.fetch_message(message_id)

    async def _get_attachment(self, message_id: int):
        return (await self.get_or_fetch_message(message_id)).attachments[0]

    async def _first_combine(
        self, id: str, size: int, tasks: list[tuple[asyncio.Task[bytes], asyncio.Event]]
    ):
        await self.file_cache.set(id, b"", size)
        for task, event in tasks:
            data = await task
            event.set()
            await self.file_cache.append_at_end(id, data)

        self.attachments_cache.pop(id, None)

    async def _combine(self, tasks: list[tuple[asyncio.Task[bytes], asyncio.Event]]):
        for task, event in tasks:
            await event.wait()
            yield task.result()

    async def check_file(self, id: str, filename: str = None):
        """
        Checks if the file exists.

        :param id: The file ID
        :type id: str
        :param filename: The filename to check.
        If filled, it will check if the filename matches the filename in database, or ignore filename check.
        :type filename: Optional[str]

        :return: Real filename, legalized filename, size, and message IDs
        :rtype: tuple[str, str, int, list[str]]

        :raises FileNotFoundError: If the file is not found.
        """
        real_filename, legalized_filename, size, message_ids = await self.db.get_file(id)
        if filename is not None and legalized_filename != filename:
            raise FileNotFoundError(f"File '{filename}' not found.")
        return real_filename, legalized_filename, size, message_ids

    async def get_file(self, id: str, filename: str, start: int = 0, interval: int = None):
        """
        Gets a file from the database.

        :param id: The file ID
        :type id: str
        :param filename: The filename to get.
        :type filename: str
        :param start: The start index of the file chunk.
        :type start: int
        :param interval: The number of bytes to get.
        :type interval: int

        :return: Real filename, size and file combine generator.
        :rtype: tuple[str, str, AsyncGenerator[bytes]]
        """
        # get file info
        real_filename, legalized_filename, size, message_ids = await self.check_file(id, filename)

        # check cache
        data = await self.file_cache.get(id, start, interval)
        if data is not None:

            async def combine(data: bytes):
                yield data

            return real_filename, str(len(data)), combine(data)

        # get from cloud
        try:
            attachments = [await self._get_attachment(mid) for mid in message_ids]
        except discord.NotFound as e:
            await self.delete_file(id)
            for mid in message_ids:
                try:
                    await (await self.get_or_fetch_message(mid)).delete()
                except Exception:
                    pass
            raise e

        tasks = self.attachments_cache.get(id)
        if tasks is None:
            self.attachments_cache[id] = tasks = [
                (self.loop.create_task(attachment.read()), asyncio.Event()) for attachment in attachments
            ]
            self.loop.create_task(self._first_combine(id, size, tasks))

        return real_filename, size, self._combine(tasks)

    async def get_generator(
        self, stream: typing.AsyncGenerator[bytes, None], max_size: int = DEFAULT_MAX_SIZE
    ):
        size = 0
        data = b""
        async for chunk in stream:
            chunk_size = len(chunk)
            if chunk_size + size > max_size:
                yield data
                size = 0
                data = b""

            size += chunk_size
            data += chunk
        yield data

    async def _upload_chunk(self, id: str, idx: int, data: bytes):
        max_retry = 10
        for retry in range(max_retry + 1):
            try:
                return idx, await self.channel.send(file=discord.File(io.BytesIO(data), id))
            except Exception:
                if retry == max_retry:
                    raise
        raise Exception("Failed to upload file")

    async def upload_file(
        self, data: typing.AsyncGenerator[bytes, None], name: str, size: int = None
    ) -> tuple[str, str]:
        """
        Uploads a file to the channel.

        :returns: The file ID and the legalized filename
        :rtype: tuple[str, str]
        """
        id = str(uuid.uuid4())

        tasks: list[asyncio.Task[tuple[int, discord.Message]]] = []
        idx = 0
        async for d in self.get_generator(data):
            tasks.append(asyncio.create_task(self._upload_chunk(id, idx, d)))
            idx += 1
        done, pending = await asyncio.wait(tasks)
        messages = [r[1] for r in sorted((t.result() for t in done), key=lambda x: x[0])]
        if not size:
            size = sum(m.attachments[0].size for m in messages)
        legalized_name = utils.legalize_filename(name)
        await self.db.add_file(id, name, legalized_name, size, [str(m.id) for m in messages])
        return id, legalized_name

    async def delete_file(self, id: str):
        """
        Deletes a file from the database.
        """
        await self.db.delete_file(id)
