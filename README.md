# AI Email Intelligence & Smart Reply System — Backend

FastAPI + SQLAlchemy 2 + PostgreSQL backend for the AI-powered email management
platform described in [`README_AI_Email_Intelligence.md`](README_AI_Email_Intelligence.md).
Implementation notes and the full route/contract reference live in
[`docs/API_CONTRACT.md`](docs/API_CONTRACT.md).

## What it provides

- **Auth & RBAC** — signup/login, rotating refresh tokens, session revocation
  (access tokens are bound to their session and die with it), email verification,
  password reset/change, `user` vs `admin` roles, Argon2id hashing, per-minute rate
  limiting.
- **Email ingestion** — manual creation, `.eml` upload, CSV/JSON dataset import with
  per-row validation, content fingerprint dedupe, thread detection, soft delete/archive,
  CSV export, full-text-ish filtering, sorting and pagination.
- **AI analysis pipeline** — category, intent, priority, sentiment, short/detailed
  summaries, key points, entity extraction (customer, company, order, invoice, amount,
  dates, deadlines, meetings, locations, requested action), action items with normalized
  deadlines, urgency/reply/action flags. Provider adapter (`mock` | `gemini`) with
  schema validation, retries, usage/error audit rows.
- **Smart replies** — tone-aware, thread-context drafts with edit/regenerate/approve/reject
  lifecycle. Nothing is ever sent to a recipient.
- **Inbox assistant** — natural-language questions answered over the user's *own* emails,
  with backend-validated filters, citations and a deterministic fallback.
- **Dashboard & analytics** — counters, activity time series, category/sentiment/priority
  distributions, recent activity, deadlines, date-range analytics.
- **Admin** — system stats, user management, AI usage/error logs, audit trail, category
  catalogue, runtime configuration.
- **Notifications** — in-app notifications for urgent/complaint/reply-required/deadline
  events plus per-user preferences.

## Requirements

- Python **3.11+** (developed and verified on 3.14)
- PostgreSQL **14+** (verified on 18.6)
- ~63 REST routes under `/api/v1`; OpenAPI schema served at `/openapi.json`

## Setup

```powershell
# 1. virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1          # macOS/Linux: source .venv/bin/activate

# 2. dependencies
pip install -r requirements.txt

# 3. database (PostgreSQL)
psql -U postgres -c "CREATE ROLE email_intel LOGIN PASSWORD 'email_intel_dev_pw';"
psql -U postgres -c "CREATE DATABASE email_intelligence OWNER email_intel;"
psql -U postgres -d email_intelligence -c "GRANT ALL ON SCHEMA public TO email_intel;"
```

Test database (optional, used by `RUNTIME_TEST_DB_URL`):

```powershell
psql -U postgres -c "CREATE DATABASE email_intelligence_test OWNER email_intel;"
```

## Configuration

```powershell
Copy-Item .env.example .env
python -c "import secrets;print(secrets.token_urlsafe(64))"   # paste into SECRET_KEY
```

`.env` is gitignored; only `.env.example` (placeholders) is committed. Key variables:

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | `postgresql+psycopg://…/email_intelligence` | SQLAlchemy URL |
| `SECRET_KEY` | *change me* | HS256 signing key for JWTs |
| `AI_PROVIDER` | `mock` | `mock` (no credentials) or `gemini` |
| `AI_API_KEY` | *(empty)* | Required only for `gemini` |
| `DEV_MODE_ENABLE_TOKEN_LINKS` | `true` | Returns verify/reset links in the response instead of emailing them. Must be `false` in production. |
| `RATE_LIMIT_ENABLED` | `true` | In-memory per-minute limits |
| `TEST_DATABASE_URL` | `sqlite+pysqlite:///.test_tmp/test.db` | Used by `pytest` |
| `APP_ENV` / `DEBUG` | `development` / `true` | `docs`/`redoc` are hidden when `APP_ENV=production` |

## Database migrations

```powershell
python -m alembic upgrade head        # apply
python -m alembic current             # show revision
python -m alembic check               # no drift between models and migrations
python -m alembic revision --autogenerate -m "message"   # after changing models
```

## Run

```powershell
uvicorn app.main:app --reload --port 8000
```

- Swagger UI: <http://localhost:8000/docs>
- Health: `GET /api/v1/health` · `GET /api/v1/health/ready`

## Seed a demo inbox

```powershell
python scripts\seed_demo.py
```

Idempotent: creates/updates `demo@example.com` / `DemoPassw0rd!`, seeds the default
category catalogue, imports the 63-message synthetic dataset from
`data/emails_seed.csv` (deduped on re-run) and runs AI analysis on anything still
pending. Useful flags: `--reset` (wipe the demo inbox first), `--skip-ai`,
`--email`, `--password`, `--create-schema` (bypass Alembic).

## Tests

```powershell
python -m pytest                      # 100 tests, SQLite (fast, no services needed)
python -m pytest -m postgres          # only PostgreSQL-dependent tests
python -m pytest tests/test_emails.py -k import
python -m ruff check .                # lint (must be clean)
```

To run the whole suite against PostgreSQL instead of SQLite:

```powershell
$env:RUNTIME_TEST_DB_URL = 'postgresql+psycopg://email_intel:email_intel_dev_pw@127.0.0.1:5432/email_intelligence_test'
python -m pytest                      # 100 passed
```

The suite pins `DATABASE_URL`, `AI_PROVIDER=mock`, `RATE_LIMIT_ENABLED=false` and
`DEBUG=true` at import time, so tests never touch your dev database or an AI vendor.

## Project layout

```
app/
  api/v1/        route handlers (auth, emails, replies, actions, notifications,
                 assistant, dashboard, admin, health) + DI dependencies
  core/          config, enums, errors, logging, security, rate limiting, utils
  db/            engine/session factory, declarative base
  models/        19 SQLAlchemy models (users, emails, analysis, entities, replies,
                 actions, notifications, assistant, audit, AI usage/errors, …)
  schemas/       Pydantic request/response models
  services/      business logic + services/ai/ (provider adapter, prompts,
                 schema models, analysis/reply pipeline, mock + gemini providers)
alembic/         migrations (initial schema: 19 tables)
scripts/         seed_demo.py
data/            emails_seed.csv (synthetic dataset)
tests/           100 tests across 8 files + conftest fixtures
docs/            API_CONTRACT.md
```

## Design notes

- Response timestamps are always UTC (`…Z`); PostgreSQL sessions are pinned to
  `TimeZone=UTC`.
- `category`, `priority` and `sentiment` live only on `email_analysis` — list/detail
  responses join them rather than duplicating columns.
- "Urgent" has one definition everywhere: `priority IN (high, critical) OR sentiment = 'urgent'`.
- Missing row ⇒ `404` (never `403`) so foreign ids cannot be probed.
- Errors always use `{ "error": { code, message, details?, request_id } }`; list
  endpoints always use the `{ items, total, page, page_size, pages }` envelope.
- Every AI output is schema-validated before it is persisted; failures are recorded in
  `ai_error_logs` and never written as partial analyses.
