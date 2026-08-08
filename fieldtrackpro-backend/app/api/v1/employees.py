"""
Employees router — /api/v1/employees
"""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps.auth import CurrentUser, require_role
from app.database import get_async_session
from app.models.user import Role
from app.schemas.employee import EmployeeCreate, EmployeeRead, EmployeeReadWithUser, EmployeeUpdate
from app.services import employee_service

router = APIRouter(prefix="/employees", tags=["employees"])

DbSession = Annotated[AsyncSession, Depends(get_async_session)]
AdminOnly = Depends(require_role(Role.ADMIN))
AnyAuth = Depends(require_role(Role.ADMIN, Role.EMPLOYEE))


@router.post("", response_model=EmployeeRead, status_code=201, dependencies=[AdminOnly])
async def create_employee(data: EmployeeCreate, session: DbSession):
    return await employee_service.create_employee(data, session)


@router.get("/me", response_model=EmployeeReadWithUser)
async def get_my_profile(current_user: CurrentUser, session: DbSession):
    """Authenticated employee: view own profile."""
    return await employee_service.get_employee_by_user_id(current_user.id, session)


@router.get("", response_model=list[EmployeeReadWithUser], dependencies=[AdminOnly])
async def list_employees(
    session: DbSession,
    territory_id: uuid.UUID | None = Query(default=None),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, le=200),
):
    """
    Admin: list employee profiles.

    FT-073: returns the linked account (`user`) alongside the profile. The
    previous `EmployeeRead` omitted it, so the admin table's Role and Contact
    columns were permanently blank - the data was already eager-loaded by
    `list_with_user()` and then discarded during serialisation. Using the same
    model as the detail endpoint also keeps one entity from changing shape
    depending on how it was fetched. No additional query is introduced.
    """
    return await employee_service.list_employees(session, territory_id, skip, limit)


@router.get("/{employee_id}", response_model=EmployeeReadWithUser, dependencies=[AnyAuth])
async def get_employee(employee_id: uuid.UUID, session: DbSession):
    return await employee_service.get_employee(employee_id, session)


@router.patch("/{employee_id}", response_model=EmployeeRead, dependencies=[AdminOnly])
async def update_employee(
    employee_id: uuid.UUID, data: EmployeeUpdate, session: DbSession
):
    return await employee_service.update_employee(employee_id, data, session)
