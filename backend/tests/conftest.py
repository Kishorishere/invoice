"""Test fixtures: isolated SQLite DB + FastAPI TestClient per test."""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest

# Environment MUST be set before importing the app.
os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("CORS_ORIGINS", "")

ADMIN_EMAIL = "admin@example.com"
ADMIN_PASSWORD = "admin-test-pw-12345"


@pytest.fixture
def tmp_db(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[None]:
    db_path = tmp_path / "test.db"
    upload_dir = tmp_path / "uploads"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("UPLOAD_DIR", str(upload_dir))
    monkeypatch.setenv("ADMIN_EMAIL", ADMIN_EMAIL)
    monkeypatch.setenv("ADMIN_PASSWORD", ADMIN_PASSWORD)

    # Clear the cached settings + re-import the app with fresh engine.
    from app import config as _config
    from app import db as _db

    _config.get_settings.cache_clear()
    _db.engine = _db._build_engine()  # type: ignore[attr-defined]
    _db.init_db()

    # Reset slowapi's in-memory counters so limits are per-test, not global.
    from app.rate_limit import limiter as _limiter

    _limiter.reset()
    yield


@pytest.fixture
def client(tmp_db: None):
    from fastapi.testclient import TestClient
    from app.main import app

    with TestClient(app) as c:
        yield c


def login(client, email: str, password: str) -> dict[str, str]:
    """Log in and return headers suitable for a state-changing request."""
    r = client.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    csrf = client.cookies.get("ix_csrf")
    assert csrf, "login should set the csrf cookie"
    return {"X-CSRF-Token": csrf}


def login_as_admin(client) -> dict[str, str]:
    return login(client, ADMIN_EMAIL, ADMIN_PASSWORD)
