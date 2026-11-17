"""Admin-only: read/update the shared quota config."""

from __future__ import annotations

from fastapi import APIRouter, Request

from app.config import get_settings
from app.deps import CsrfProtected, CurrentAdmin, DbSession
from app.rate_limit import limiter
from app.schemas import LimitsConfig, LimitsPatch
from app.services.quotas import get_limits, invalidate_status_cache, set_limits

router = APIRouter(prefix="/admin/limits", tags=["admin"])

_settings = get_settings()


@router.get("", response_model=LimitsConfig)
@limiter.limit(_settings.rate_limit_admin_read)
def read_limits(
    request: Request, admin: CurrentAdmin, session: DbSession
) -> LimitsConfig:
    return get_limits(session)


@router.put("", response_model=LimitsConfig)
@limiter.limit(_settings.rate_limit_admin_write)
def update_limits(
    request: Request,
    body: LimitsPatch,
    _csrf: CsrfProtected,
    admin: CurrentAdmin,
    session: DbSession,
) -> LimitsConfig:
    updated = set_limits(session, body)
    # Users' cached /api/limits status now reflects stale caps — flush all.
    invalidate_status_cache()
    return updated


__all__ = ["router"]
