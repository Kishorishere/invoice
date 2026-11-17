"""POST /extract: image -> structured invoice -> validation -> persisted."""

from __future__ import annotations

import asyncio
import logging
import uuid
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Form, HTTPException, Request, UploadFile, status
from pydantic import ValidationError

from app.config import get_settings
from app.deps import CsrfProtected, CurrentUser, DbSession
from app.models import Invoice
from app.schemas import ExtractResponse, InvoiceData, ModelInfo, ModelsResponse, ProvidersInfo
from app.services.dedupe import find_duplicate, raise_duplicate, sha256_hex
from app.services.mime import UnsupportedUpload, assert_accepted
from app.services.pdf import pdf_first_page_png
from app.services.providers import (
    ProviderError,
    default_model_for,
    get_provider,
    list_providers,
)
from app.services.providers.model_cache import cached as cached_models
from app.services.quotas import check_and_reject, invalidate_user_status
from app.services.validator import validate

log = logging.getLogger(__name__)

router = APIRouter(tags=["extract"])


@router.get("/providers", response_model=ProvidersInfo)
def providers(request: Request) -> ProvidersInfo:
    available = list_providers()
    default = available[0] if available else None
    return ProvidersInfo(available=available, default=default)


@router.get("/providers/{name}/models", response_model=ModelsResponse)
async def provider_models(request: Request, name: str) -> ModelsResponse:
    """Vision-capable models for `name`. Cached for 24h to avoid hammering upstream."""
    try:
        impl = get_provider(name)
    except ProviderError as err:
        raise HTTPException(err.http_status, err.user_message) from err

    cache_key = f"models:{impl.name}"

    async def _loader() -> list[dict[str, str]]:
        return await impl.list_models()

    try:
        models_raw, was_hit = await cached_models(cache_key, _loader)
    except ProviderError as err:
        log.warning(
            "models_list_failed",
            extra={"provider": impl.name, "detail": err.debug_detail or ""},
        )
        raise HTTPException(err.http_status, err.user_message) from err

    return ModelsResponse(
        provider=impl.name,
        default=default_model_for(impl.name),
        models=[ModelInfo(**m) for m in models_raw],
        cached=was_hit,
    )


# Mapping canonical sniffed MIME -> file extension on disk.
_EXT_FOR_MIME = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "application/pdf": ".pdf",
}


@router.post("/extract", response_model=ExtractResponse)
async def extract(
    _csrf: CsrfProtected,
    user: CurrentUser,
    session: DbSession,
    file: UploadFile,
    model: Annotated[str | None, Form()] = None,
    force: Annotated[bool, Form()] = False,
) -> ExtractResponse:
    provider = "gemini"
    # Note: /extract is intentionally NOT decorated with slowapi. The per-user
    # rolling-window quota below is the authoritative throttle for this endpoint.
    settings = get_settings()

    raw = await file.read()
    size_mb = len(raw) / (1024 * 1024)
    if size_mb > settings.max_upload_mb:
        # Belt-and-suspenders — the body-size middleware should have caught
        # this already via Content-Length. If we got here the client lied.
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            f"File is {size_mb:.1f}MB; the limit is {settings.max_upload_mb}MB.",
        )

    # Magic-byte sniffing. The declared Content-Type is user-controlled; the
    # bytes are not. We log the mismatch for visibility.
    try:
        sniffed = assert_accepted(raw, file.content_type)
    except UnsupportedUpload as err:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, str(err)) from err
    if file.content_type and file.content_type.lower() != sniffed and not (
        file.content_type.lower() == "image/jpg" and sniffed == "image/jpeg"
    ):
        log.info(
            "mime_mismatch",
            extra={
                "declared": file.content_type,
                "sniffed": sniffed,
                "filename": file.filename,
            },
        )

    # Per-user dedupe: SHA-256 of the raw upload. If this user already has an
    # invoice with these exact bytes, refuse with 409 unless the caller asked
    # to force a re-extract. The 409 path does NOT tick the quota — the user
    # isn't consuming an extraction.
    content_hash = sha256_hex(raw)
    if not force:
        existing = find_duplicate(session, user.id, content_hash)
        if existing is not None:
            log.info(
                "dedupe_hit",
                extra={
                    "user_id": user.id,
                    "duplicate_of": existing.id,
                    "filename": file.filename,
                },
            )
            raise_duplicate(existing)

    # Per-user rolling quota. Raises 429 with a structured body when full.
    check_and_reject(session, user.id)

    # Rasterize PDF page 1 on a worker thread (CPU-bound PIL encode blocks the loop).
    if sniffed == "application/pdf":
        try:
            image_bytes = await asyncio.to_thread(pdf_first_page_png, raw)
        except ValueError as err:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(err)) from err
        send_mime = "image/png"
    else:
        image_bytes = raw
        send_mime = sniffed

    try:
        provider_impl = get_provider(provider, model=model)
    except ProviderError as err:
        log.warning(
            "provider_resolution_failed",
            extra={"provider": provider, "detail": err.debug_detail or err.user_message},
        )
        raise HTTPException(err.http_status, err.user_message) from err

    try:
        raw_data = await provider_impl.extract(image_bytes, send_mime)
    except ProviderError as err:
        log.warning(
            "provider_call_failed",
            extra={"provider": provider_impl.name, "detail": err.debug_detail or ""},
        )
        raise HTTPException(err.http_status, err.user_message) from err

    try:
        inv = InvoiceData.model_validate(raw_data)
    except ValidationError as err:
        log.warning(
            "provider_offschema",
            extra={"provider": provider_impl.name, "errors": err.errors()},
        )
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"{provider_impl.name.title()} returned data in an unexpected shape. "
            f"Try again in a moment.",
        ) from err

    validation = validate(inv)

    # Persist the uploaded file. write_bytes is sync disk I/O — run off the loop.
    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    ext = _EXT_FOR_MIME.get(sniffed, ".bin")
    file_id = uuid.uuid4().hex
    rel_path = f"{file_id}{ext}"
    await asyncio.to_thread((upload_dir / rel_path).write_bytes, raw)

    row = Invoice(
        user_id=user.id,
        provider=provider_impl.name,
        model=getattr(provider_impl, "model_id", None),
        file_name=file.filename or "invoice",
        file_path=rel_path,
        mime_type=sniffed,
        data_json=inv.model_dump_json(),
        validation_json=validation.model_dump_json(),
        invoice_number=inv.invoice_number,
        supplier_name=inv.supplier.name,
        total_amount=float(inv.total),
        currency=inv.currency,
        invoice_date=inv.invoice_date,
        due_date=inv.due_date,
        all_checks_pass=validation.all_pass,
        content_hash=content_hash,
    )
    session.add(row)
    session.commit()
    session.refresh(row)

    # The new row changes the user's rolling-window counts; drop their cache
    # entry so the meter reflects it on the next /api/limits poll.
    invalidate_user_status(user.id)

    return ExtractResponse(
        invoice_id=row.id,
        provider=row.provider,
        model=row.model,
        data=inv,
        validation=validation,
        created_at=row.created_at,
    )


__all__ = ["router"]
