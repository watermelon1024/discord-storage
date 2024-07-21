import asyncio
import io
import os
import uuid

import discord
from fastapi import UploadFile

from . import utils
from .cache import cache
from .database import Database


class Bot(discord.Client):
    DEFAULT_MAX_SIZE: int = 25 * 1024 * 1024  # 25 MB
    __init_task = None

    async def initialize(self):
        channel_id = int(os.getenv("CHANNEL"))
        self.channel = self.get_channel(channel_id) or await self.fetch_channel(channel_id)

        self.attachments_cache: dict[str, tuple[asyncio.Task[bytes]]] = {}
        self.db = Database(os.getenv("DB_PATH") or "storage/database.db")
        await self.db.initialize()

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

    async def get_file(self, id: str, filename: str):
        """
        Gets a file from the database.

        :return: Real filename, size and file combine generator.
        :rtype: tuple[str, int, AsyncGenerator[bytes]]
        """
        real_filename, legalized_filename, size, message_ids = await self.check_file(id, filename)
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

        if self.attachments_cache.get(id) is None:
            self.attachments_cache[id] = [asyncio.create_task(a.read()) for a in attachments]

        async def combine():
            for task in self.attachments_cache[id]:
                yield await task

        return real_filename, size, combine()

    async def _split_file(self, data: UploadFile, max_size: int = DEFAULT_MAX_SIZE):
        """
        Splits a file into chunks of a maximum size.

        :return: The index of the chunk and the chunk data.
        :rtype: AsyncGenerator[int, bytes]
        """
        idx = 0
        sizes = 0
        chunks = b""
        while True:
            chunk = await data.read(max_size)
            if not chunk:
                yield idx, chunks
                break
            size = len(chunk)
            if size + sizes > max_size:
                yield idx, chunks
                idx += 1
                sizes = 0
                chunks = b""

            sizes += size
            chunks += chunk

    async def _upload_chunk(self, id: str, idx: int, data: bytes):
        max_retry = 10
        for retry in range(max_retry + 1):
            try:
                return idx, await self.channel.send(file=discord.File(io.BytesIO(data), id))
            except Exception:
                if retry == max_retry:
                    raise
        raise Exception("Failed to upload file")

    async def upload_file(self, data: UploadFile, name: str, size: int = None) -> tuple[str, str]:
        """
        Uploads a file to the channel.

        :returns: The file ID and the legalized filename
        :rtype: tuple[str, str]
        """
        id = str(uuid.uuid4())

        tasks: list[asyncio.Task[tuple[int, discord.Message]]] = []
        async for idx, d in self._split_file(data):
            tasks.append(asyncio.create_task(self._upload_chunk(id, idx, d)))
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
