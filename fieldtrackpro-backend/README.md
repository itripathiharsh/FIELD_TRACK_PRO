# FieldTrack Pro Backend (`fieldtrackpro-backend`)

Python 3.11 / FastAPI backend service for FieldTrack Pro.

## Stack

| Concern | Dependency |
|---|---|
| API Framework | FastAPI 0.115+ |
| Server | Uvicorn (standard) |
| Configuration | Pydantic Settings v2 |
| Database Driver | asyncpg |
| ORM | SQLAlchemy 2.0 (async) |
| Migrations | Alembic |

## Prerequisites

- Python 3.11+
- Poetry
- PostgreSQL 17

## Setup

```bash
# 1. Install dependencies
poetry install

# 2. Copy environment config
cp .env.example .env
# Then edit .env and set your DATABASE_URL

# 3. Run migrations
poetry run alembic upgrade head

# 4. Start development server
poetry run uvicorn app.main:app --reload --port 8000
```

## API

| URL | Purpose |
|---|---|
| `GET /health` | Infrastructure health probe |
| `GET /api/v1/health` | Application health check |
| `GET /api/v1/health/db` | Database connectivity check |
| `GET /docs` | Swagger UI (OpenAPI) |
| `GET /redoc` | ReDoc (OpenAPI) |

## Tests

```bash
poetry run pytest -v
```

## Authentication & hardening notes

- Roles: `ADMIN` and `EMPLOYEE` only. No default users are created; make the first admin with `poetry run python scripts/bootstrap_admin.py` (env `ADMIN_BOOTSTRAP_EMAIL` / `ADMIN_BOOTSTRAP_PASSWORD`).
- Forced password change: `ENFORCE_PASSWORD_CHANGE=true` -> flagged staff receive `403 PASSWORD_CHANGE_REQUIRED` except on `/auth/me`, `/auth/logout`, `/auth/refresh`, `/auth/change-password`, `PATCH /users/me/password` (returns a fresh token pair). Login/refresh/`/auth/me` expose `must_change_password`.
- `DELETE /api/v1/auth/me` needs `{"password": "..."}` (optional `reason`) for all roles.
- Passwords: 8-128 characters and at most 72 bytes (`422 PASSWORD_TOO_LONG`).
- Per-IP rate limits use `app/core/client_ip.py` (`TRUSTED_PROXY_HOPS`, default 1); run uvicorn with `--no-proxy-headers`.
- Upload/body limits: `MAX_REQUEST_BODY_BYTES`, per-endpoint chunked caps (`413 FILE_TOO_LARGE`).
- SMTP: 465 implicit TLS, 587/2525 STARTTLS, no clear-text credentials (`SMTP_ALLOW_INSECURE` is dev-only).
- Storage: see `STORAGE_MIGRATION.md`. Outlet proofs: `OUTLET_PROOF_*` settings.
- Payments: submitted -> verified by an admin -> Tally write-back job -> posted (acknowledged by the Tally Sync Agent).

## Database role grants

Migrations never grant rights to the runtime role. After `alembic upgrade head`, run (as the schema owner, by hand):

```bash
psql "<owner connection string>" -v owner_role=<migrating role> -f scripts/grant_runtime_role.sql
```

It is idempotent: CRUD on all tables and sequences for `fieldtrack_app`, `geo_verification_logs` stays insert-only, and default privileges cover future tables created by the owner role. It is never executed by the app, Alembic or the tests.

## Operations

- **Single instance:** the in-process scheduler (missed visits, security-record purge) has no locking; run one API instance/worker, or move the scheduler to its own single instance before scaling out.
- **Scripts** under `scripts/` are dry-run by default; use `--execute` with `CONFIRM_PURGE_DATABASE=<database name>` (and `--i-understand-production` when `ENVIRONMENT=production`). They read passwords/URLs from the environment (`scripts/_script_env.py`).
- `CORS_ALLOWED_ORIGINS` accepts a comma-separated list or a JSON array.
