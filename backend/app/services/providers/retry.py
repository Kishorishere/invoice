"""Tenacity-powered retries for provider SDK calls.

Only retries on transient failures — rate limits and timeouts. Never retries
auth errors (will not become valid on a retry) or bad-input errors (the
image or model id is wrong and that won't change).
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from tenacity import (
    AsyncRetrying,
    RetryError,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from app.services.providers.base import ProviderError
from app.services.providers.errors import translate

log = logging.getLogger(__name__)


def _retriable(provider_name: str) -> Callable[[BaseException], bool]:
    """A predicate that says yes only on transient failures."""

    def _predicate(exc: BaseException) -> bool:
        if isinstance(exc, asyncio.TimeoutError):
            return True

        # ProviderError carries an http_status. 429 (rate limit) and 5xx
        # (upstream overload — 500, 502, 503, 504) are the canonical
        # transient failures worth retrying.
        retriable_codes = (429, 500, 502, 503, 504)
        if isinstance(exc, ProviderError):
            return exc.http_status in retriable_codes

        # Unknown exceptions: translate to decide retriability.
        if isinstance(exc, Exception):
            translated = translate(provider_name, exc)
            return translated.http_status in retriable_codes
        return False

    return _predicate


async def retry_provider(
    provider_name: str,
    attempt: Callable[[], Awaitable[Any]],
    max_attempts: int,
) -> Any:
    """Call `attempt()` with retries on rate-limit / timeout only.

    `max_attempts` is the total number of calls, including the first try.
    Backoff: 0.5s, 1s, 2s, 4s (capped).
    """
    total = max(1, max_attempts + 1)  # settings.provider_retry_attempts = retries
    try:
        async for retry_state in AsyncRetrying(
            stop=stop_after_attempt(total),
            wait=wait_exponential(multiplier=0.5, min=0.5, max=4),
            retry=retry_if_exception(_retriable(provider_name)),
            reraise=True,
        ):
            with retry_state:
                return await attempt()
    except RetryError as err:
        # Unwrap the last underlying exception.
        last = err.last_attempt.exception()
        if last is not None:
            raise last from None
        raise
    # Unreachable — AsyncRetrying either returns or raises.
    raise RuntimeError("retry loop exited without a result")


__all__ = ["retry_provider"]
