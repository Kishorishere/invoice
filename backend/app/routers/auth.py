"""Login / me / logout — invite-only (no self-serve register).

New accounts are created by admins via /api/admin/users. The admin role is
bootstrapped on server startup from ADMIN_EMAIL / ADMIN_PASSWORD (see db.py).
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request, Response, status
from sqlmodel import select

from app.auth import create_access_token, verify_password
from app.config import get_settings
from app.deps import CurrentUser, DbSession
from app.models import User
from app.rate_limit import limiter
from app.schemas import AuthResponse, LoginRequest, UserPublic
from app.security import clear_auth_cookies, generate_csrf_token, set_auth_cookies

log = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


_settings = get_settings()


@router.post("/login", response_model=AuthResponse)
@limiter.limit(_settings.rate_limit_login)
def login(
    request: Request,
    body: LoginRequest,
    session: DbSession,
    response: Response,
) -> AuthResponse:
    email = body.email.lower()
    user = session.exec(select(User).where(User.email == email)).first()
    # verify_password runs even when user is None so request timing does not
    # leak whether the email exists.
    valid = user is not None and verify_password(body.password, user.hashed_password)
    if user is None or not valid:
        log.info("login_failed", extra={"email": email})
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect email or password.")

    set_auth_cookies(
        response,
        access_token=create_access_token(user.id),
        csrf_token=generate_csrf_token(),
    )
    log.info("login_ok", extra={"user_id": user.id, "email": email})
    return AuthResponse(
        user=UserPublic(id=user.id, email=user.email, role=user.role, created_at=user.created_at)  # type: ignore[arg-type]
    )


@router.get("/me", response_model=UserPublic)
@limiter.limit(_settings.rate_limit_auth_other)
def me(request: Request, user: CurrentUser) -> UserPublic:
    return UserPublic(id=user.id, email=user.email, role=user.role, created_at=user.created_at)  # type: ignore[arg-type]


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit(_settings.rate_limit_auth_other)
def logout(request: Request, response: Response) -> None:
    # No CSRF check on logout: the worst a CSRF attack can do is sign the
    # user out, which is low-impact. Keeps the "my session is dead" button
    # reliable even if the csrf cookie was lost.
    clear_auth_cookies(response)
