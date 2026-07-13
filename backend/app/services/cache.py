"""Lightweight TTL cache for advisor list endpoints.

Keeps hot data in memory so F5 refreshes skip the DB entirely.
Cache is invalidated automatically on TTL expiry + explicitly on any
persona mutation (create/update/delete/publish/visibility/ingest).
"""

import time
import threading
from typing import Optional, Any, Callable, Awaitable

from app.core.logging import get_logger

log = get_logger("cache")


class TTLCache:
    """Simple dict-based TTL cache. Thread-safe via lock."""

    def __init__(self):
        self._store: dict[str, tuple[float, Any]] = {}
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0

    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                self._misses += 1
                log.info(f"CACHE MISS key={key} (misses={self._misses} hits={self._hits})")
                return None
            expires, value = entry
            if time.time() > expires:
                del self._store[key]
                self._misses += 1
                log.info(f"CACHE EXPIRED key={key} (misses={self._misses} hits={self._hits})")
                return None
            self._hits += 1
            age_ms = (time.time() - (expires - 30)) * 1000 if expires > time.time() else 0
            log.info(f"CACHE HIT key={key} age={age_ms:.0f}ms (hits={self._hits} misses={self._misses})")
            return value

    def set(self, key: str, value: Any, ttl: float = 30.0):
        with self._lock:
            self._store[key] = (time.time() + ttl, value)
            log.info(f"CACHE SET key={key} ttl={ttl}s entries={len(self._store)}")

    def invalidate(self, prefix: str = ""):
        """Remove all keys starting with prefix. Empty prefix = clear all."""
        with self._lock:
            if prefix:
                keys = [k for k in self._store if k.startswith(prefix)]
            else:
                keys = list(self._store.keys())
            for k in keys:
                del self._store[k]
            if keys:
                log.info(f"CACHE INVALIDATE prefix={prefix!r} removed={len(keys)} remaining={len(self._store)}")

    def stats(self) -> dict:
        with self._lock:
            return {"hits": self._hits, "misses": self._misses, "entries": len(self._store)}


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
