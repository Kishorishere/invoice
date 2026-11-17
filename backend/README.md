# Backend

FastAPI + SQLModel + uv. See the repo root README for the full picture.

```bash
uv sync
cp ../.env.example .env
uv run uvicorn app.main:app --reload
```

Tests:

```bash
uv run pytest
```
