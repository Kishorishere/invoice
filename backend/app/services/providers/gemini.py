"""Gemini provider using the google-genai SDK (new unified SDK).

Note on schema: the SDK's `response_schema` wants a Gemini-native Schema
(uppercase types + `nullable: true`), not standard JSON Schema with
`type: ["string", "null"]` unions. Rather than maintain two schema dialects,
we skip `response_schema` and pin the shape via `response_mime_type` +
inlining the JSON schema in the prompt. Gemini 2.0 Flash follows this reliably
at temperature 0.
"""

from __future__ import annotations

import asyncio
import json
import logging

from app.config import get_settings
from app.services.providers.base import BaseProvider, ProviderError
from app.services.providers.errors import translate
from app.services.providers.keypool import KeyPool, with_pool_rotation
from app.services.providers.prompt import INVOICE_JSON_SCHEMA, SYSTEM_PROMPT
from app.services.providers.retry import retry_provider

log = logging.getLogger(__name__)


class GeminiProvider(BaseProvider):
    name = "gemini"

    def __init__(self, key_pool: KeyPool, model_id: str) -> None:
        if len(key_pool) == 0:
            raise ProviderError(
                "Gemini is not configured on this server. Set GEMINI_API_KEY and restart."
            )
        self.model_id = model_id
        self._pool = key_pool
        # Imported lazily so the server starts even if the SDK is absent.
        from google import genai  # type: ignore[import-not-found]

        self._genai = genai
        self._client = genai.Client(api_key=key_pool.current())

    def _rebuild_client(self) -> None:
        self._client = self._genai.Client(api_key=self._pool.current())

    async def extract(self, image_bytes: bytes, mime_type: str) -> dict:
        from google.genai import types  # type: ignore[import-not-found]

        prompt = (
            SYSTEM_PROMPT
            + "\n\nReturn JSON matching this schema exactly (no prose, no markdown):\n"
            + json.dumps(INVOICE_JSON_SCHEMA)
        )
        contents = [
            types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
            prompt,
        ]
        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.0,
        )

        def _call() -> object:
            return self._client.models.generate_content(
                model=self.model_id,
                contents=contents,
                config=config,
            )

        settings = get_settings()

        async def _attempt() -> object:
            return await asyncio.wait_for(
                asyncio.to_thread(_call),
                timeout=settings.gemini_timeout_s,
            )

        try:
            response = await with_pool_rotation(
                self._pool,
                self._rebuild_client,
                lambda: retry_provider("Gemini", _attempt, settings.provider_retry_attempts),
                provider_name="Gemini",
            )
        except asyncio.TimeoutError as err:
            raise ProviderError(
                "Gemini didn't respond in time. Try again, or switch to the other provider.",
                http_status=504,
                debug_detail="asyncio.wait_for timeout",
            ) from err

        text = getattr(response, "text", None)
        if not text:
            raise ProviderError(
                "Gemini returned an empty response. Try again in a moment.",
                debug_detail="empty response text",
            )

        try:
            data = json.loads(_strip_code_fence(text))
        except json.JSONDecodeError as err:
            raise ProviderError(
                "Gemini returned data we couldn't parse. Try again — this usually fixes it.",
                http_status=502,
                debug_detail=f"JSON decode error: {err}; raw={text[:500]}",
            ) from err

        if not isinstance(data, dict):
            raise ProviderError(
                "Gemini returned unexpected data. Try again in a moment.",
                debug_detail=f"non-object JSON: {type(data).__name__}",
            )
        return data

    async def list_models(self) -> list[dict[str, str]]:
        def _call() -> object:
            return list(self._client.models.list())

        raw = await with_pool_rotation(
            self._pool,
            self._rebuild_client,
            lambda: asyncio.to_thread(_call),
            provider_name="Gemini",
        )

        out: list[dict[str, str]] = []
        for m in raw:
            name = str(getattr(m, "name", "") or "").removeprefix("models/")
            if not name:
                continue
            actions = (
                getattr(m, "supported_actions", None)
                or getattr(m, "supported_generation_methods", None)
                or []
            )
            if actions and not any(
                a in actions for a in ("generateContent", "generate_content")
            ):
                continue
            lower = name.lower()
            if any(kw in lower for kw in ("embedding", "aqa", "imagen", "tts")):
                continue
            display = str(getattr(m, "display_name", None) or _pretty(name))
            out.append({"id": name, "label": display})

        out.sort(key=lambda m: (-_version_score(m["id"]), m["id"]))
        return out


def _pretty(model_id: str) -> str:
    return " ".join(part.capitalize() for part in model_id.replace("-", " ").split())


def _version_score(model_id: str) -> int:
    import re

    nums = re.findall(r"(\d+)\.(\d+)", model_id)
    if not nums:
        return 0
    major, minor = nums[0]
    return int(major) * 10 + int(minor)


def _strip_code_fence(text: str) -> str:
    """Defensive: `response_mime_type=application/json` should prevent fences,
    but the occasional model drift still produces ```json ... ``` wrappers."""
    stripped = text.strip()
    if stripped.startswith("```"):
        parts = stripped.split("\n", 1)
        if len(parts) == 2:
            body = parts[1]
            if body.rstrip().endswith("```"):
                body = body.rstrip()[:-3]
            return body.strip()
    return stripped
