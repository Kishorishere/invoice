"""Per-user dedupe on POST /api/extract.

These tests never invoke the real AI provider — the duplicate check runs
before quota and before any provider call, so a 409 vs. non-409 response
is a clean signal.
"""

from __future__ import annotations

import hashlib
import io
from datetime import UTC, datetime

from sqlmodel import Session, select

from tests.conftest import ADMIN_EMAIL, ADMIN_PASSWORD, login, login_as_admin


# --- Smallest valid PNG (same byte-string across tests) ---------------------
PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xf8\x0f"
    b"\x00\x00\x01\x01\x00\x01\x00\x18\xdd\x8d\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)
PNG_HASH = hashlib.sha256(PNG).hexdigest()


def _me_id(client) -> str:
    return client.get("/api/auth/me").json()["id"]


def _seed_invoice(user_id: str, *, content_hash: str) -> str:
    """Seed one Invoice row with an explicit content_hash. Returns its id."""
    from app.db import engine
    from app.models import Invoice

    with Session(engine) as session:
        row = Invoice(
            user_id=user_id,
            provider="gemini",
            file_name="original.png",
            file_path="seeded.png",
            mime_type="image/png",
            data_json='{"invoice_number":"INV-001","total":500.0,"currency":"NPR"}',
            validation_json='{"checks":[],"all_pass":true}',
            invoice_number="INV-001",
            supplier_name="Rivertech Supplies Ltd.",
            total_amount=500.0,
            currency="NPR",
            all_checks_pass=True,
            content_hash=content_hash,
            created_at=datetime.now(UTC),
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return row.id


def _invoice_count(user_id: str) -> int:
    from app.db import engine
    from app.models import Invoice

    with Session(engine) as session:
        return len(session.exec(select(Invoice).where(Invoice.user_id == user_id)).all())


def _post_extract(client, headers, *, force: bool = False):
    data = {"provider": "gemini"}
    if force:
        data["force"] = "true"
    files = {"file": ("invoice.png", io.BytesIO(PNG), "image/png")}
    return client.post("/api/extract", data=data, files=files, headers=headers)


def test_dedupe_hit_returns_409_with_details(client) -> None:
    headers = login_as_admin(client)
    uid = _me_id(client)
    existing_id = _seed_invoice(uid, content_hash=PNG_HASH)

    r = _post_extract(client, headers)

    assert r.status_code == 409, r.text
    detail = r.json()["detail"]
    assert detail["duplicate_of"] == existing_id
    assert detail["invoice_number"] == "INV-001"
    assert detail["supplier_name"] == "Rivertech Supplies Ltd."
    assert detail["total_amount"] == 500.0
    assert detail["currency"] == "NPR"
    assert detail["all_checks_pass"] is True
    assert "uploaded_at" in detail


def test_dedupe_409_does_not_tick_quota(client) -> None:
    """Three dedupe hits → row count stays at 1, usage stays at 1."""
    headers = login_as_admin(client)
    uid = _me_id(client)
    _seed_invoice(uid, content_hash=PNG_HASH)

    for _ in range(3):
        r = _post_extract(client, headers)
        assert r.status_code == 409

    assert _invoice_count(uid) == 1
    body = client.get("/api/limits").json()
    assert body["usage"]["hour"] == 1


def test_force_overrides_dedupe(client) -> None:
    """force=true skips the 409. The call then fails downstream because the
    test env has no provider credentials — but NOT with 409."""
    headers = login_as_admin(client)
    uid = _me_id(client)
    _seed_invoice(uid, content_hash=PNG_HASH)

    r = _post_extract(client, headers, force=True)

    assert r.status_code != 409, r.text
    # And it didn't get blocked by quota either.
    assert r.status_code != 429, r.text


def test_dedupe_is_per_user(client) -> None:
    """User A seeds a hash; user B uploading the same bytes is NOT a duplicate."""
    # Admin creates a second user.
    admin_headers = login_as_admin(client)
    r = client.post(
        "/api/admin/users",
        json={"email": "u2@example.com", "password": "second-user-pw-12345", "role": "user"},
        headers=admin_headers,
    )
    assert r.status_code == 201, r.text

    # User A (admin) seeds a hash in their own row.
    admin_id = _me_id(client)
    _seed_invoice(admin_id, content_hash=PNG_HASH)
    client.post("/api/auth/logout")
    # Cookies from logout: make sure we drop them explicitly.
    client.cookies.clear()

    # User B logs in; uploading the same bytes must NOT trip the dedupe.
    b_headers = login(client, "u2@example.com", "second-user-pw-12345")
    r = _post_extract(client, b_headers)
    assert r.status_code != 409, r.text


def test_dedupe_matches_only_exact_bytes(client) -> None:
    """A different byte-string (different hash) does NOT trip dedupe."""
    headers = login_as_admin(client)
    uid = _me_id(client)
    _seed_invoice(uid, content_hash=PNG_HASH)

    # One extra null byte at the end → different sha256.
    other = PNG + b"\x00"
    files = {"file": ("other.png", io.BytesIO(other), "image/png")}
    r = client.post(
        "/api/extract",
        data={"provider": "gemini"},
        files=files,
        headers=headers,
    )
    # Not 409. (The MIME sniffer also accepts it because the PNG magic bytes
    # are unchanged at the head.)
    assert r.status_code != 409, r.text
