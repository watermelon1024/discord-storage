import os
import re

from asyncache import cached
from cachetools import TLRUCache


def convert_to_bytes(size_str: str) -> float:
    size_str = size_str.strip().upper()
    match = re.match(r"^(\d+(?:\.\d+)?)\s*([KMGT]?B)$", size_str)
    if match:
        units = {"B": 1, "KB": 1024, "MB": 1024**2, "GB": 1024**3}
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


def _get_size(size: bytes):
    return len(size)


def ttu(_key, _value, now):
    return now + CACHE_TTL


cache = cached(TLRUCache(maxsize=CACHE_MAX_SIZE, ttu=ttu, getsizeof=_get_size))
