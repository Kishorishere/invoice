# syntax=docker/dockerfile:1.7

# ---------- Stage 1: build the frontend ----------
FROM node:20-alpine AS frontend
WORKDIR /app/frontend
COPY frontend/package.json ./
# Lockfile is optional on first build; use `npm install` if absent, `npm ci` otherwise.
COPY frontend/package-lock.json* ./
RUN if [ -f package-lock.json ]; then npm ci; else npm install; fi
COPY frontend/ ./
RUN npm run build


# ---------- Stage 2: install backend deps with uv ----------
FROM python:3.12-slim-bookworm AS backend-deps
COPY --from=ghcr.io/astral-sh/uv:0.5.4 /uv /uvx /bin/
ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PROJECT_ENVIRONMENT=/app/.venv

WORKDIR /app
COPY backend/pyproject.toml backend/uv.lock* ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --no-install-project --no-dev --frozen 2>/dev/null \
    || uv sync --no-install-project --no-dev


# ---------- Stage 3: runtime ----------
FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH" \
    STATIC_DIR=/app/static \
    UPLOAD_DIR=/app/data/uploads \
    DATABASE_URL=sqlite:////app/data/app.db

# System deps — pypdfium2 ships its own binary, but keep ca-certificates for TLS.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Python environment
COPY --from=backend-deps /app/.venv /app/.venv

# Backend source + Alembic migrations (required by init_db on startup)
COPY backend/app /app/app
COPY backend/alembic /app/alembic
COPY backend/alembic.ini /app/alembic.ini
COPY backend/pyproject.toml /app/pyproject.toml

# Built frontend
COPY --from=frontend /app/frontend/dist /app/static

# Persistent data dir (mounted as a volume on Fly.io)
RUN mkdir -p /app/data/uploads

EXPOSE 3004

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:3004/api/health').status==200 else 1)" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "3004", \
     "--proxy-headers", "--forwarded-allow-ips=*"]
