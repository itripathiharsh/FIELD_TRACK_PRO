"""
Employees router — /api/v1/employees
"""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.client_ip import get_client_ip
from app.core.deps.auth import CurrentUser, require_role
from app.database import get_async_session
from app.models.user import Role
from app.schemas.admin_security import AdminPasswordResetResponse
from app.schemas.employee import EmployeeCreate, EmployeeRead, EmployeeReadWithUser, EmployeeRegistration, EmployeeUpdate
from app.schemas.employee_activity import EmployeeActivity
from app.schemas.employee_area_assignment import EmployeeAreaAssignmentCreate, EmployeeAreaAssignmentRead
from app.schemas.territory_assignment import TerritoryAssignmentCreate, TerritoryAssignmentHistory, TerritoryAssignmentRead
from app.services import (
    admin_security_service,
    employee_activity_service,
    employee_area_service,
    employee_service,
    territory_assignment_service,
)

router = APIRouter(prefix="/employees", tags=["employees"])

DbSession = Annotated[AsyncSession, Depends(get_async_session)]
AdminOnly = Depends(require_role(Role.ADMIN))
AnyAuth = Depends(require_role(Role.ADMIN, Role.EMPLOYEE))


async def _accountant_targets_field_staff_only(employee_id: uuid.UUID, actor, session: AsyncSession) -> None:
    """An ACCOUNTANT may change FIELD STAFF (EMPLOYEE) profiles and assignments only - never an Admin,
    Super Admin or Accountant profile (whose login email / mobile the edit form could change)."""
    if actor.role != Role.ACCOUNTANT:
        return
    from sqlalchemy import select
    from app.exceptions.custom import ForbiddenException
    from app.models.employee import Employee
    from app.models.user import User

    target_role = (
        await session.execute(select(User.role).join(Employee, Employee.user_id == User.id).where(Employee.id == employee_id))
    ).scalar_one_or_none()
    if target_role is not None and target_role != Role.EMPLOYEE:
        raise ForbiddenException("An Accountant can only change field staff profiles")


@router.post("/register", response_model=EmployeeReadWithUser, status_code=201, dependencies=[AdminOnly])
async def register_employee(data: EmployeeRegistration, request: Request, current_user: CurrentUser, session: DbSession):
    """
    Admin: create a new user account and employee profile together.

    Role rules: an Admin may create EMPLOYEE accounts only; creating an ADMIN requires a Super Admin;
    SUPER_ADMIN can never be created here.
    """
    return await employee_service.register_employee(data, session, current_user, get_client_ip(request))


@router.post("", response_model=EmployeeRead, status_code=201, dependencies=[AdminOnly])
async def create_employee(data: EmployeeCreate, session: DbSession):
    return await employee_service.create_employee(data, session)


@router.get("/me", response_model=EmployeeReadWithUser)
async def get_my_profile(current_user: CurrentUser, session: DbSession):
    """Authenticated employee: view own profile."""
    return await employee_service.get_employee_by_user_id(current_user.id, session)


@router.get("", response_model=list[EmployeeReadWithUser], dependencies=[AdminOnly])
async def list_employees(
    response: Response,
    session: DbSession,
    territory_id: uuid.UUID | None = Query(default=None),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, le=5000),
    search: str | None = Query(default=None, description="Search across full name, code, email, mobile, CUG"),
    is_active: bool | None = Query(default=None),
    role: str | None = Query(default=None),
    working_profile: str | None = Query(default=None),
    area_id: uuid.UUID | None = Query(default=None),
):
    """
    Admin: list employee profiles with server-side pagination, search, and filtering.
    Returns X-Total-Count header for scalable frontend pagination.
    """
    employees, total_count = await employee_service.list_employees(
        session=session,
        territory_id=territory_id,
        skip=skip,
        limit=limit,
        search=search,
        is_active=is_active,
        role=role,
        working_profile=working_profile,
        area_id=area_id,
    )
    response.headers["X-Total-Count"] = str(total_count)
    return [EmployeeReadWithUser.model_validate(e) for e in employees]


@router.get("/{employee_id}", response_model=EmployeeReadWithUser, dependencies=[AdminOnly])
async def get_employee(employee_id: uuid.UUID, session: DbSession):
    """Admin: view any employee profile. Employees use GET /employees/me for their own."""
    return await employee_service.get_employee(employee_id, session)


@router.patch("/{employee_id}", response_model=EmployeeRead, dependencies=[AdminOnly])
async def update_employee(
    employee_id: uuid.UUID, data: EmployeeUpdate, request: Request, current_user: CurrentUser, session: DbSession
):
    await _accountant_targets_field_staff_only(employee_id, current_user, session)
    return await employee_service.update_employee(employee_id, data, session, current_user, get_client_ip(request))


@router.post(
    "/{employee_id}/reset-password",
    response_model=AdminPasswordResetResponse,
    dependencies=[AdminOnly],
    summary="Admin: reset an employee's password",
)
async def reset_employee_password(
    employee_id: uuid.UUID,
    request: Request,
    response: Response,
    current_user: CurrentUser,
    session: DbSession,
):
    """
    Generate a single-use temporary password for the employee (valid for `TEMP_PASSWORD_EXPIRY_MINUTES`,
    default 30). The plaintext is returned in THIS response only - it is never stored or logged, and
    there is no endpoint to fetch it again. All of the employee's sessions are ended and they must set a
    new password at next sign-in. Admins may reset EMPLOYEE accounts; Super Admins may also reset ADMIN
    accounts; Super Admin accounts and your own account cannot be reset here.
    """
    result = await admin_security_service.admin_reset_employee_password(
        current_user, employee_id, session, get_client_ip(request)
    )
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    return AdminPasswordResetResponse(**result)


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
    await _accountant_targets_field_staff_only(employee_id, current_user, session)
    assignment = await territory_assignment_service.create_assignment(employee_id, data, current_user, session)
    history = await territory_assignment_service.get_assignment_history(employee_id, session)
    return next(a for a in history.assignments if a.id == assignment.id)


@router.get(
    "/{employee_id}/areas",
    response_model=list[EmployeeAreaAssignmentRead],
    dependencies=[AdminOnly],
)
async def list_employee_area_coverage(employee_id: uuid.UUID, session: DbSession):
    """
    Admin: every Area this employee is currently assigned to cover -
    brand-agnostic, many-to-many (an employee can cover several Areas across
    several Zones; see EmployeeAreaAssignment). Independent of, and additive
    to, the older single-Zone territory-assignments endpoint above.
    """
    return await employee_area_service.list_area_coverage(employee_id, session)


@router.post(
    "/{employee_id}/areas",
    response_model=EmployeeAreaAssignmentRead,
    status_code=201,
    dependencies=[AdminOnly],
)
async def assign_employee_area(
    employee_id: uuid.UUID, data: EmployeeAreaAssignmentCreate, current_user: CurrentUser, session: DbSession
):
    """Admin: assign this employee to cover an additional Area."""
    await _accountant_targets_field_staff_only(employee_id, current_user, session)
    return await employee_area_service.assign_area(employee_id, data.area_id, current_user, session)


@router.delete("/{employee_id}/areas/{area_id}", status_code=204, dependencies=[AdminOnly])
async def unassign_employee_area(employee_id: uuid.UUID, area_id: uuid.UUID, current_user: CurrentUser, session: DbSession):
    """Admin: remove this employee's coverage of an Area."""
    await _accountant_targets_field_staff_only(employee_id, current_user, session)
    await employee_area_service.unassign_area(employee_id, area_id, session)
