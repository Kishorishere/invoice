"""Cookie-based auth + CSRF double-submit helpers + security headers.

Why cookies instead of bearer tokens: HttpOnly cookies are sent by the
browser on every same-origin request, including <img src> and <a href>
downloads — which bearer-in-Authorization headers cannot be. Trade-off:
cookies are auto-sent on cross-site POSTs too, so we need CSRF defense.

CSRF strategy: double-submit token. On auth, we set two cookies:
  - `ix_session`  (HttpOnly, Secure, SameSite=Lax) — the JWT
  - `ix_csrf`     (NOT HttpOnly) — a random token, read by JS
On state-changing requests, the client echoes the csrf cookie value back
in an `X-CSRF-Token` header. The server compares them in constant time.
A cross-origin attacker cannot read `ix_csrf` from their page (same-origin
policy for scripts), so they can't forge the header.
"""

from __future__ import annotations

import secrets
import uuid
from contextvars import ContextVar

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.config import get_settings


# Per-request context — logging middleware reads this to tag log lines.
request_id_var: ContextVar[str] = ContextVar("request_id", default="-")


def generate_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def set_auth_cookies(response: Response, *, access_token: str, csrf_token: str) -> None:
    s = get_settings()
    max_age = s.jwt_ttl_hours * 3600

    response.set_cookie(
        key=s.session_cookie_name,
        value=access_token,
        max_age=max_age,
        httponly=True,
        secure=s.cookie_secure,
        samesite=s.cookie_samesite,
        path="/",
    )
    response.set_cookie(
        key=s.csrf_cookie_name,
        value=csrf_token,
        max_age=max_age,
        httponly=False,  # JS needs to read this to echo it back
        secure=s.cookie_secure,
        samesite=s.cookie_samesite,
        path="/",
    )


def clear_auth_cookies(response: Response) -> None:
    s = get_settings()
    for name in (s.session_cookie_name, s.csrf_cookie_name):
        response.delete_cookie(
            key=name,
            path="/",
            secure=s.cookie_secure,
            samesite=s.cookie_samesite,
        )


def csrf_ok(request: Request) -> bool:
    s = get_settings()
    cookie = request.cookies.get(s.csrf_cookie_name)
    header = request.headers.get(s.csrf_header_name)
    if not cookie or not header:
        return False
    return secrets.compare_digest(cookie, header)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Set conservative security headers on every response.

    - X-Content-Type-Options: nosniff → browsers must not MIME-sniff
    - X-Frame-Options: DENY → no framing (clickjacking defense)
    - Referrer-Policy: strict-origin-when-cross-origin → leak less on nav
    - Strict-Transport-Security → only sent when we're actually on HTTPS
    """

    def __init__(self, app: ASGIApp, *, hsts: bool = False) -> None:
        super().__init__(app)
        self._hsts = hsts

    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault(
            "Permissions-Policy",
            "camera=(), microphone=(), geolocation=(), payment=()",
        )
        if self._hsts:
            response.headers.setdefault(
                "Strict-Transport-Security",
                "max-age=63072000; includeSubDomains",
            )
        return response


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Attach a request ID to every request + response for log correlation.

    Honors a caller-supplied `X-Request-ID` (useful for client-side tracing
    through a load balancer) and generates one otherwise. Stored on
    `request.state.request_id` and in a ContextVar so loggers can pick it up
    without threading it through every call."""

    async def dispatch(self, request: Request, call_next):
        incoming = request.headers.get("x-request-id", "").strip()
        rid = incoming if incoming else uuid.uuid4().hex
        request.state.request_id = rid
        token = request_id_var.set(rid)
        try:
            response = await call_next(request)
        finally:
            request_id_var.reset(token)
        response.headers["X-Request-ID"] = rid
        return response


class MaxBodySizeMiddleware:
    """Reject oversized request bodies BEFORE they are buffered into memory.

    The upload endpoint has a post-read size check as a last line of defense,
    but by then the server has already allocated the full body. On a 512MB VM
    a few 500MB requests OOM the box. This middleware short-circuits via
    `Content-Length` when present, and wraps `receive()` to accumulate-then-
    reject on chunked uploads that lie about their size (or omit the header).
    """

    def __init__(self, app: ASGIApp, *, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Content-Length declared: refuse upfront without touching the body.
        headers = {k.decode().lower(): v.decode() for k, v in scope.get("headers", [])}
        declared = headers.get("content-length")
        if declared is not None:
            try:
                if int(declared) > self.max_bytes:
                    await self._reject(send)
                    return
            except ValueError:
                pass  # malformed header — let the framework handle it

        received = 0
        exceeded = False

        async def guarded_receive() -> Message:
            nonlocal received, exceeded
            message = await receive()
            if message["type"] == "http.request":
                body = message.get("body", b"") or b""
                received += len(body)
                if received > self.max_bytes:
                    exceeded = True
                    # Signal end-of-stream so the app finishes quickly. We'll
                    # override its response below.
                    return {"type": "http.request", "body": b"", "more_body": False}
            return message

        response_started = False

        async def guarded_send(message: Message) -> None:
            nonlocal response_started
            if exceeded:
                # Swallow the app's response once we've decided to reject.
                return
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        await self.app(scope, guarded_receive, guarded_send)
        if exceeded and not response_started:
            await self._reject(send)

    async def _reject(self, send: Send) -> None:
        settings = get_settings()
        body = (
            b'{"detail":"Request body exceeds the '
            + str(settings.max_upload_mb).encode()
            + b' MB limit."}'
        )
        await send(
            {
                "type": "http.response.start",
                "status": 413,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode()),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})
