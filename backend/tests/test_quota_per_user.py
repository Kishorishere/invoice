"""Per-user pools — one user's usage never counts against another's."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlmodel import Session

from tests.conftest import login, login_as_admin


def test_pools_are_isolated(client) -> None:
    headers = login_as_admin(client)

    # Admin creates user B.
    client.post(
        "/api/admin/users",
        json={"email": "b@x.com", "password": "user-b-password", "role": "user"},
        headers=headers,
    )

    # Tight hourly cap.
    client.put(
        "/api/admin/limits",
        json={"max_per_hour": 2, "max_per_day": 10_000, "max_per_month": 100_000},
        headers=headers,
    )

    # Admin (user A) burns the cap.
    admin_id = client.get("/api/auth/me").json()["id"]
    from app.db import engine
    from app.models import Invoice

    with Session(engine) as s:
        for _ in range(2):
            s.add(
                Invoice(
                    user_id=admin_id,
                    provider="gemini",
                    file_name="s.png",
                    file_path="s.png",
                    mime_type="image/png",
                    data_json="{}",
                    validation_json="{}",
                    created_at=datetime.now(UTC),
                )
            )
        s.commit()

    # Admin is now at the ceiling.
    assert client.get("/api/limits").json()["remaining"]["hour"] == 0

    # Switch to user B — their pool is untouched.
    client.post("/api/auth/logout")
    login(client, "b@x.com", "user-b-password")
    body = client.get("/api/limits").json()
    assert body["usage"]["hour"] == 0
    assert body["remaining"]["hour"] == 2
