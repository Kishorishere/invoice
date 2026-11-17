"""Database engine + session management + startup bootstrap."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import event, text
from sqlalchemy.engine import Engine
from sqlmodel import Session, SQLModel, create_engine, select

from app.config import get_settings

log = logging.getLogger(__name__)


def _is_memory_sqlite(url: str) -> bool:
    return url.startswith("sqlite") and ":memory:" in url


def _build_engine() -> Engine:
    settings = get_settings()
    connect_args: dict[str, object] = {}
    if settings.database_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
    return create_engine(settings.database_url, echo=False, connect_args=connect_args)


engine: Engine = _build_engine()


@event.listens_for(engine, "connect")
def _apply_sqlite_pragmas(dbapi_connection, _connection_record) -> None:  # noqa: ANN001
    """WAL + sane durability defaults for SQLite.

    WAL gives us concurrent reads while a write transaction is open — the
    quota COUNT queries no longer block the extract-row INSERT. synchronous=
    NORMAL is the recommended pairing with WAL (durability on COMMIT, not on
    every write). busy_timeout prevents SQLITE_BUSY when writers overlap.
    No-op for non-SQLite drivers.
    """
    if not get_settings().database_url.startswith("sqlite"):
        return
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=5000")
    finally:
        cursor.close()


def init_db() -> None:
    # Import models so SQLModel.metadata knows about them.
    from app import models  # noqa: F401

    get_settings().ensure_dirs()

    if _is_memory_sqlite(get_settings().database_url):
        # In-memory databases don't persist — tests want a fresh schema per run.
        SQLModel.metadata.create_all(engine)
    else:
        _run_migrations()

    _bootstrap_admin()
    _bootstrap_limits()


def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session


def _run_migrations() -> None:
    """Run Alembic migrations up to head.

    The alembic.ini lives at `backend/alembic.ini` and names the env.py below
    it. We programmatically configure the DB URL from our Settings so there's
    a single source of truth (nobody has to re-edit alembic.ini to match .env).
    """
    from alembic import command
    from alembic.config import Config

    settings = get_settings()
    backend_root = Path(__file__).resolve().parent.parent  # backend/
    cfg = Config(str(backend_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(backend_root / "alembic"))
    cfg.set_main_option("sqlalchemy.url", settings.database_url)
    command.upgrade(cfg, "head")


def _bootstrap_admin() -> None:
    """Create or promote the admin named by ADMIN_EMAIL/ADMIN_PASSWORD.

    Idempotency rules:
    - If the user doesn't exist: create with the configured password, mark
      `bootstrapped_at = now()`.
    - If the user exists AND `bootstrapped_at` is NULL (migrated from an
      earlier version): set `bootstrapped_at` and promote role, but DO NOT
      overwrite the password — someone may have changed it via the admin API.
    - If the user exists AND `bootstrapped_at` is set: promote to admin if
      needed and leave the password alone.
    """
    from datetime import UTC, datetime

    settings = get_settings()
    email = settings.admin_email.strip().lower()
    password = settings.admin_password
    if not email or not password:
        return

    # Lazy imports so this module stays import-cheap.
    from app.auth import hash_password
    from app.models import User

    with Session(engine) as session:
        existing = session.exec(select(User).where(User.email == email)).first()
        now = datetime.now(UTC)
        if existing is None:
            session.add(
                User(
                    email=email,
                    hashed_password=hash_password(password),
                    role="admin",
                    bootstrapped_at=now,
                )
            )
            session.commit()
            log.info("admin_bootstrapped", extra={"email": email})
            return

        changed = False
        if existing.role != "admin":
            existing.role = "admin"
            changed = True
            log.info("admin_promoted", extra={"email": email})
        if existing.bootstrapped_at is None:
            existing.bootstrapped_at = now
            changed = True
        if changed:
            session.add(existing)
            session.commit()


def _bootstrap_limits() -> None:
    """Insert the singleton AppLimits row with defaults if missing."""
    from app.models import AppLimits
    from app.services.quotas import DEFAULTS

    with Session(engine) as session:
        if session.get(AppLimits, 1) is not None:
            return
        session.add(
            AppLimits(
                id=1,
                max_files_per_upload=DEFAULTS.max_files_per_upload,
                max_per_hour=DEFAULTS.max_per_hour,
                max_per_day=DEFAULTS.max_per_day,
                max_per_month=DEFAULTS.max_per_month,
            )
        )
        session.commit()
        log.info("limits_bootstrapped")


# `text` is re-exported for health-check use.
__all__ = ["engine", "get_session", "init_db", "text"]
