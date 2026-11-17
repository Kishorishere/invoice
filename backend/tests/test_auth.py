from __future__ import annotations

from tests.conftest import ADMIN_EMAIL, ADMIN_PASSWORD, login, login_as_admin


def test_admin_is_bootstrapped(client) -> None:
    # The admin user is created on init_db via ADMIN_EMAIL / ADMIN_PASSWORD env.
    headers = login_as_admin(client)
    assert "X-CSRF-Token" in headers
    r = client.get("/api/auth/me")
    assert r.status_code == 200
    body = r.json()
    assert body["email"] == ADMIN_EMAIL
    assert body["role"] == "admin"


def test_no_self_serve_register(client) -> None:
    # The register endpoint was removed — invite-only now.
    r = client.post(
        "/api/auth/register",
        json={"email": "x@x.com", "password": "password123"},
    )
    assert r.status_code == 404


def test_wrong_password_rejected(client) -> None:
    r = client.post(
        "/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": "definitely-not-it"},
    )
    assert r.status_code == 401


def test_me_requires_cookie(client) -> None:
    assert client.get("/api/auth/me").status_code == 401


def test_logout_clears_cookies(client) -> None:
    login_as_admin(client)
    assert client.get("/api/auth/me").status_code == 200
    assert client.post("/api/auth/logout").status_code == 204
    assert client.get("/api/auth/me").status_code == 401


def test_csrf_required_for_delete(client) -> None:
    login_as_admin(client)
    # No X-CSRF-Token header → 403, even before the DB lookup runs.
    r = client.delete("/api/invoices/does-not-exist")
    assert r.status_code == 403
    assert "csrf" in r.json()["detail"].lower()


def test_csrf_accepted_when_header_matches(client) -> None:
    headers = login_as_admin(client)
    r = client.delete("/api/invoices/does-not-exist", headers=headers)
    assert r.status_code == 404


def test_security_headers_present(client) -> None:
    r = client.get("/api/health")
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert r.headers["X-Frame-Options"] == "DENY"
    assert "Referrer-Policy" in r.headers


# ---------- Admin user management ----------


def test_admin_creates_user_and_user_can_login(client) -> None:
    headers = login_as_admin(client)
    r = client.post(
        "/api/admin/users",
        json={"email": "newbie@x.com", "password": "newbie-pw-1234", "role": "user"},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    assert r.json()["email"] == "newbie@x.com"
    assert r.json()["role"] == "user"

    # Admin logs out; the newbie logs in.
    client.post("/api/auth/logout")
    login(client, "newbie@x.com", "newbie-pw-1234")
    me = client.get("/api/auth/me").json()
    assert me["email"] == "newbie@x.com"
    assert me["role"] == "user"


def test_non_admin_cannot_list_users(client) -> None:
    # Create a regular user as admin, then switch to them.
    headers = login_as_admin(client)
    client.post(
        "/api/admin/users",
        json={"email": "u1@x.com", "password": "u1-password-123", "role": "user"},
        headers=headers,
    )
    client.post("/api/auth/logout")
    login(client, "u1@x.com", "u1-password-123")

    r = client.get("/api/admin/users")
    assert r.status_code == 403


def test_admin_cannot_demote_self(client) -> None:
    headers = login_as_admin(client)
    me = client.get("/api/auth/me").json()
    r = client.patch(
        f"/api/admin/users/{me['id']}",
        json={"role": "user"},
        headers=headers,
    )
    assert r.status_code == 400


def test_admin_cannot_delete_self(client) -> None:
    headers = login_as_admin(client)
    me = client.get("/api/auth/me").json()
    r = client.delete(f"/api/admin/users/{me['id']}", headers=headers)
    assert r.status_code == 400


def test_admin_resets_user_password(client) -> None:
    headers = login_as_admin(client)
    created = client.post(
        "/api/admin/users",
        json={"email": "reset-me@x.com", "password": "old-password-1234", "role": "user"},
        headers=headers,
    ).json()
    r = client.post(
        f"/api/admin/users/{created['id']}/reset-password",
        json={"password": "brand-new-pass-99"},
        headers=headers,
    )
    assert r.status_code == 204

    client.post("/api/auth/logout")
    # Old password no longer works.
    assert (
        client.post(
            "/api/auth/login",
            json={"email": "reset-me@x.com", "password": "old-password-1234"},
        ).status_code
        == 401
    )
    # New one does.
    login(client, "reset-me@x.com", "brand-new-pass-99")
