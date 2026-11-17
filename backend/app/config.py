"""Application settings loaded from environment / .env."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


DEFAULT_JWT_SECRET = "dev-only-change-me"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    gemini_api_key: str = Field(default="")

    gemini_model: str = Field(default="gemini-3.6-flash")

    jwt_secret: str = Field(default=DEFAULT_JWT_SECRET)
    jwt_ttl_hours: int = Field(default=72)
    jwt_algorithm: str = "HS256"

    # Cookie-based auth settings. `cookie_secure` MUST be True in production
    # (HTTPS). SameSite=Lax blocks cross-site form POSTs; Strict is too
    # strict for normal nav flows.
    cookie_secure: bool = Field(default=False)
    cookie_samesite: Literal["lax", "strict", "none"] = "lax"
    session_cookie_name: str = "ix_session"
    csrf_cookie_name: str = "ix_csrf"
    csrf_header_name: str = "X-CSRF-Token"

    database_url: str = Field(default="sqlite:///./data/app.db")

    cors_origins: str = Field(default="http://localhost:3005")

    upload_dir: str = Field(default="./data/uploads")
    max_upload_mb: int = Field(default=10)

    static_dir: str = Field(default="./static")

    # Admin bootstrap. If both are set and no user with this email exists,
    # a new admin is created on startup. If the user exists but isn't admin,
    # they are promoted. Leave empty to opt out.
    admin_email: str = Field(default="")
    admin_password: str = Field(default="")

    # ---- Rate limiting (slowapi). Human-readable strings per slowapi syntax. ----
    rate_limit_login: str = Field(default="5/minute;20/hour")
    rate_limit_auth_other: str = Field(default="60/minute")
    rate_limit_admin_write: str = Field(default="30/minute")
    rate_limit_admin_read: str = Field(default="60/minute")
    rate_limit_providers: str = Field(default="30/minute")
    rate_limit_invoices_read: str = Field(default="120/minute")
    rate_limit_invoices_write: str = Field(default="30/minute")
    rate_limit_limits: str = Field(default="60/minute")
    rate_limit_default: str = Field(default="120/minute")

    # ---- Provider call budgets ----
    gemini_timeout_s: float = Field(default=30.0)
    provider_retry_attempts: int = Field(default=2)

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def gemini_api_keys(self) -> list[str]:
        """Split GEMINI_API_KEY as CSV so operators can rotate across multiple
        keys. A single key is just a CSV of length 1 — backward compatible."""
        return [k.strip() for k in self.gemini_api_key.split(",") if k.strip()]

    @property
    def available_providers(self) -> list[str]:
        out: list[str] = []
        if self.gemini_api_keys:
            out.append("gemini")
        return out

    def ensure_dirs(self) -> None:
        Path(self.upload_dir).mkdir(parents=True, exist_ok=True)
        db_path = self._sqlite_file()
        if db_path is not None:
            db_path.parent.mkdir(parents=True, exist_ok=True)

    def _sqlite_file(self) -> Path | None:
        prefix = "sqlite:///"
        if self.database_url.startswith(prefix):
            return Path(self.database_url[len(prefix):])
        return None

    @model_validator(mode="after")
    def _guard_prod_secrets(self) -> "Settings":
        # In production (cookie_secure=True implies HTTPS deployment), refuse
        # to boot with the default or a weak JWT secret. Catches the "forgot
        # to set JWT_SECRET on Fly" class of mistake before any token is issued.
        if self.cookie_secure:
            if self.jwt_secret == DEFAULT_JWT_SECRET:
                raise ValueError(
                    "JWT_SECRET is still the default value in production "
                    "(cookie_secure=True). Set JWT_SECRET to a random string "
                    "of at least 32 characters."
                )
            if len(self.jwt_secret) < 32:
                raise ValueError(
                    f"JWT_SECRET is too short ({len(self.jwt_secret)} chars) "
                    f"for production. Use at least 32 characters."
                )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
