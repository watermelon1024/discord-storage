from asyncache import cached
from cachetools import TLRUCache

CACHE_MAX_SIZE: int = 512 * 1024 * 1024  # 512 MB
CACHE_TTL: int = 24 * 60 * 60  # 24 hour


def _get_size(size: bytes):
    return len(size)


def ttu(_key, _value, now):
    return now + CACHE_TTL


cache = cached(TLRUCache(maxsize=CACHE_MAX_SIZE, ttu=ttu, getsizeof=_get_size))
