import asyncio
import io
import os

import discord

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

    async def get_file(self, id: str, file_name: str):
        """
        Gets a file from the database.
        """
        file_name, size, message_ids = await self.db.get_file(id, file_name)
        try:
            attachments = [await self._get_attachment(id) for id in message_ids]
        except discord.NotFound as e:
            await self.delete_file(message_ids[0])
            for id in message_ids:
                try:
                    await (await self.get_or_fetch_message(id)).delete()
                except Exception:
                    pass
            raise e

        return (
            file_name,
            size,
            (
                (await self._get_attachment(message_ids[0])).url
                if len(attachments) == 1
                else self._combine_file(attachments)
            ),
        )

    def _split_file(self, data: io.BytesIO, max_size: int = DEFAULT_MAX_SIZE):
        data.seek(0)
        while True:
            chunk = data.read(max_size)
            if not chunk:
                break
            yield chunk

    async def upload_file(self, data: io.BytesIO, file_name: str) -> str:
        """
        Uploads a file to the channel and returns the ID of the message.
        """
        size = data.getbuffer().nbytes
        message_ids = [
            (
                await self.channel.send(
                    file=discord.File(io.BytesIO(d), f"{file_name}{f'.part{idx}' if idx else ''}")
                )
            ).id.__str__()
            for idx, d in enumerate(self._split_file(data))
        ]
        await self.db.add_file(message_ids[0], file_name, size, message_ids)
        return message_ids[0]

    async def delete_file(self, id: str):
        """
        Deletes a file from the database.
        """
        await self.db.delete_file(id)
