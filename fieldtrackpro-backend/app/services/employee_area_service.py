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
        territory_name=assignment.area.territory.name,
        created_at=assignment.created_at,
    )


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
    await get_area(area_id, session)  # 404s if the area doesn't exist

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
