from pathlib import Path

import aiosqlite


class Database:
    """
    The database class of the bot.
    """

    def __init__(self, path: str) -> None:
        self.path = path

    async def initialize(self) -> None:
        """
        Initializes the database.
        """
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self.path) as db:
            # create file mapping
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS file (
                    id TEXT PRIMARY KEY,
                    name TEXT,
                    legalized_name TEXT,
                    size TEXT,
                    message_ids TEXT
                )
                """
            )

    async def add_file(
        self, id: str, name: str, legalized_name: str, size: int | str, message_ids: list[str]
    ) -> None:
        """
        Adds a file to the database.
        """
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                """
                INSERT INTO file (id, name, legalized_name, size, message_ids)
                VALUES (?, ?, ?, ?, ?)
                """,
                (id, name, legalized_name, size, ",".join(message_ids)),
            )
            await db.commit()

    async def get_file(self, id: str) -> tuple[str, str, str, list[str]]:
        """
        Gets a file from the database.

        :return: The name, legalized name, and message IDs of the file.
        :rtype: tuple[str, str, str, list[str]]
        """
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM file WHERE id = ?",
                (id,),
            ) as cursor:
                data = await cursor.fetchone()
                if data is None:
                    raise FileNotFoundError(f"File '{id}' not found.")
                return data["name"], data["legalized_name"], data["size"], data["message_ids"].split(",")

    async def delete_file(self, id: str) -> None:
        """
        Deletes a file from the database.
        """
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "DELETE FROM file WHERE id = ?",
                (id,),
            )
            await db.commit()
