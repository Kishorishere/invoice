"""Admin-only: user management (list / create / update / reset password / delete)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import func
from sqlmodel import select

from app.auth import hash_password
from app.config import get_settings
from app.deps import CsrfProtected, CurrentAdmin, DbSession
from app.models import Invoice, User
from app.rate_limit import limiter
from app.schemas import (
    AdminCreateUserRequest,
    AdminResetPasswordRequest,
    AdminUpdateUserRequest,
    AdminUserRow,
    UserPublic,
)

router = APIRouter(prefix="/admin/users", tags=["admin"])

_settings = get_settings()


@router.get("", response_model=list[AdminUserRow])
@limiter.limit(_settings.rate_limit_admin_read)
def list_users(
    request: Request, admin: CurrentAdmin, session: DbSession
) -> list[AdminUserRow]:
    # One SQL query per row count would be fine for small user bases; a
    # grouped count keeps us honest as it grows.
    counts: dict[str, int] = dict(
        session.exec(
            select(Invoice.user_id, func.count(Invoice.id)).group_by(Invoice.user_id)
        ).all()
    )
    users = session.exec(select(User).order_by(User.created_at.desc())).all()
    return [
        AdminUserRow(
            id=u.id,
            email=u.email,
            role=u.role,  # type: ignore[arg-type]
            created_at=u.created_at,
            invoice_count=counts.get(u.id, 0),
        )
        for u in users
    ]


@router.post(
    "",
    response_model=UserPublic,
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit(_settings.rate_limit_admin_write)
def create_user(
    request: Request,
    body: AdminCreateUserRequest,
    _csrf: CsrfProtected,
    admin: CurrentAdmin,
    session: DbSession,
) -> UserPublic:
    email = body.email.lower()
    if session.exec(select(User).where(User.email == email)).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with that email already exists.")

    user = User(
        email=email,
        hashed_password=hash_password(body.password),
        role=body.role,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return UserPublic(id=user.id, email=user.email, role=user.role, created_at=user.created_at)  # type: ignore[arg-type]


@router.patch("/{user_id}", response_model=UserPublic)
@limiter.limit(_settings.rate_limit_admin_write)
def update_user(
    request: Request,
    user_id: str,
    body: AdminUpdateUserRequest,
    _csrf: CsrfProtected,
    admin: CurrentAdmin,
    session: DbSession,
) -> UserPublic:
    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found.")

    if body.email is not None:
        new_email = body.email.lower()
        if new_email != user.email:
            clash = session.exec(select(User).where(User.email == new_email)).first()
            if clash and clash.id != user.id:
                raise HTTPException(status.HTTP_409_CONFLICT, "That email is already in use.")
            user.email = new_email

    if body.role is not None:
        if user.id == admin.id and body.role != "admin":
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "You can't demote yourself. Ask another admin.",
            )
        user.role = body.role

    session.add(user)
    session.commit()
    session.refresh(user)
    return UserPublic(id=user.id, email=user.email, role=user.role, created_at=user.created_at)  # type: ignore[arg-type]


@router.post("/{user_id}/reset-password", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit(_settings.rate_limit_admin_write)
def reset_password(
    request: Request,
    user_id: str,
    body: AdminResetPasswordRequest,
    _csrf: CsrfProtected,
    admin: CurrentAdmin,
    session: DbSession,
) -> None:
    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found.")
    user.hashed_password = hash_password(body.password)
    session.add(user)
    session.commit()


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit(_settings.rate_limit_admin_write)
def delete_user(
    request: Request,
    user_id: str,
    _csrf: CsrfProtected,
    admin: CurrentAdmin,
    session: DbSession,
) -> None:
    if user_id == admin.id:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "You can't delete your own account. Ask another admin.",
        )
    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found.")

    # Cascade: drop that user's invoices too (owned data).
    invoices = session.exec(select(Invoice).where(Invoice.user_id == user_id)).all()
    for inv in invoices:
        session.delete(inv)
    session.delete(user)
    session.commit()
