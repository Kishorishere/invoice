"""Provider interface."""

from __future__ import annotations

from abc import ABC, abstractmethod


class ProviderError(RuntimeError):
    """User-visible provider failure.

    `user_message` is what the frontend shows (friendly, actionable).
    `http_status` is what the API returns (502 by default; 401/429/504 when known).
    `debug_detail` is the raw upstream error (logged server-side, never sent).
    """

    def __init__(
        self,
        user_message: str,
        *,
        http_status: int = 502,
        debug_detail: str | None = None,
    ) -> None:
        super().__init__(user_message)
        self.user_message = user_message
        self.http_status = http_status
        self.debug_detail = debug_detail


class BaseProvider(ABC):
    name: str

    @abstractmethod
    async def extract(self, image_bytes: bytes, mime_type: str) -> dict:
        """Return a dict shaped like InvoiceData. Raise ProviderError on failure."""

    @abstractmethod
    async def list_models(self) -> list[dict[str, str]]:
        """Return `[{"id": "...", "label": "..."}]` for vision-capable models."""
