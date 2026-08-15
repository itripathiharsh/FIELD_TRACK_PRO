"""
Territory reassignment (P2-D): permanent and temporary employee-territory
assignments, resolved at read time rather than by overwriting
Employee.territory_id, so:
  - a permanent reassignment effective in the future doesn't jump the gun,
  - a temporary assignment reverts automatically once its end_date passes,
    with no scheduled job needed,
  - and no historical visit's territory context is ever rewritten, since
    Employee.territory_id (and every visit already recorded) is never
    touched by this feature.

Employee.territory_id is kept purely as a fallback for employees who predate
this feature and have no assignment history row yet.
"""
from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions.custom import BaseAPIException
from app.models.employee import Employee
from app.models.employee_territory_assignment import AssignmentType, EmployeeTerritoryAssignment
from app.models.territory import Territory
from app.models.user import User
from app.schemas.territory_assignment import TerritoryAssignmentCreate, TerritoryAssignmentHistory, TerritoryAssignmentRead
from app.services.employee_service import get_employee


async def _resolve_effective_assignment(
    employee_id: uuid.UUID, session: AsyncSession, as_of: date | None = None
) -> EmployeeTerritoryAssignment | None:
    """The single history row in effect on `as_of` (default today), or None
    if the employee has no assignment history yet (legacy fallback case)."""
    as_of = as_of or date.today()

    temp_result = await session.execute(
        select(EmployeeTerritoryAssignment)
        .where(
            EmployeeTerritoryAssignment.employee_id == employee_id,
            EmployeeTerritoryAssignment.assignment_type == AssignmentType.TEMPORARY,
            EmployeeTerritoryAssignment.start_date <= as_of,
            EmployeeTerritoryAssignment.end_date >= as_of,
        )
        .order_by(EmployeeTerritoryAssignment.created_at.desc())
        .limit(1)
    )
    temp_row = temp_result.scalar_one_or_none()
    if temp_row is not None:
        return temp_row

    perm_result = await session.execute(
        select(EmployeeTerritoryAssignment)
        .where(
            EmployeeTerritoryAssignment.employee_id == employee_id,
            EmployeeTerritoryAssignment.assignment_type == AssignmentType.PERMANENT,
            EmployeeTerritoryAssignment.start_date <= as_of,
        )
        .order_by(EmployeeTerritoryAssignment.start_date.desc(), EmployeeTerritoryAssignment.created_at.desc())
        .limit(1)
    )
    return perm_result.scalar_one_or_none()


async def get_effective_territory_id(
    employee_id: uuid.UUID, session: AsyncSession, as_of: date | None = None
) -> uuid.UUID | None:
    """The territory an employee is actually working as of `as_of` (default
    today) - a temporary assignment active on that date wins, else the most
    recent permanent assignment effective by then, else the legacy
    Employee.territory_id pointer for employees never reassigned via this
    feature."""
    winning = await _resolve_effective_assignment(employee_id, session, as_of)
    if winning is not None:
        return winning.territory_id
    employee = await session.get(Employee, employee_id)
    return employee.territory_id if employee else None


async def create_assignment(
    employee_id: uuid.UUID,
    data: TerritoryAssignmentCreate,
    current_user: User,
    session: AsyncSession,
) -> EmployeeTerritoryAssignment:
    await get_employee(employee_id, session)  # 404s if the employee doesn't exist

    territory = await session.get(Territory, data.territory_id)
    if territory is None:
        raise BaseAPIException(status_code=404, detail="Territory not found", error_code="TERRITORY_NOT_FOUND")

    if data.assignment_type == AssignmentType.TEMPORARY:
        if data.end_date is None:
            raise BaseAPIException(
                status_code=400,
                detail="end_date is required for a temporary assignment",
                error_code="ASSIGNMENT_END_DATE_REQUIRED",
            )
        if data.end_date < data.start_date:
            raise BaseAPIException(
                status_code=400, detail="end_date cannot be before start_date", error_code="ASSIGNMENT_INVALID_DATES"
            )
        overlap_result = await session.execute(
            select(EmployeeTerritoryAssignment).where(
                EmployeeTerritoryAssignment.employee_id == employee_id,
                EmployeeTerritoryAssignment.assignment_type == AssignmentType.TEMPORARY,
                EmployeeTerritoryAssignment.start_date <= data.end_date,
                EmployeeTerritoryAssignment.end_date >= data.start_date,
            )
        )
        if overlap_result.scalars().first() is not None:
            raise BaseAPIException(
                status_code=409,
                detail="This employee already has a temporary assignment overlapping these dates",
                error_code="ASSIGNMENT_OVERLAP",
            )
    else:  # PERMANENT
        if data.end_date is not None:
            raise BaseAPIException(
                status_code=400,
                detail="end_date must not be set for a permanent assignment",
                error_code="ASSIGNMENT_INVALID_DATES",
            )

    assignment = EmployeeTerritoryAssignment(
        employee_id=employee_id,
        territory_id=data.territory_id,
        assignment_type=data.assignment_type,
        start_date=data.start_date,
        end_date=data.end_date,
        created_by=current_user.id,
    )
    session.add(assignment)

    # Keep the legacy Employee.territory_id pointer in sync ONLY when a
    # PERMANENT assignment is immediately effective (start_date <= today) -
    # this is what every pre-existing admin list/filter that reads the raw
    # column directly (e.g. "employees assigned to this territory" on
    # TerritoryDetailPage) still relies on. A future-dated permanent
    # assignment or any TEMPORARY assignment must NOT touch it: the former
    # hasn't taken effect yet, the latter must revert on its own once its
    # window ends. The history row above is unaffected either way - this is
    # purely a convenience cache, never re-derived FROM this column.
    if data.assignment_type == AssignmentType.PERMANENT and data.start_date <= date.today():
        employee = await session.get(Employee, employee_id)
        if employee is not None:
            employee.territory_id = data.territory_id
            session.add(employee)

    await session.commit()
    await session.refresh(assignment)
    return assignment


async def get_assignment_history(employee_id: uuid.UUID, session: AsyncSession) -> TerritoryAssignmentHistory:
    await get_employee(employee_id, session)  # 404s if the employee doesn't exist

    rows_result = await session.execute(
        select(EmployeeTerritoryAssignment, Territory.name, User.email)
        .join(Territory, Territory.id == EmployeeTerritoryAssignment.territory_id)
        .outerjoin(User, User.id == EmployeeTerritoryAssignment.created_by)
        .where(EmployeeTerritoryAssignment.employee_id == employee_id)
        .order_by(EmployeeTerritoryAssignment.start_date.desc(), EmployeeTerritoryAssignment.created_at.desc())
    )
    rows = rows_result.all()

    winning = await _resolve_effective_assignment(employee_id, session)
    effective_territory_id: uuid.UUID | None
    effective_territory_name: str | None
    if winning is not None:
        effective_territory_id = winning.territory_id
        effective_territory_name = next((name for a, name, _ in rows if a.id == winning.id), None)
    else:
        employee = await session.get(Employee, employee_id)
        effective_territory_id = employee.territory_id if employee else None
        effective_territory_name = None
        if effective_territory_id:
            effective_territory_name = await session.scalar(
                select(Territory.name).where(Territory.id == effective_territory_id)
            )

    assignments = [
        TerritoryAssignmentRead(
            id=a.id,
            employee_id=a.employee_id,
            territory_id=a.territory_id,
            territory_name=territory_name,
            assignment_type=a.assignment_type,
            start_date=a.start_date,
            end_date=a.end_date,
            created_by=a.created_by,
            created_by_email=created_by_email,
            created_at=a.created_at,
            is_current=(winning is not None and a.id == winning.id),
        )
        for a, territory_name, created_by_email in rows
    ]

    return TerritoryAssignmentHistory(
        employee_id=employee_id,
        effective_territory_id=effective_territory_id,
        effective_territory_name=effective_territory_name,
        assignments=assignments,
    )
