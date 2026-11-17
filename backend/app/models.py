"""Persistence models."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import Index
from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _uuid() -> str:
    return uuid4().hex


class User(SQLModel, table=True):
    __tablename__ = "users"

    id: str = Field(default_factory=_uuid, primary_key=True)
    email: str = Field(index=True, unique=True)
    hashed_password: str
    role: str = Field(default="user")  # "user" | "admin"
    created_at: datetime = Field(default_factory=_utcnow)
    # Set when the admin-bootstrap routine has already run for this account.
    # Prevents the startup bootstrap from overwriting a password that was
    # later changed via the admin API — see db.py::_bootstrap_admin.
    bootstrapped_at: datetime | None = Field(default=None)


class Invoice(SQLModel, table=True):
    __tablename__ = "invoices"

    id: str = Field(default_factory=_uuid, primary_key=True)
    user_id: str = Field(index=True, foreign_key="users.id")
    provider: str  # "gemini" (historical rows may hold other values)
    model: str | None = Field(default=None)  # e.g. "gemini-2.5-flash"
    file_name: str
    file_path: str  # relative path inside UPLOAD_DIR
    mime_type: str

    # Extracted structured data (JSON-serialized)
    data_json: str
    # Validation result (JSON-serialized)
    validation_json: str

    # Flat fields for list sorting / filtering
    invoice_number: str | None = Field(default=None, index=True)
    supplier_name: str | None = None
    total_amount: float | None = None
    currency: str | None = None
    invoice_date: str | None = None  # ISO date string
    due_date: str | None = None
    all_checks_pass: bool = False

    # SHA-256 (hex) of the raw upload bytes. Used for per-user dedupe: a POST
    # /extract whose (user_id, content_hash) already exists returns 409 unless
    # the caller passes force=true. Nullable for legacy rows backfilled lazily.
    content_hash: str | None = Field(default=None)

    created_at: datetime = Field(default_factory=_utcnow, index=True)

    __table_args__ = (
        Index("ix_invoices_user_created", "user_id", "created_at"),
        Index("ix_invoices_user_hash", "user_id", "content_hash"),
    )


class AppLimits(SQLModel, table=True):
    """Singleton row (id=1): admin-configured per-user quotas."""

    __tablename__ = "app_limits"

    id: int = Field(default=1, primary_key=True)
    max_files_per_upload: int = Field(default=5)
    max_per_hour: int = Field(default=60)
    max_per_day: int = Field(default=500)
    max_per_month: int = Field(default=5000)
    updated_at: datetime = Field(default_factory=_utcnow)
