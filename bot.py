import asyncio
import io
import os
import uuid

import discord

import utils
from cache import cache
from database import Database


class Bot(discord.Client):
    DEFAULT_MAX_SIZE: int = 25 * 1024 * 1024  # 25 MB
    __init_task = None

    async def initialize(self):
        channel_id = int(os.getenv("CHANNEL"))
        self.channel = self.get_channel(channel_id) or await self.fetch_channel(channel_id)

        db_path = os.getenv("DB_PATH") or "storage/database.db"
        self.db = Database(db_path)
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

    @cache
    async def _read_attachment(self, attachment: discord.Attachment):
        return await attachment.read()

    async def _combine_file(self, attachments: list[discord.Attachment]):
        """
        Combine the file from the attachments.
        """
        for attachment in attachments:
            yield await self._read_attachment(attachment)

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

        return real_filename, size, self._combine_file(attachments)

    def _split_file(self, data: io.BytesIO, max_size: int = DEFAULT_MAX_SIZE):
        data.seek(0)
        while True:
            chunk = data.read(max_size)
            if not chunk:
                break
            yield chunk

    async def _upload_chunk(self, id: str, data: bytes):
        max_retry = 10
        for retry in range(max_retry + 1):
            try:
                return await self.channel.send(file=discord.File(io.BytesIO(data), id))
            except Exception:
                if retry == max_retry:
                    raise
        raise Exception("Failed to upload file")

    async def upload_file(self, data: io.BytesIO, name: str, size: int = None) -> tuple[str, str]:
        """
        Uploads a file to the channel.

        :returns: The file ID and the legalized filename
        :rtype: tuple[str, str]
        """
        if not size:
            data.seek(0)
            size = len(data.read())
        id = str(uuid.uuid4())
        messages = await asyncio.gather(*(self._upload_chunk(id, d) for d in self._split_file(data)))
        legalized_name = utils.legalize_filename(name)
        await self.db.add_file(id, name, legalized_name, size, [str(m.id) for m in messages])
        return id, legalized_name

    async def delete_file(self, id: str):
        """
        Deletes a file from the database.
        """
        await self.db.delete_file(id)
