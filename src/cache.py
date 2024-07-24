import asyncio
import os
import re
import time
from pathlib import Path

import aiosqlite


def convert_to_bytes(size_str: str) -> float:
    size_str = size_str.strip().upper()
    match = re.match(r"^(\d+(?:\.\d+)?)\s*([KMGT]?B)$", size_str)
    if match:
        units = {"B": 1, "KB": 1024, "MB": 1024**2, "GB": 1024**3, "TB": 1024**4}
        num, unit = match.groups()
        return float(num) * units[unit]
    else:
        raise ValueError(f"Invalid size format '{size_str}'. Please use the format like '50MB', '1GB', etc.")


def convert_to_seconds(time_str: str) -> float:
    time_str = time_str.strip().lower()
    match = re.match(r"^(\d+(?:\.\d+)?)\s*([smhd])$", time_str)
    if match:
        units = {"s": 1, "m": 60, "h": 60 * 60, "d": 24 * 60 * 60}
        num, unit = match.groups()
        return float(num) * units[unit]
    else:
        raise ValueError(f"Invalid time format '{time_str}'. Please use the format like '2h', '1d', etc.")


CACHE_MAX_SIZE: float = convert_to_bytes(os.getenv("CACHE_MAX_SIZE") or "512MB")
CACHE_TTL: float = convert_to_seconds(os.getenv("CACHE_TTL") or "24h")


class SQLiteCache:
    def __init__(self, path=".cache/cache.db", max_size=CACHE_MAX_SIZE, default_ttl=CACHE_TTL):
        self.path = path
        self.max_size = max_size
        self.default_ttl = default_ttl

    async def initialize(self):
        """
        Initialize the database and create the cache table if it doesn't exist
        """
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS cache (
                    key TEXT PRIMARY KEY,
                    value BLOB,
                    size TEXT,
                    expiration_time INTEGER,
                    last_access_time INTEGER
                )
                """
            )

    def _get_db_size(self):
        return os.path.getsize(self.path)

    async def _evict_if_needed(self):
        """
        Evict the least recently used items from the cache if the cache size exceeds the maximum size
        """
        current_size = self._get_db_size()
        if current_size < self.max_size:
            return
        async with aiosqlite.connect(self.path) as db:
            current_time = int(time.time())
            await db.execute("DELETE FROM cache WHERE expiration_time < ?", (current_time,))

            db.row_factory = aiosqlite.Row
            async with db.execute(
                """
                SELECT key, size FROM cache
                ORDER BY last_access_time ASC
                LIMIT 10
                """
            ) as cursor:
                rows = await cursor.fetchall()
            to_delete = []
            for row in rows:
                to_delete.append(row["key"])
                current_size -= int(row["size"])
                if current_size < self.max_size:
                    break
            await db.execute(
                f"""
                DELETE FROM cache
                WHERE key IN ({", ".join(f"'{s}'" for s in to_delete)})
                """
            )
            await db.execute("VACUME")
            await db.commit()

    # async def _delete_expired(self):
    #     async with aiosqlite.connect(self.path) as db:
    #         current_time = int(time.time())
    #         await db.execute("DELETE FROM cache WHERE expiration_time < ?", (current_time,))
    #         await db.execute("VACUME cache")
    #         await db.commit()

    async def set(self, key: str, value: bytes, ttl=None):
        """
        Set a key-value pair in the cache with an optional time-to-live (TTL)
        """
        if ttl is None:
            ttl = self.default_ttl
        current_time = int(time.time())
        expiration_time = current_time + ttl
        last_access_time = current_time
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                """
                INSERT OR REPLACE INTO cache (key, value, size, expiration_time, last_access_time)
                VALUES (?, ?, ?, ?, ?)
                """,
                (key, value, len(value), expiration_time, last_access_time),
            )
            await db.commit()
        asyncio.create_task(self._evict_if_needed())

    async def get(self, key: str, start: int = 0, interval: int = None) -> bytes:
        """
        Get the value associated with the given key from the cache

        :param key: The key to retrieve
        :type key: str
        :param start: The start index of the value to retrieve (optional)
        :type start: int
        :param interval: The number of bytes to retrieve (optional)
        :type interval: int

        :return: The value associated with the key, or None if the key is not found
        :rtype: bytes or None
        """
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            if start and not interval:
                value = f"substr(value, {start}, LENGTH(value) - {start}) as value"
            elif start and interval:
                value = f"substr(value, {start}, {interval}) as value"
            else:
                value = "value"
            async with db.execute(f"SELECT {value} FROM cache WHERE key = ?", (key,)) as cursor:
                row = await cursor.fetchone()
                if row:
                    value = row["value"]
                else:
                    value = None
        asyncio.create_task(self._evict_if_needed())
        return value

    async def delete(self, key: str):
        """
        Delete the key-value pair from the cache
        """
        async with aiosqlite.connect(self.path) as db:
            await db.execute("DELETE FROM cache WHERE key = ?", (key,))
            await db.commit()

    async def clear(self):
        """
        Clear the entire cache
        """
        async with aiosqlite.connect(self.path) as db:
            await db.execute("DELETE FROM cache")
            await db.commit()
