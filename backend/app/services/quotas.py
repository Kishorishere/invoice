"""Per-user quota enforcement.

Rolling-window counts straight off the invoices table — no counter rows, no
drift, no race. Admin edits one shared `AppLimits` row; every user gets their
own pool against those numbers.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import func
from sqlmodel import Session, select

from app.models import AppLimits, Invoice
from app.schemas import (
    LimitsConfig,
    LimitsPatch,
    LimitsStatus,
    WindowCounts,
    WindowResets,
)


DEFAULTS = LimitsConfig(
    max_files_per_upload=5,
    max_per_hour=60,
    max_per_day=500,
    max_per_month=5000,
)


def _row(session: Session) -> AppLimits:
    row = session.get(AppLimits, 1)
    if row is None:
        row = AppLimits(
            id=1,
            max_files_per_upload=DEFAULTS.max_files_per_upload,
            max_per_hour=DEFAULTS.max_per_hour,
            max_per_day=DEFAULTS.max_per_day,
            max_per_month=DEFAULTS.max_per_month,
        )
        session.add(row)
        session.commit()
        session.refresh(row)
    return row


def get_limits(session: Session) -> LimitsConfig:
    r = _row(session)
    return LimitsConfig(
        max_files_per_upload=r.max_files_per_upload,
        max_per_hour=r.max_per_hour,
        max_per_day=r.max_per_day,
        max_per_month=r.max_per_month,
    )


def set_limits(session: Session, patch: LimitsPatch) -> LimitsConfig:
    r = _row(session)
    if patch.max_files_per_upload is not None:
        r.max_files_per_upload = patch.max_files_per_upload
    if patch.max_per_hour is not None:
        r.max_per_hour = patch.max_per_hour
    if patch.max_per_day is not None:
        r.max_per_day = patch.max_per_day
    if patch.max_per_month is not None:
        r.max_per_month = patch.max_per_month

    # Positive-value guards. A zero on any window would brick /extract for
    # everyone; a negative would silently invert the comparison.
    if r.max_files_per_upload < 1:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "max_files_per_upload must be at least 1.",
        )
    if r.max_per_hour <= 0 or r.max_per_day <= 0 or r.max_per_month <= 0:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "All window limits (hour, day, month) must be greater than 0.",
        )

    # Sanity: wider windows must be >= narrower ones.
    if not (r.max_per_hour <= r.max_per_day <= r.max_per_month):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Limits must satisfy: hour ≤ day ≤ month.",
        )

    r.updated_at = datetime.now(UTC)
    session.add(r)
    session.commit()
    session.refresh(r)
    return get_limits(session)


def _count_since(session: Session, user_id: str, since: datetime) -> int:
    stmt = select(func.count(Invoice.id)).where(
        Invoice.user_id == user_id,
        Invoice.created_at >= since,
    )
    return int(session.exec(stmt).one() or 0)


def _ensure_aware(dt: datetime) -> datetime:
    """SQLite returns naive datetimes — treat them as UTC for the comparison."""
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def current_usage(session: Session, user_id: str, now: datetime | None = None) -> WindowCounts:
    now = _ensure_aware(now or datetime.now(UTC))
    return WindowCounts(
        hour=_count_since(session, user_id, now - timedelta(hours=1)),
        day=_count_since(session, user_id, now - timedelta(days=1)),
        month=_count_since(session, user_id, now - timedelta(days=30)),
    )


def status_for(session: Session, user_id: str, now: datetime | None = None) -> LimitsStatus:
    now = _ensure_aware(now or datetime.now(UTC))
    limits = get_limits(session)
    usage = current_usage(session, user_id, now)
    remaining = WindowCounts(
        hour=max(0, limits.max_per_hour - usage.hour),
        day=max(0, limits.max_per_day - usage.day),
        month=max(0, limits.max_per_month - usage.month),
    )
    reset_at = WindowResets(
        hour=now + timedelta(hours=1),
        day=now + timedelta(days=1),
        month=now + timedelta(days=30),
    )
    return LimitsStatus(limits=limits, usage=usage, remaining=remaining, reset_at=reset_at)


# ---- Status cache -----------------------------------------------------------
# The frontend meter polls /api/limits after every extract and on mount. Each
# call runs 3 COUNT(*) queries. We cache the per-user status for a few seconds
# and invalidate on extract (the only event that changes a user's count).
STATUS_CACHE_TTL_S = 5.0
_status_cache: dict[str, tuple[float, LimitsStatus]] = {}
_status_lock = threading.Lock()


def cached_status_for(session: Session, user_id: str) -> LimitsStatus:
    now = time.monotonic()
    with _status_lock:
        entry = _status_cache.get(user_id)
        if entry is not None and entry[0] > now:
            return entry[1]
    # Compute outside the lock — it hits the DB.
    fresh = status_for(session, user_id)
    with _status_lock:
        _status_cache[user_id] = (now + STATUS_CACHE_TTL_S, fresh)
    return fresh


def invalidate_user_status(user_id: str) -> None:
    """Called after an extract so the next meter poll sees the fresh row."""
    with _status_lock:
        _status_cache.pop(user_id, None)


def invalidate_status_cache() -> None:
    """Called after an admin updates limits — every user's cached caps are stale."""
    with _status_lock:
        _status_cache.clear()


# ---- Enforcement -----------------------------------------------------------


@dataclass
class QuotaExceeded:
    scope: str  # "hour" | "day" | "month"
    limit: int
    used: int
    retry_after_seconds: int


def check_and_reject(session: Session, user_id: str, now: datetime | None = None) -> None:
    """Raises HTTPException(429) with a structured body if any window is full."""
    now = _ensure_aware(now or datetime.now(UTC))
    limits = get_limits(session)
    usage = current_usage(session, user_id, now)

    offender: QuotaExceeded | None = None
    if usage.hour >= limits.max_per_hour:
        offender = QuotaExceeded("hour", limits.max_per_hour, usage.hour, 60 * 60)
    elif usage.day >= limits.max_per_day:
        offender = QuotaExceeded("day", limits.max_per_day, usage.day, 60 * 60 * 24)
    elif usage.month >= limits.max_per_month:
        offender = QuotaExceeded("month", limits.max_per_month, usage.month, 60 * 60 * 24 * 30)

    if offender is None:
        return

    remaining = WindowCounts(
        hour=max(0, limits.max_per_hour - usage.hour),
        day=max(0, limits.max_per_day - usage.day),
        month=max(0, limits.max_per_month - usage.month),
    )
    reset_at = (
        now + timedelta(seconds=offender.retry_after_seconds)
    ).isoformat()
    raise HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail={
            "message": f"You've hit your {offender.scope}ly limit ({offender.limit}).",
            "scope": offender.scope,
            "limit": offender.limit,
            "used": offender.used,
            "retry_after_seconds": offender.retry_after_seconds,
            "reset_at": reset_at,
            "remaining": remaining.model_dump(),
        },
        headers={"Retry-After": str(offender.retry_after_seconds)},
    )


__all__ = [
    "DEFAULTS",
    "cached_status_for",
    "check_and_reject",
    "current_usage",
    "get_limits",
    "invalidate_status_cache",
    "invalidate_user_status",
    "set_limits",
    "status_for",
]
