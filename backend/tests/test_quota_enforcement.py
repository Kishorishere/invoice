"""Quota enforcement — verified without ever calling the AI provider by
seeding Invoice rows directly and watching /api/extract return 429 before any
provider code runs.
"""

from __future__ import annotations

import io
from datetime import UTC, datetime

from sqlmodel import Session

from tests.conftest import login_as_admin


def _seed_invoices(user_id: str, n: int) -> None:
    from app.db import engine
    from app.models import Invoice

    with Session(engine) as session:
        for i in range(n):
            session.add(
                Invoice(
                    user_id=user_id,
                    provider="gemini",
                    file_name=f"seed-{i}.png",
                    file_path=f"seed-{i}.png",
                    mime_type="image/png",
                    data_json="{}",
                    validation_json="{}",
                    created_at=datetime.now(UTC),
                )
            )
        session.commit()


def _me_id(client) -> str:
    return client.get("/api/auth/me").json()["id"]


def _tiny_png() -> bytes:
    # Smallest valid PNG so the request gets as far as the quota gate.
    return (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xf8\x0f"
        b"\x00\x00\x01\x01\x00\x01\x00\x18\xdd\x8d\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    )


def _set_hour_limit(client, headers: dict[str, str], n: int) -> None:
    r = client.put(
        "/api/admin/limits",
        json={"max_per_hour": n, "max_per_day": max(n, 10_000), "max_per_month": max(n, 100_000)},
        headers=headers,
    )
    assert r.status_code == 200, r.text


def test_429_when_hourly_cap_reached(client) -> None:
    headers = login_as_admin(client)
    _set_hour_limit(client, headers, n=2)

    uid = _me_id(client)
    _seed_invoices(uid, 2)

    # /api/limits reflects the usage.
    body = client.get("/api/limits").json()
    assert body["usage"]["hour"] == 2
    assert body["remaining"]["hour"] == 0

    # Extract is rejected at the gate, before any provider work.
    files = {"file": ("x.png", io.BytesIO(_tiny_png()), "image/png")}
    r = client.post(
        "/api/extract",
        data={"provider": "gemini"},
        files=files,
        headers=headers,
    )
    assert r.status_code == 429, r.text
    detail = r.json()["detail"]
    assert detail["scope"] == "hour"
    assert detail["limit"] == 2
    assert detail["used"] == 2
    assert "retry_after_seconds" in detail
    assert r.headers.get("Retry-After") is not None


def test_under_cap_passes_the_quota_gate(client) -> None:
    """At 1 of 2, we pass the quota check. The call will fail downstream because
    we have no provider credentials in tests — but the status will not be 429."""
    headers = login_as_admin(client)
    _set_hour_limit(client, headers, n=2)

    uid = _me_id(client)
    _seed_invoices(uid, 1)

    files = {"file": ("x.png", io.BytesIO(_tiny_png()), "image/png")}
    r = client.post(
        "/api/extract",
        data={"provider": "gemini"},
        files=files,
        headers=headers,
    )
    assert r.status_code != 429, r.text
