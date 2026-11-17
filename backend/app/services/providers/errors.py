"""Translate upstream SDK exceptions into user-friendly ProviderErrors.

Prefers typed exceptions from the google-genai SDK, with a string-matching
fallback for anything typed checks miss (unknown SDK versions, transport-layer
errors, etc).
"""

from __future__ import annotations

from app.services.providers.base import ProviderError

# ---- Fallback keyword buckets (for errors that don't come typed). ----
_AUTH = ("api_key", "invalid key", "permission_denied", "unauthenticated", "unauthorized", " 401", " 403")
_NOT_FOUND = (" 404", "not_found", "no longer available", "not found")
_RATE = (" 429", "quota", "rate limit", "resource_exhausted")
_TIMEOUT = ("timeout", "timed out", "deadline exceeded", " 504")
_BAD_INPUT = ("invalid_argument", "unsupported", " 400")
_SAFETY = ("safety", "blocked", "harmful", "finish_reason")


def translate(provider_name: str, err: Exception) -> ProviderError:
    # 1) Typed-exception path — fast, exact, survives error-message drift.
    typed = _translate_typed(provider_name, err)
    if typed is not None:
        return typed

    # 2) Fallback string-matching bucket.
    raw = str(err)
    low = raw.lower()

    if _any(low, raw, _AUTH):
        return _auth_error(provider_name, raw)
    if _any(low, raw, _NOT_FOUND):
        return _not_found_error(provider_name, raw)
    if _any(low, raw, _RATE):
        return _rate_error(provider_name, raw)
    if _any(low, raw, _TIMEOUT):
        return _timeout_error(provider_name, raw)
    if _any(low, raw, _BAD_INPUT):
        return _bad_input_error(provider_name, raw)
    if _any(low, raw, _SAFETY):
        return _safety_error(provider_name, raw)

    return ProviderError(
        f"{provider_name} couldn't process this invoice. Try again in a moment.",
        http_status=502,
        debug_detail=raw,
    )


def _translate_typed(provider_name: str, err: Exception) -> ProviderError | None:
    """Return a ProviderError when `err` is a known SDK exception, else None."""
    name_lower = provider_name.lower()
    raw = str(err)

    if name_lower == "gemini":
        try:
            from google.genai import errors as gerrs  # type: ignore[import-not-found]
        except ImportError:
            return None
        api_error = getattr(gerrs, "APIError", None)
        if api_error is not None and isinstance(err, api_error):
            return _by_status_code(provider_name, getattr(err, "code", 502), raw)

    return None


def _by_status_code(provider_name: str, code: int, raw: str) -> ProviderError:
    if code in (401, 403):
        return _auth_error(provider_name, raw)
    if code == 404:
        return _not_found_error(provider_name, raw)
    if code == 429:
        return _rate_error(provider_name, raw)
    if code in (408, 504):
        return _timeout_error(provider_name, raw)
    if 400 <= code < 500:
        return _bad_input_error(provider_name, raw)
    if code in (500, 502, 503):
        return ProviderError(
            f"{provider_name} had an upstream error (status {code}).",
            http_status=code,
            debug_detail=raw,
        )
    return ProviderError(
        f"{provider_name} had an upstream error (status {code}).",
        http_status=502,
        debug_detail=raw,
    )


# ---- Shared translators so typed + string paths produce identical copy. ----


def _auth_error(provider_name: str, raw: str) -> ProviderError:
    return ProviderError(
        f"The {provider_name} API key is missing, invalid, or lacks access. "
        f"Check the server configuration and try again.",
        http_status=502,
        debug_detail=raw,
    )


def _not_found_error(provider_name: str, raw: str) -> ProviderError:
    return ProviderError(
        f"{provider_name} says the configured model isn't available. "
        f"Set GEMINI_MODEL to a current model and restart the server.",
        http_status=502,
        debug_detail=raw,
    )


def _rate_error(provider_name: str, raw: str) -> ProviderError:
    return ProviderError(
        f"{provider_name} is rate-limited right now. Wait a moment and try again.",
        http_status=429,
        debug_detail=raw,
    )


def _timeout_error(provider_name: str, raw: str) -> ProviderError:
    return ProviderError(
        f"{provider_name} didn't respond in time. Try again in a moment.",
        http_status=504,
        debug_detail=raw,
    )


def _bad_input_error(provider_name: str, raw: str) -> ProviderError:
    return ProviderError(
        f"{provider_name} rejected the request. "
        f"The image may be too large or an unsupported format.",
        http_status=400,
        debug_detail=raw,
    )


def _safety_error(provider_name: str, raw: str) -> ProviderError:
    return ProviderError(
        f"{provider_name} blocked the response. Try a different image.",
        http_status=502,
        debug_detail=raw,
    )


def _any(low: str, raw: str, needles: tuple[str, ...]) -> bool:
    return any(n in low or n in raw for n in needles)
