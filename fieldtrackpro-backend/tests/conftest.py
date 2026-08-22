"""
pytest configuration and shared fixtures.
"""
from __future__ import annotations

import asyncio
import uuid

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

from app.core.security import create_access_token, hash_password
from app.main import app
from app.models.user import Role, User
from app.models.employee import Employee
from app.models.territory import Territory
from app.models.customer import Customer
from app.models.visit import Visit, VisitStatus
from app.models.refresh_token import RefreshToken


# ---------------------------------------------------------------------------
# Async test event loop
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture(autouse=True)
async def dispose_db_engine():
    yield
    from app.database import engine
    await engine.dispose()



# ---------------------------------------------------------------------------
# HTTP client fixture (no real DB — tests target unit/service logic)
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


# ---------------------------------------------------------------------------
# Auth token helpers
# ---------------------------------------------------------------------------

SEED_ADMIN_ID = "0f8eb7d1-bf0d-4c52-a022-491b61d2bdb3"
SEED_EMPLOYEE_ID = "328140a1-d592-42a1-a287-69871f287ed2"


def make_admin_token(user_id: str | None = None) -> str:
    if user_id:
        return create_access_token(user_id, Role.ADMIN.value)
    try:
        from app.config import settings
        from sqlalchemy import create_engine, select
        from sqlalchemy.orm import Session
        engine = create_engine(settings.database_url.replace("postgresql+asyncpg://", "postgresql://"))
        with Session(engine) as s:
            u = s.execute(select(User).where(User.role == Role.ADMIN, User.is_active == True)).scalars().first()
            if u:
                return create_access_token(str(u.id), Role.ADMIN.value)
    except Exception:
        pass
    return create_access_token(SEED_ADMIN_ID, Role.ADMIN.value)


def make_employee_token(user_id: str | None = None) -> str:
    if user_id:
        return create_access_token(user_id, Role.EMPLOYEE.value)
    try:
        from app.config import settings
        from sqlalchemy import create_engine, select
        from sqlalchemy.orm import Session
        engine = create_engine(settings.database_url.replace("postgresql+asyncpg://", "postgresql://"))
        with Session(engine) as s:
            u = s.execute(select(User).where(User.role == Role.EMPLOYEE, User.is_active == True)).scalars().first()
            if u:
                return create_access_token(str(u.id), Role.EMPLOYEE.value)
    except Exception:
        pass
    return create_access_token(SEED_EMPLOYEE_ID, Role.EMPLOYEE.value)



def admin_headers(user_id: str | None = None) -> dict:
    return {"Authorization": f"Bearer {make_admin_token(user_id)}"}


def employee_headers(user_id: str | None = None) -> dict:
    return {"Authorization": f"Bearer {make_employee_token(user_id)}"}


# ---------------------------------------------------------------------------
# DB availability check for integration tests
# ---------------------------------------------------------------------------

def _check_db_migrated() -> bool:
    try:
        from app.config import settings
        from sqlalchemy import create_engine, text

        # Use sync driver for quick check
        sync_url = settings.database_url.replace("+asyncpg", "")
        engine = create_engine(sync_url, connect_args={"connect_timeout": 2})
        with engine.connect() as conn:
            conn.execute(text("SELECT 1 FROM users LIMIT 1"))
        engine.dispose()
        return True
    except Exception:
        return False


IS_DB_MIGRATED = _check_db_migrated()

requires_db = pytest.mark.skipif(
    not IS_DB_MIGRATED,
    reason="Requires PostGIS PostgreSQL database migration (external prerequisite)",
)
