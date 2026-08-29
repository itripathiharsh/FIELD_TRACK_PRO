"""
Employee <-> Area coverage service - the brand-agnostic many-to-many
assignment introduced by the Zone/Area/Outlet hierarchy migration. See
app/models/employee_area_assignment.py for why this exists alongside (not
instead of) the older single-Zone Employee.territory_id model.
"""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.exceptions.custom import BaseAPIException
from app.models.area import Area
from app.models.employee import Employee
from app.models.employee_area_assignment import EmployeeAreaAssignment
from app.models.user import User
from app.schemas.employee_area_assignment import EmployeeAreaAssignmentRead
from app.services.area_service import get_area
from app.services.employee_service import get_employee


def _to_read(assignment: EmployeeAreaAssignment) -> EmployeeAreaAssignmentRead:
    return EmployeeAreaAssignmentRead(
        id=assignment.id,
        employee_id=assignment.employee_id,
        area_id=assignment.area_id,
        area_name=assignment.area.name,
        territory_id=assignment.area.territory_id,
        territory_name=assignment.area.territory.name if assignment.area.territory else None,
        created_at=assignment.created_at,
    )


async def get_valid_territory_ids_for_employee(employee_id: uuid.UUID, session: AsyncSession) -> set[uuid.UUID]:
    """Return all territory IDs that this employee is currently validly assigned to."""
    from app.models.employee_territory_assignment import EmployeeTerritoryAssignment
    from app.services.territory_assignment_service import get_effective_territory_id

    valid_ids: set[uuid.UUID] = set()
    effective_id = await get_effective_territory_id(employee_id, session)
    if effective_id:
        valid_ids.add(effective_id)

    # Active territory assignments
    active_assignments = await session.execute(
        select(EmployeeTerritoryAssignment.territory_id).where(
            EmployeeTerritoryAssignment.employee_id == employee_id
        )
    )
    for tid in active_assignments.scalars().all():
        if tid:
            valid_ids.add(tid)

    emp = await session.get(Employee, employee_id)
    if emp and emp.territory_id:
        valid_ids.add(emp.territory_id)

    return valid_ids


async def prune_invalid_area_assignments(employee_id: uuid.UUID, session: AsyncSession) -> int:
    """Remove any EmployeeAreaAssignment rows for areas belonging to territories the employee no longer covers."""
    valid_territories = await get_valid_territory_ids_for_employee(employee_id, session)

    if not valid_territories:
        stmt = select(EmployeeAreaAssignment).where(EmployeeAreaAssignment.employee_id == employee_id)
    else:
        stmt = (
            select(EmployeeAreaAssignment)
            .join(Area, Area.id == EmployeeAreaAssignment.area_id)
            .where(
                EmployeeAreaAssignment.employee_id == employee_id,
                Area.territory_id.notin_(valid_territories),
            )
        )

    result = await session.execute(stmt)
    stale_rows = result.scalars().all()
    count = 0
    for row in stale_rows:
        await session.delete(row)
        count += 1
    return count


async def list_area_coverage(employee_id: uuid.UUID, session: AsyncSession) -> list[EmployeeAreaAssignmentRead]:
    await get_employee(employee_id, session)  # 404s if the employee doesn't exist
    result = await session.execute(
        select(EmployeeAreaAssignment)
        .options(selectinload(EmployeeAreaAssignment.area).selectinload(Area.territory))
        .where(EmployeeAreaAssignment.employee_id == employee_id)
        .order_by(EmployeeAreaAssignment.created_at.desc())
    )
    return [_to_read(a) for a in result.scalars().all()]


async def assign_area(
    employee_id: uuid.UUID, area_id: uuid.UUID, current_user: User, session: AsyncSession
) -> EmployeeAreaAssignmentRead:
    await get_employee(employee_id, session)  # 404s if the employee doesn't exist
    area = await get_area(area_id, session)  # 404s if the area doesn't exist

    valid_territories = await get_valid_territory_ids_for_employee(employee_id, session)
    if area.territory_id not in valid_territories:
        raise BaseAPIException(
            status_code=400,
            detail=f"Area '{area.name}' belongs to a territory that the employee is not assigned to.",
            error_code="INVALID_AREA_TERRITORY",
        )

    existing = await session.execute(
        select(EmployeeAreaAssignment).where(
            EmployeeAreaAssignment.employee_id == employee_id,
            EmployeeAreaAssignment.area_id == area_id,
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise BaseAPIException(
            status_code=409,
            detail="This employee is already assigned to cover this area",
            error_code="AREA_ASSIGNMENT_ALREADY_EXISTS",
        )

    assignment = EmployeeAreaAssignment(employee_id=employee_id, area_id=area_id, created_by=current_user.id)
    session.add(assignment)
    await session.commit()

    result = await session.execute(
        select(EmployeeAreaAssignment)
        .options(selectinload(EmployeeAreaAssignment.area).selectinload(Area.territory))
        .where(EmployeeAreaAssignment.id == assignment.id)
    )
    return _to_read(result.scalar_one())


async def unassign_area(employee_id: uuid.UUID, area_id: uuid.UUID, session: AsyncSession) -> None:
    result = await session.execute(
        select(EmployeeAreaAssignment).where(
            EmployeeAreaAssignment.employee_id == employee_id,
            EmployeeAreaAssignment.area_id == area_id,
        )
    )
    assignment = result.scalar_one_or_none()
    if assignment is None:
        raise BaseAPIException(
            status_code=404,
            detail="This employee is not assigned to cover this area",
            error_code="AREA_ASSIGNMENT_NOT_FOUND",
        )
    await session.delete(assignment)
    await session.commit()


async def list_employees_covering_area(area_id: uuid.UUID, session: AsyncSession) -> list[uuid.UUID]:
    """Every employee_id currently assigned to cover this area - used to
    derive an outlet's "assigned employee(s)" for the Collections Overview."""
    result = await session.execute(
        select(EmployeeAreaAssignment.employee_id).where(EmployeeAreaAssignment.area_id == area_id)
    )
    return [row[0] for row in result.all()]
