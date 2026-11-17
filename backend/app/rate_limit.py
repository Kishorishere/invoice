"""Shared slowapi `Limiter` instance.

Lives in its own module so routers can decorate with `@limiter.limit(...)`
without creating a cycle with `main.py`. `main.py` is the one that attaches
this limiter to the FastAPI app's state and registers the exception handler.
"""

from __future__ import annotations

from slowapi import Limiter

from app.config import get_settings
from app.deps import rate_key


_settings = get_settings()

limiter = Limiter(
    key_func=rate_key,
    default_limits=[_settings.rate_limit_default],
    # headers_enabled=False: injecting X-RateLimit-* headers requires every
    # decorated handler to take `response: Response`, which clutters signatures
    # across the whole app. The 429 Retry-After header is set in main.py's
    # exception handler, so clients still get the backoff signal.
    headers_enabled=False,
)


__all__ = ["limiter"]
