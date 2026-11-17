"""Rotating pool of provider API keys.

A single Gemini key can fail for reasons the key itself can't fix:
regional capacity hitting 503, per-key minute quota hitting 429, or the
whole key getting revoked and returning 401. With a pool of 2+ keys we
switch to the next one instead of surfacing the error to the user.

Rotation rules:
- 5xx / 429 → the current key is likely fine, just unlucky; rotate forward
  and retry. Key stays alive in the pool.
- 401 / 403 → the key itself is bad (revoked, wrong project, no quota).
  Kill it for the process lifetime and rotate.
- Pool exhausted (every key dead or every key just failed on this request)
  → caller re-raises the last error.

State is per-process: a dead key stays dead until restart. That's fine for
the demo — if the operator rotates a key they'll redeploy anyway.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Awaitable, Callable, Iterable
from typing import Any

log = logging.getLogger(__name__)


class KeyPoolExhausted(RuntimeError):
    """Raised when every key has been killed (auth) for this process."""


class KeyPool:
    def __init__(self, keys: Iterable[str], *, label: str) -> None:
        cleaned = [k.strip() for k in keys if k and k.strip()]
        self._keys: list[str] = cleaned
        self._dead: set[int] = set()
        self._cursor: int = 0
        self._lock = threading.Lock()
        self._label = label

    def __len__(self) -> int:
        return len(self._keys)

    @property
    def alive_count(self) -> int:
        return len(self._keys) - len(self._dead)

    def current(self) -> str:
        with self._lock:
            if not self._keys:
                raise KeyPoolExhausted(f"{self._label} key pool is empty.")
            if self._cursor in self._dead:
                self._advance_locked()
            return self._keys[self._cursor]

    def rotate(self) -> str:
        """Move to the next live key. Returns the new current key."""
        with self._lock:
            self._advance_locked()
            log.info(
                "%s key pool rotated to index %d (alive=%d/%d)",
                self._label, self._cursor, self.alive_count, len(self._keys),
            )
            return self._keys[self._cursor]

    def kill_current(self) -> None:
        """Mark the current key as permanently dead (auth failure)."""
        with self._lock:
            if self._cursor < len(self._keys):
                self._dead.add(self._cursor)
                log.warning(
                    "%s key at index %d killed (auth failure); %d alive remaining",
                    self._label, self._cursor, self.alive_count,
                )
            if self.alive_count == 0:
                raise KeyPoolExhausted(
                    f"All {self._label} keys failed authentication."
                )
            self._advance_locked()

    def _advance_locked(self) -> None:
        if not self._keys:
            raise KeyPoolExhausted(f"{self._label} key pool is empty.")
        if self.alive_count == 0:
            raise KeyPoolExhausted(f"All {self._label} keys are dead.")
        n = len(self._keys)
        for _ in range(n):
            self._cursor = (self._cursor + 1) % n
            if self._cursor not in self._dead:
                return
        raise KeyPoolExhausted(f"All {self._label} keys are dead.")


_POOL_ROTATE_CODES = (429, 500, 502, 503, 504)
_POOL_KILL_CODES = (401, 403)


async def with_pool_rotation(
    pool: "KeyPool",
    rebuild_client: Callable[[], None],
    attempt: Callable[[], Awaitable[Any]],
    *,
    provider_name: str,
) -> Any:
    """Run `attempt()`; on retriable / auth failure, rotate the pool, rebuild
    the SDK client, and try again. Raises the last ProviderError once every
    live key has been tried on this request.
    """
    # Lazy import to avoid a cycle (base imports nothing from here).
    from app.services.providers.base import ProviderError
    from app.services.providers.errors import translate

    tried = 0
    max_tries = max(1, pool.alive_count)
    last_error: ProviderError | None = None

    while tried < max_tries:
        tried += 1
        try:
            return await attempt()
        except ProviderError as pe:
            last_error = pe
            if pe.http_status in _POOL_KILL_CODES:
                try:
                    pool.kill_current()
                except KeyPoolExhausted:
                    raise pe
                rebuild_client()
                # The killed attempt doesn't count against the fresh key we
                # just rotated to — give the remaining pool a clean budget.
                tried = 0
                max_tries = max(1, pool.alive_count)
                continue
            if pe.http_status in _POOL_ROTATE_CODES and pool.alive_count > 1 and tried < max_tries:
                log.info(
                    "%s: status %d, rotating to next key (try %d/%d)",
                    provider_name, pe.http_status, tried + 1, max_tries,
                )
                pool.rotate()
                rebuild_client()
                continue
            raise
        except Exception as err:
            translated = translate(provider_name, err)
            last_error = translated
            if translated.http_status in _POOL_KILL_CODES:
                try:
                    pool.kill_current()
                except KeyPoolExhausted:
                    raise translated from err
                rebuild_client()
                tried = 0
                max_tries = max(1, pool.alive_count)
                continue
            if translated.http_status in _POOL_ROTATE_CODES and pool.alive_count > 1 and tried < max_tries:
                pool.rotate()
                rebuild_client()
                continue
            raise translated from err

    assert last_error is not None
    raise last_error


__all__ = ["KeyPool", "KeyPoolExhausted", "with_pool_rotation"]
