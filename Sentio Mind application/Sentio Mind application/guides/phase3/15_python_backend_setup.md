# FieldTrack Pro — Python Backend Setup
### Phase 3.1 — Backend Development
### Replaces "Spring Boot Setup" — this is what an Antigravity prompt for "set up the backend project" should now produce

First actual build step. Concrete enough to run, not just planning prose.

---

## 1. Project Initialization

- **Python version**: 3.12 (latest stable, broad library support)
- **Dependency manager**: Poetry
- **Framework**: FastAPI
- **Project name**: `fieldtrackpro-backend`
- **Package layout**: `src`-less, single top-level `app/` package (see Folder Structure doc)

```bash
poetry new fieldtrackpro-backend --name app
cd fieldtrackpro-backend
poetry env use 3.12
```

---

## 2. Core Dependencies (`pyproject.toml`)

```toml
[tool.poetry]
name = "fieldtrackpro-backend"
version = "0.1.0"
description = "FieldTrack Pro backend API"
package-mode = false

[tool.poetry.dependencies]
python = "^3.12"

# Web framework
fastapi = "^0.115.0"
uvicorn = { extras = ["standard"], version = "^0.32.0" }

# Config
pydantic = "^2.9.0"
pydantic-settings = "^2.6.0"

# Database / ORM
sqlalchemy = "^2.0.36"
asyncpg = "^0.30.0"
geoalchemy2 = "^0.16.0"
alembic = "^1.14.0"

# Auth
python-jose = { extras = ["cryptography"], version = "^3.3.0" }
passlib = { extras = ["bcrypt"], version = "^1.7.4" }
python-multipart = "^0.0.12"      # required for form/file uploads in FastAPI

# File & media
minio = "^7.2.0"
pillow = "^11.0.0"
python-magic = "^0.4.27"

# Notifications
firebase-admin = "^6.5.0"

# Background jobs
apscheduler = "^3.10.4"

[tool.poetry.group.dev.dependencies]
pytest = "^8.3.0"
pytest-asyncio = "^0.24.0"
httpx = "^0.27.0"                  # async test client for FastAPI
testcontainers = { extras = ["postgres"], version = "^4.8.0" }
ruff = "^0.7.0"                    # lint + format
mypy = "^1.13.0"

[build-system]
requires = ["poetry-core"]
build-backend = "poetry.core.masonry.api"
```

**Note on `python-magic`**: on Linux containers this requires the system `libmagic1` package (added to the Dockerfile in the Deployment doc) — a common source of confusing `ImportError`s if the OS package is missing while the Python wheel installs fine locally on macOS/Windows where `libmagic` ships differently. Flagging it here so it isn't discovered the hard way mid-Phase-5 build.

---

## 3. `app/config.py` — Base Config

```python
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # App
    environment: str = "dev"
    api_v1_prefix: str = "/api/v1"

    # Database
    database_url: str  # e.g. postgresql+asyncpg://user:pass@localhost:5432/fieldtrackpro_dev

    # JWT
    jwt_secret: str                       # required, no default — fails startup if missing (see Section 7)
    jwt_access_token_expiry_minutes: int = 15
    jwt_refresh_token_expiry_days: int = 7

    # MinIO
    minio_endpoint: str
    minio_access_key: str
    minio_secret_key: str
    minio_bucket: str
    minio_secure: bool = False

    # CORS
    cors_allowed_origins: list[str] = []

    # Firebase
    firebase_credentials_path: str


settings = Settings()
```

This replaces the `application.yml` / `application-dev.yml` / `application-prod.yml` split — a single `Settings` class reads from `.env.dev` or `.env.prod` depending on which file is present/loaded at container start, and **fails to construct (and therefore fails app startup) if any required field like `jwt_secret` or `database_url` is missing**, preserving the original "no silent prod fallback" discipline exactly.

---

## 4. `app/database.py` — Async Engine + Session

```python
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from app.config import settings

engine = create_async_engine(settings.database_url, echo=(settings.environment == "dev"))
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session
```

`ddl-auto: validate`'s job (making sure the app never silently mutates schema on startup) is handled differently in this stack: **SQLAlchemy models never create/alter tables at runtime** — `Base.metadata.create_all()` is never called outside of test fixtures. Alembic is the only thing allowed to change schema, matching the original "Flyway owns schema" rule exactly.

---

## 5. `app/main.py` — App Entrypoint

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.api.v1 import auth, employees, customers, visits, media, reports, notifications, dashboard
from app.exceptions.handlers import register_exception_handlers
from app.jobs.missed_visit_scheduler import start_scheduler

app = FastAPI(title="FieldTrack Pro API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allowed_origins,   # locked list, never "*" in production — per Security Design
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_exception_handlers(app)

app.include_router(auth.router, prefix=f"{settings.api_v1_prefix}/auth", tags=["auth"])
app.include_router(employees.router, prefix=f"{settings.api_v1_prefix}/employees", tags=["employees"])
app.include_router(customers.router, prefix=f"{settings.api_v1_prefix}/customers", tags=["customers"])
app.include_router(visits.router, prefix=f"{settings.api_v1_prefix}/visits", tags=["visits"])
app.include_router(media.router, prefix=f"{settings.api_v1_prefix}", tags=["media"])
app.include_router(reports.router, prefix=f"{settings.api_v1_prefix}/reports", tags=["reports"])
app.include_router(notifications.router, prefix=f"{settings.api_v1_prefix}/notifications", tags=["notifications"])
app.include_router(dashboard.router, prefix=f"{settings.api_v1_prefix}/dashboard", tags=["dashboard"])


@app.on_event("startup")
async def on_startup():
    start_scheduler()   # APScheduler — replaces Spring's @Scheduled missed-visit job


@app.get("/actuator/health", tags=["health"])
async def health_check():
    return {"status": "UP"}
```

**Health check path kept as `/actuator/health`** (rather than switching to a more Python-idiomatic path like `/health`) — deliberate, so the Docker healthcheck and any existing monitoring config from the Deployment doc need zero changes.

---

## 6. Local Development Environment (`docker-compose.yml`)

```yaml
services:
  postgres:
    image: postgis/postgis:15-3.4
    environment:
      POSTGRES_DB: fieldtrackpro_dev
      POSTGRES_USER: fieldtrackpro
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data

  minio:
    image: minio/minio:latest
    command: server /data --console-address ":9001"
    environment:
      MINIO_ROOT_USER: ${MINIO_ACCESS_KEY}
      MINIO_ROOT_PASSWORD: ${MINIO_SECRET_KEY}
    ports:
      - "9000:9000"
      - "9001:9001"
    volumes:
      - miniodata:/data

volumes:
  pgdata:
  miniodata:
```

Unchanged from the original — `postgres`/`minio` containers never depended on the backend's language. The `postgis/postgis` image is what makes `CREATE EXTENSION postgis;` work locally without manual extension install, same as before.

---

## 7. First Alembic Migration

```bash
alembic init alembic
alembic revision --autogenerate -m "init schema"
alembic upgrade head
```

`alembic/versions/xxxx_init_schema.py` should contain the literal DDL from the Database Design doc (generated automatically from the SQLAlchemy models in `app/models/`), including the signatures uniqueness fix already folded into the schema:

```python
def upgrade():
    # ... full schema from Database Design doc: users, employees, territories,
    # customers, visits, requirement_forms, visit_media, visit_signatures,
    # geo_verification_logs, notifications, requirement_categories ...

    op.create_unique_constraint(
        "uq_visit_signature", "visit_signatures", ["visit_id", "signature_type"]
    )
```

---

## 8. Startup Verification Checklist

Before moving to Authentication (Phase 3.2), confirm:
- [ ] `poetry install` completes cleanly
- [ ] `poetry run uvicorn app.main:app --reload` starts without errors
- [ ] `alembic upgrade head` runs cleanly against a fresh `postgis/postgis` container
- [ ] `/docs` (FastAPI's built-in Swagger UI) loads — confirms routing + OpenAPI generation wiring works, even before real endpoints exist
- [ ] MinIO console (`localhost:9001`) is reachable and the `fieldtrackpro-dev` bucket can be created manually
- [ ] Application fails to start (raises a `pydantic.ValidationError`, not a silent default) if `JWT_SECRET` env var is missing — confirms the "no silent prod fallback" config discipline carried over correctly from the original setup

---

**Next up:** Authentication (Phase 3.2) — JWT handling, security dependencies, login/refresh/logout endpoints, built directly against this scaffold.
