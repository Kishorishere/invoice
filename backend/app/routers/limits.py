"""GET /api/limits: the current user's quota + live usage."""

from __future__ import annotations

from fastapi import APIRouter, Request

from app.config import get_settings
from app.deps import CurrentUser, DbSession
from app.rate_limit import limiter
from app.schemas import LimitsStatus
from app.services.quotas import cached_status_for

router = APIRouter(tags=["limits"])

_settings = get_settings()


@router.get("/limits", response_model=LimitsStatus)
@limiter.limit(_settings.rate_limit_limits)
def my_limits(request: Request, user: CurrentUser, session: DbSession) -> LimitsStatus:
    return cached_status_for(session, user.id)


__all__ = ["router"]
