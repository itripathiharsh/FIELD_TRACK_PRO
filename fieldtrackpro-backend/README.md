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
