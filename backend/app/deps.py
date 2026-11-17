"""FastAPI dependencies."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, Request, status
from sqlmodel import Session

from app.auth import decode_token
from app.config import get_settings
from app.db import get_session
from app.models import User
from app.security import csrf_ok


def _client_ip(request: Request) -> str:
    """Return the real client IP when the app sits behind Fly's proxy."""
    fly_ip = request.headers.get("fly-client-ip")
    if fly_ip:
        return fly_ip.strip()
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        # XFF is a comma-separated chain; the leftmost entry is the originator.
        return fwd.split(",", 1)[0].strip()
    return request.client.host if request.client else "unknown"


def rate_key(request: Request) -> str:
    """slowapi key function: authenticated user id when the cookie decodes,
    else the real client IP. Keeps per-user buckets when we know who's calling
    and per-IP buckets at the login / anonymous edge."""
    s = get_settings()
    token = request.cookies.get(s.session_cookie_name)
    if token:
        try:
            payload = decode_token(token)
            user_id = payload.get("sub")
            if isinstance(user_id, str) and user_id:
                return f"u:{user_id}"
        except jwt.InvalidTokenError:
            pass  # fall through to IP keying
    return f"ip:{_client_ip(request)}"


def db_session() -> Iterator[Session]:
    yield from get_session()


DbSession = Annotated[Session, Depends(db_session)]


def current_user(
    session: DbSession,
    request: Request,
) -> User:
    s = get_settings()
    token = request.cookies.get(s.session_cookie_name)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not signed in.",
        )
    try:
        payload = decode_token(token)
    except jwt.ExpiredSignatureError as err:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired. Please sign in again.",
        ) from err
    except jwt.InvalidTokenError as err:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid session.",
        ) from err

    user_id = payload.get("sub")
    if not isinstance(user_id, str):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Malformed session.")

    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Account no longer exists.")
    return user


CurrentUser = Annotated[User, Depends(current_user)]


def current_admin(user: CurrentUser) -> User:
    if user.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin access required.")
    return user


CurrentAdmin = Annotated[User, Depends(current_admin)]


def require_csrf(request: Request) -> None:
    """Enforce the double-submit CSRF token on mutating endpoints."""
    if not csrf_ok(request):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Missing or invalid CSRF token.",
        )


CsrfProtected = Annotated[None, Depends(require_csrf)]
