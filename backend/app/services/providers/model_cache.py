"""In-memory TTL cache for upstream `models.list()` calls.

24h default TTL — model catalogs change rarely and listing them on every
page load is wasteful. Per-key asyncio lock prevents a thundering herd when
the cache is cold and multiple requests arrive at once.
"""

from __future__ import annotations

import time
from asyncio import Lock
from collections.abc import Awaitable, Callable
from typing import Any

DEFAULT_TTL_SECONDS = 24 * 60 * 60  # 24 hours

_entries: dict[str, tuple[float, Any]] = {}
_locks: dict[str, Lock] = {}


async def cached(
    key: str,
    loader: Callable[[], Awaitable[Any]],
    *,
    ttl: int = DEFAULT_TTL_SECONDS,
) -> tuple[Any, bool]:
    """Return `(value, hit)` for `key`, loading via `loader()` on miss or expiry.

    `hit=True` when the returned value came from a live cache entry (same
    process lifetime, within TTL). `hit=False` after a cold-load.
    """
    now = time.time()
    hit = _entries.get(key)
    if hit is not None and now - hit[0] < ttl:
        return hit[1], True

    lock = _locks.setdefault(key, Lock())
    async with lock:
        # Re-check under lock — another coroutine may have populated it.
        now = time.time()
        hit = _entries.get(key)
        if hit is not None and now - hit[0] < ttl:
            return hit[1], True
        value = await loader()
        _entries[key] = (now, value)
        return value, False


def invalidate(key: str | None = None) -> None:
    """Drop a single key, or all keys when `key` is None. Used by tests."""
    if key is None:
        _entries.clear()
    else:
        _entries.pop(key, None)
