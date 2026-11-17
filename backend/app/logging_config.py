"""Structured JSON logging + per-request access log.

Stdlib-only — no extra dependency, no hidden magic. Every log line is one JSON
object on stdout. The request-id context var (set by RequestIdMiddleware) is
threaded through so a single request's log lines share a correlation key.
"""

from __future__ import annotations

import json
import logging
import sys
import time
from datetime import UTC, datetime
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.security import request_id_var


class JsonFormatter(logging.Formatter):
    """One JSON object per log record; stable key order; UTC ISO timestamps."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "request_id": request_id_var.get(),
        }
        # Merge any extras the caller attached via logger.info(..., extra={...}).
        for key, value in record.__dict__.items():
            if key in _RESERVED or key in payload:
                continue
            try:
                json.dumps(value)  # only keep JSON-serializable extras
                payload[key] = value
            except (TypeError, ValueError):
                payload[key] = repr(value)

        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)

        return json.dumps(payload, default=str)


_RESERVED = {
    "args",
    "asctime",
    "created",
    "exc_info",
    "exc_text",
    "filename",
    "funcName",
    "levelname",
    "levelno",
    "lineno",
    "message",
    "module",
    "msecs",
    "msg",
    "name",
    "pathname",
    "process",
    "processName",
    "relativeCreated",
    "stack_info",
    "thread",
    "threadName",
    "taskName",
}


def configure_logging(level: str = "INFO") -> None:
    """Replace the root handler with our JSON formatter. Silence uvicorn's
    access log — our middleware emits one per request with richer fields."""
    root = logging.getLogger()
    for existing in list(root.handlers):
        root.removeHandler(existing)

    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setFormatter(JsonFormatter())
    root.addHandler(handler)
    root.setLevel(level)

    # Uvicorn configures its own loggers on startup. Reset their handlers so
    # everything flows through ours.
    for noisy in ("uvicorn", "uvicorn.error", "uvicorn.access", "sqlalchemy.engine"):
        lg = logging.getLogger(noisy)
        lg.handlers.clear()
        lg.propagate = True
    # Silence the raw access log — we emit a richer version from AccessLogMiddleware.
    logging.getLogger("uvicorn.access").disabled = True


class AccessLogMiddleware(BaseHTTPMiddleware):
    """Emit one structured log line per request with timing + status."""

    _logger = logging.getLogger("app.access")

    async def dispatch(self, request: Request, call_next) -> Response:
        start = time.perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        finally:
            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            # user_id is cheap to read from the cookie but we avoid decoding
            # the JWT here to keep the access log fast; auth-router logs handle
            # actor attribution for login events.
            self._logger.info(
                "request",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "status": status_code,
                    "duration_ms": duration_ms,
                    "client": request.client.host if request.client else None,
                },
            )


__all__ = ["AccessLogMiddleware", "JsonFormatter", "configure_logging"]
