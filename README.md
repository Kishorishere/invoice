# invoice.ai — AI-powered invoice data extraction

> Drop an invoice, we'll do the squinting.

A production-shaped take on the "extract an invoice to JSON" task — a FastAPI backend wrapped around Google Gemini, a soft-and-friendly React + Tailwind frontend, per-user scan history, arithmetic validation, due-date tracking, and exports in the formats real B2B accounting pipelines actually consume: JSON, CSV, UBL 2.1 XML, and Factur-X / ZUGFeRD XML.

Single container, single `fly deploy`.

![screenshot placeholder — replace with a real one after deploy](./docs/screenshot.png)

---

## What it does

| | |
|---|---|
| **Upload** | Drag-drop JPG, PNG, WEBP, or PDF (first page) &middot; up to 10 MB |
| **Extract** | Google Gemini (Flash family) &middot; model picker per user |
| **Validate** | Subtotal, VAT, total, dates &middot; each check has a green/red chip with the exact delta |
| **Store** | Per-user history in SQLite &middot; thumbnail + supplier + total + status |
| **Export** | JSON, CSV, UBL 2.1 XML, Factur-X XML &middot; one click per format |
| **Auth** | Email + password &middot; bcrypt + JWT in an HttpOnly, SameSite=Lax cookie &middot; CSRF double-submit on mutations |

Everything is yours — user accounts are isolated at the DB layer, uploaded images live in a user-owned folder.

---

## Why these invoice formats?

Real B2B invoicing in the EU (and specifically in Germany, where Deutschelink is based) does not exchange invoices as "whatever the vendor's API dumps." There are two open standards that matter:

- **UBL 2.1** — OASIS Universal Business Language; the ISO 19845 standard used by PEPPOL, government procurement across the EU, and most SaaS accounting integrations. XML.
- **Factur-X / ZUGFeRD** — the Franco-German hybrid: a PDF/A-3 with an embedded `factur-x.xml` payload that conforms to EN 16931. Required for B2G in Germany from 2025 onward.

Shipping both exports means the JSON isn't the end of the pipeline — a Deutschelink AP clerk can take the XML and feed it straight to DATEV or SAP. That is the point of the extraction, and the reason the exporter module isn't an afterthought.

---

## Tech stack

```
┌─────────────────────────────────────────────────────────────┐
│                     Single Docker image                     │
│                                                             │
│   React SPA (Vite + TS + Tailwind + shadcn + framer)       │
│                        ↓ /api/*                             │
│   FastAPI (uv-managed)                                      │
│     ├─ auth (bcrypt + PyJWT)                                │
│     ├─ extract: Gemini provider → validator                 │
│     ├─ invoices: list / get / delete / export               │
│     └─ exporters: JSON · CSV · UBL 2.1 · Factur-X           │
│                        ↓                                    │
│   SQLite + ./data/uploads   (Fly volume mounted to /app/data)│
└─────────────────────────────────────────────────────────────┘
```

- **Backend**: Python 3.12, FastAPI, SQLModel, pydantic-settings, PyJWT, bcrypt, google-genai, pypdfium2, lxml
- **Frontend**: React 18, Vite, TypeScript (strict), Tailwind, shadcn primitives, framer-motion, sonner, lucide
- **Package management**: `uv` on the backend, `npm` on the frontend
- **Testing**: pytest (backend), tsc --noEmit (frontend typecheck)
- **CI/CD**: GitHub Actions — lint + test + Docker build + Fly deploy
- **Deploy**: Fly.io — single machine, 512 MB, Frankfurt region, persistent volume

---

## Run it locally

Requires **Python 3.12**, **Node 20+**, and [**uv**](https://docs.astral.sh/uv/).

### 1. Clone + env

```bash
git clone <this-repo>
cd deutscheland-task
cp .env.example .env
# Open .env and set GEMINI_API_KEY
# Also set JWT_SECRET to a random string (python -c "import secrets; print(secrets.token_urlsafe(48))")
```

### 2. Backend

```bash
cd backend
uv sync
uv run python dev.py
# → http://localhost:3004  (API + /docs)
```

### 3. Frontend (separate terminal)

```bash
cd frontend
npm install
npm run dev
# → http://localhost:3005  (proxies /api → localhost:3004)
```

### 4. Try it

Open http://localhost:3005 and sign in with the admin credentials from your `.env` (`ADMIN_EMAIL` / `ADMIN_PASSWORD`). The admin is created on first server start. Click **Try the sample** on the dashboard — that uses the included `invoice.png`. Open **Users** in the nav to invite teammates with their own permanent passwords.

### Run tests

```bash
cd backend
uv run pytest
```

---

## Run the whole thing in one container

```bash
# Build + run with docker-compose
GEMINI_API_KEY=... JWT_SECRET=... docker compose up --build
# → http://localhost:3004
```

This is the exact same image that ships to Fly.io.

---

## Deploy to Fly.io

One-time setup:

```bash
# Install flyctl, then:
fly auth login
fly launch --no-deploy        # pick an app name; edit fly.toml if needed
fly volumes create invoice_data --size 1 --region fra
fly secrets set \
  GEMINI_API_KEY=... \
  JWT_SECRET=$(python -c "import secrets; print(secrets.token_urlsafe(48))")
```

Every deploy after that:

```bash
fly deploy
```

CI deploys automatically on push to `main` if you add a `FLY_API_TOKEN` repo secret (`fly tokens create deploy`).

---

## Test login for reviewers

Reviewers can create their own account in 10 seconds. If you want a shared test login, create one after deploy:

```
Email:    reviewer@example.com
Password: review-this-app
```

The server bootstraps an admin on every start from `ADMIN_EMAIL` and `ADMIN_PASSWORD` (set in `.env` locally, or via `fly secrets set` in prod). Sign in as that admin, then use the Users page to invite reviewers with their own email + password — the app is invite-only, no self-serve registration.

---

## Project layout

```
.
├── backend/
│   ├── pyproject.toml              # uv-managed
│   ├── app/
│   │   ├── main.py                 # FastAPI app, static SPA mount, CORS
│   │   ├── config.py               # pydantic-settings
│   │   ├── db.py, models.py        # SQLModel engine + tables
│   │   ├── schemas.py              # Pydantic request/response + domain types
│   │   ├── auth.py, deps.py        # JWT, bcrypt, current_user
│   │   ├── routers/
│   │   │   ├── auth.py             # /auth/login|me|logout (invite-only; no register)
│   │   │   ├── admin.py            # /admin/users CRUD + reset-password (admin-only + CSRF)
│   │   │   ├── extract.py          # /extract, /providers
│   │   │   └── invoices.py         # list/get/delete/export
│   │   └── services/
│   │       ├── providers/
│   │       │   ├── base.py         # BaseProvider ABC
│   │       │   ├── gemini.py       # google-genai, response_schema
│   │       │   ├── factory.py      # get_provider(name)
│   │       │   └── prompt.py       # system prompt + JSON schema
│   │       ├── validator.py        # subtotal / VAT / total / dates
│   │       ├── exporters.py        # JSON / CSV / UBL / Factur-X
│   │       └── pdf.py              # PDF page-1 → PNG
│   └── tests/                      # pytest (no live API calls)
├── frontend/
│   ├── package.json
│   ├── vite.config.ts              # /api proxy to localhost:3004 in dev
│   ├── tailwind.config.js          # soft warm palette + coral accent
│   └── src/
│       ├── main.tsx, App.tsx
│       ├── index.css               # CSS vars for light + dark
│       ├── lib/{api,auth,types,utils}.ts
│       ├── components/
│       │   ├── ui/                 # shadcn primitives
│       │   ├── Nav.tsx
│       │   ├── Uploader.tsx        # drag-drop + provider toggle
│       │   ├── ExtractionStepper.tsx # animated loading
│       │   ├── CopyField.tsx       # one-click copy on every value
│       │   ├── ValidationBadge.tsx # per-check green/red chip
│       │   ├── DueBadge.tsx        # overdue / due soon / later
│       │   └── InvoiceResults.tsx  # 2-col image + fields layout
│       └── pages/{Login,Dashboard,History,Detail,Users}.tsx
├── Dockerfile                      # multi-stage (frontend → backend → runtime)
├── docker-compose.yml              # local one-command run
├── fly.toml                        # Fly.io deploy config
├── .github/workflows/ci.yml        # lint + test + build + deploy
├── invoice.png                     # sample invoice from the task email
└── README.md
```

---

## Trade-offs and notes

- **SQLite, not Postgres.** This is a single-tenant demo. One container, one volume, zero config. Swap `DATABASE_URL` to Postgres when a second machine joins the party.
- **JWT in HttpOnly cookie + CSRF double-submit token.** Was briefly bearer-in-localStorage during the first build — switched after realising `<img>` tags and `<a href>` downloads can't attach `Authorization` headers, and bearer tokens in JS-reachable storage are an XSS exfiltration risk. Cookies auto-attach to every same-origin request; CSRF double-submit (non-HttpOnly csrf cookie echoed in `X-CSRF-Token` header) blocks cross-site forgery because an attacker's page can't read our cookie. Set `COOKIE_SECURE=true` on Fly deploy so the session cookie is HTTPS-only.
- **No OAuth / no email verification.** The task said "simple auth."
- **PDF support is first page only.** Most invoices are one page; multi-page extraction is a separate problem (page-by-page merge, item deduplication).
- **Gemini only.** Groq's Llama models are text/chat — they don't have a production vision endpoint for invoice-image extraction, so the provider toggle was removed. The UI keeps a Gemini model picker (Flash, Flash-Lite, etc.) so operators can trade cost for accuracy without a redeploy.
- **Exports write to disk ephemerally only during request handling** — we store the normalized JSON, and regenerate every export on demand.

---

## License

MIT. Make something nice.
