from __future__ import annotations

from tests.conftest import login, login_as_admin


def test_defaults_served_on_empty_db(client) -> None:
    headers = login_as_admin(client)
    r = client.get("/api/admin/limits", headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()
    for key in ("max_files_per_upload", "max_per_hour", "max_per_day", "max_per_month"):
        assert isinstance(body[key], int) and body[key] > 0


def test_non_admin_forbidden(client) -> None:
    headers = login_as_admin(client)
    client.post(
        "/api/admin/users",
        json={"email": "u@x.com", "password": "user-password-12", "role": "user"},
        headers=headers,
    )
    client.post("/api/auth/logout")
    login(client, "u@x.com", "user-password-12")

    assert client.get("/api/admin/limits").status_code == 403


def test_round_trip_partial_update(client) -> None:
    headers = login_as_admin(client)
    r = client.put(
        "/api/admin/limits",
        json={"max_files_per_upload": 7, "max_per_hour": 10},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["max_files_per_upload"] == 7
    assert body["max_per_hour"] == 10

    # Unspecified fields keep their previous (default) values.
    again = client.get("/api/admin/limits", headers=headers).json()
    assert again["max_files_per_upload"] == 7
    assert again["max_per_day"] >= 10


def test_rejects_zero_and_negative(client) -> None:
    headers = login_as_admin(client)
    r = client.put("/api/admin/limits", json={"max_per_hour": 0}, headers=headers)
    assert r.status_code == 422
    r = client.put("/api/admin/limits", json={"max_files_per_upload": -1}, headers=headers)
    assert r.status_code == 422


def test_rejects_window_inversion(client) -> None:
    headers = login_as_admin(client)
    # hour > day is nonsense.
    r = client.put(
        "/api/admin/limits",
        json={"max_per_hour": 100, "max_per_day": 50},
        headers=headers,
    )
    assert r.status_code == 422


def test_user_can_read_their_status(client) -> None:
    login_as_admin(client)
    r = client.get("/api/limits")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["usage"]["hour"] == 0
    assert body["remaining"]["hour"] == body["limits"]["max_per_hour"]
    assert "reset_at" in body and "hour" in body["reset_at"]
