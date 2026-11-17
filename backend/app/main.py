"""FastAPI application entry point."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from slowapi.errors import RateLimitExceeded
from sqlalchemy import text
from sqlmodel import Session

from app import __version__
from app.config import get_settings
from app.db import engine, init_db
from app.logging_config import AccessLogMiddleware, configure_logging
from app.models import AppLimits
from app.rate_limit import limiter
from app.routers import admin, admin_limits, auth, extract, invoices, limits
from app.security import (
    MaxBodySizeMiddleware,
    RequestIdMiddleware,
    SecurityHeadersMiddleware,
)


settings = get_settings()
configure_logging()


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


def _rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    # slowapi's default formatter includes the bucket name; we keep that for
    # debuggability. Client code reads `Retry-After` for the delay.
    return JSONResponse(
        status_code=429,
        content={"detail": f"Too many requests ({exc.detail})."},
        headers={"Retry-After": str(getattr(exc, "retry_after", 60))},
    )


# `/docs` and OpenAPI only in non-production. cookie_secure=True implies HTTPS.
_docs_disabled = settings.cookie_secure
app = FastAPI(
    title="Invoice Extractor API",
    version=__version__,
    description="AI-powered invoice data extraction (Gemini).",
    lifespan=lifespan,
    docs_url=None if _docs_disabled else "/docs",
    redoc_url=None if _docs_disabled else "/redoc",
    openapi_url=None if _docs_disabled else "/openapi.json",
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_handler)

# --- Middleware order matters: outermost declared last. We want:
#  1. body-size guard (first to run, so oversized bodies short-circuit)
#  2. request-id (so every downstream log line has a correlation key)
#  3. access log (sees the final status)
#  4. security headers (set on every response)
#  5. CORS (must wrap the rest)
app.add_middleware(SecurityHeadersMiddleware, hsts=settings.cookie_secure)
app.add_middleware(AccessLogMiddleware)
app.add_middleware(RequestIdMiddleware)
app.add_middleware(
    MaxBodySizeMiddleware,
    max_bytes=settings.max_upload_mb * 1024 * 1024,
)

if settings.cors_origin_list:
    # NOTE: when using cookies, `allow_origins` must NOT be "*" and
    # `allow_credentials` must be True. We also expose the CSRF header so
    # browsers permit the custom header on cross-origin preflight.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=[
            "Content-Type",
            "X-Request-ID",
            settings.csrf_header_name,
        ],
        expose_headers=["X-Request-ID"],
    )


@app.get("/api/health", tags=["meta"])
def health() -> JSONResponse:
    """Deep health check: DB reachable, upload dir writable, limits seeded.

    Returns 503 when any check fails. Fly's HTTP healthcheck already hits
    this URL.
    """
    checks: dict[str, object] = {
        "ok": True,
        "version": __version__,
        "providers": settings.available_providers,
    }

    # DB round-trip + limits row seed check.
    try:
        with Session(engine) as session:
            session.exec(text("SELECT 1"))  # type: ignore[arg-type]
            checks["db"] = "ok"
            checks["limits_row"] = (
                "present" if session.get(AppLimits, 1) is not None else "missing"
            )
    except Exception as err:  # noqa: BLE001 — health checks must be defensive
        checks["db"] = f"error: {err!r}"
        checks["limits_row"] = "unknown"
        checks["ok"] = False

    # Upload directory writable.
    try:
        upload_dir = Path(settings.upload_dir)
        upload_dir.mkdir(parents=True, exist_ok=True)
        probe = upload_dir / ".healthcheck"
        probe.write_bytes(b"ok")
        probe.unlink(missing_ok=True)
        checks["upload_dir_writable"] = True
    except Exception as err:  # noqa: BLE001
        checks["upload_dir_writable"] = False
        checks["upload_error"] = repr(err)
        checks["ok"] = False

    if checks["limits_row"] == "missing":
        checks["ok"] = False

    return JSONResponse(checks, status_code=200 if checks["ok"] else 503)


# Exempt /api/health from the default rate limiter so Fly's probe never trips.
limiter.exempt(health)

# Mount API routers under /api so the SPA can own the root.
app.include_router(auth.router, prefix="/api")
app.include_router(extract.router, prefix="/api")
app.include_router(invoices.router, prefix="/api")
app.include_router(limits.router, prefix="/api")
app.include_router(admin.router, prefix="/api")
app.include_router(admin_limits.router, prefix="/api")


# ---- Static SPA (only when the built frontend is present) ----
_static_dir = Path(settings.static_dir)
if _static_dir.is_dir() and (_static_dir / "index.html").exists():
    # Serve assets at their built paths (e.g. /assets/*).
    app.mount("/assets", StaticFiles(directory=_static_dir / "assets"), name="assets")

    # SPA fallback: any non-API path returns index.html so client-side routing works.
    @app.get("/{full_path:path}", include_in_schema=False, response_model=None)
    async def spa_fallback(full_path: str, request: Request) -> FileResponse | JSONResponse:
        if full_path.startswith("api/"):
            return JSONResponse({"detail": "Not Found"}, status_code=404)
        # A real file in the static dir (favicon.ico, robots.txt, ...)
        candidate = _static_dir / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(_static_dir / "index.html")
