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
from app.schemas.employee_activity import EmployeeActivity
from app.schemas.territory_assignment import TerritoryAssignmentCreate, TerritoryAssignmentHistory, TerritoryAssignmentRead
from app.services import employee_activity_service, employee_service, territory_assignment_service

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


@router.get("/{employee_id}", response_model=EmployeeReadWithUser, dependencies=[AdminOnly])
async def get_employee(employee_id: uuid.UUID, session: DbSession):
    """Admin: view any employee profile. Employees use GET /employees/me for their own."""
    return await employee_service.get_employee(employee_id, session)


@router.patch("/{employee_id}", response_model=EmployeeRead, dependencies=[AdminOnly])
async def update_employee(
    employee_id: uuid.UUID, data: EmployeeUpdate, session: DbSession
):
    return await employee_service.update_employee(employee_id, data, session)


@router.get("/{employee_id}/activity", response_model=EmployeeActivity, dependencies=[AdminOnly])
async def get_employee_activity(employee_id: uuid.UUID, session: DbSession):
    """Admin: consolidated visits/collections/orders view for one employee (P2-C)."""
    return await employee_activity_service.get_employee_activity(employee_id, session)


@router.get(
    "/{employee_id}/territory-assignments",
    response_model=TerritoryAssignmentHistory,
    dependencies=[AdminOnly],
)
async def get_territory_assignment_history(employee_id: uuid.UUID, session: DbSession):
    """Admin: current effective territory + full reassignment history (P2-D)."""
    return await territory_assignment_service.get_assignment_history(employee_id, session)


@router.post(
    "/{employee_id}/territory-assignments",
    response_model=TerritoryAssignmentRead,
    status_code=201,
    dependencies=[AdminOnly],
)
async def create_territory_assignment(
    employee_id: uuid.UUID, data: TerritoryAssignmentCreate, current_user: CurrentUser, session: DbSession
):
    """Admin: create a permanent or temporary territory reassignment (P2-D)."""
    assignment = await territory_assignment_service.create_assignment(employee_id, data, current_user, session)
    history = await territory_assignment_service.get_assignment_history(employee_id, session)
    return next(a for a in history.assignments if a.id == assignment.id)
