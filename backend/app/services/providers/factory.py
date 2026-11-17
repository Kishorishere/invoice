"""Provider factory."""

from __future__ import annotations

from app.config import get_settings
from app.services.providers.base import BaseProvider, ProviderError
from app.services.providers.keypool import KeyPool

# Pools persist across requests so a key that's been auth-killed stays killed
# until process restart. Keyed by provider name; populated lazily on first use.
_POOLS: dict[str, KeyPool] = {}


def _pool_for(name: str) -> KeyPool:
    settings = get_settings()
    if name not in _POOLS:
        if name == "gemini":
            _POOLS[name] = KeyPool(settings.gemini_api_keys, label="Gemini")
    return _POOLS[name]


def list_providers() -> list[str]:
    return get_settings().available_providers


def get_provider(name: str, *, model: str | None = None) -> BaseProvider:
    """Instantiate a provider. `model` overrides the configured default."""
    settings = get_settings()
    normalized = (name or "").strip().lower()

    if normalized == "gemini":
        from app.services.providers.gemini import GeminiProvider
        return GeminiProvider(
            key_pool=_pool_for("gemini"),
            model_id=model or settings.gemini_model,
        )

    raise ProviderError(
        f"Unknown provider '{name}'. Available providers: gemini.",
        http_status=400,
    )


def _reset_pools_for_tests() -> None:
    """Testing hook — drop cached pools so re-reading settings is honored."""
    _POOLS.clear()


def default_model_for(provider_name: str) -> str | None:
    settings = get_settings()
    name = (provider_name or "").strip().lower()
    if name == "gemini":
        return settings.gemini_model
    return None
