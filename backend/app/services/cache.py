"""Lightweight TTL cache for advisor list endpoints.

Keeps hot data in memory so F5 refreshes skip the DB entirely.
Cache is invalidated automatically on TTL expiry + explicitly on any
persona mutation (create/update/delete/publish/visibility/ingest).
"""

import time
import threading
from typing import Optional, Any, Callable, Awaitable


class TTLCache:
    """Simple dict-based TTL cache. Thread-safe via lock."""

    def __init__(self):
        self._store: dict[str, tuple[float, Any]] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            expires, value = entry
            if time.time() > expires:
                del self._store[key]
                return None
            return value

    def set(self, key: str, value: Any, ttl: float = 30.0):
        with self._lock:
            self._store[key] = (time.time() + ttl, value)

    def invalidate(self, prefix: str = ""):
        """Remove all keys starting with prefix. Empty prefix = clear all."""
        with self._lock:
            if prefix:
                keys = [k for k in self._store if k.startswith(prefix)]
            else:
                keys = list(self._store.keys())
            for k in keys:
                del self._store[k]

    def size(self) -> int:
        with self._lock:
            return len(self._store)


# Singleton
cache = TTLCache()


async def cached(key: str, ttl: float, factory: Callable[[], Awaitable[Any]]) -> Any:
    """Get from cache or compute via factory. Async."""
    value = cache.get(key)
    if value is not None:
        return value
    value = await factory()
    cache.set(key, value, ttl)
    return value
