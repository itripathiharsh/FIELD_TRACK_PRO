"""
Territory service — updated to support geographic center and coverage radius.
"""
from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions.custom import BaseAPIException
from app.models.territory import Territory
from app.repositories.territory_repo import TerritoryRepository
from app.schemas.territory import TerritoryCreate, TerritoryUpdate


async def create_territory(data: TerritoryCreate, session: AsyncSession) -> Territory:
    repo = TerritoryRepository(session)
    territory = Territory(
        name=data.name,
        center_latitude=data.center_latitude,
        center_longitude=data.center_longitude,
        radius_km=data.radius_km,
        status=data.status,
    )
    await repo.add(territory)
    await repo.commit()
    return territory


async def get_territory(territory_id: uuid.UUID, session: AsyncSession) -> Territory:
    repo = TerritoryRepository(session)
    t = await repo.get_by_id(territory_id)
    if t is None:
        raise BaseAPIException(status_code=404, detail="Territory not found", error_code="TERRITORY_NOT_FOUND")
    return t


async def list_territories(session: AsyncSession) -> list[Territory]:
    repo = TerritoryRepository(session)
    return await repo.list_all()


async def update_territory(territory_id: uuid.UUID, data: TerritoryUpdate, session: AsyncSession) -> Territory:
    t = await get_territory(territory_id, session)
    if data.name is not None:
        t.name = data.name
    if data.center_latitude is not None:
        t.center_latitude = data.center_latitude
    if data.center_longitude is not None:
        t.center_longitude = data.center_longitude
    if data.radius_km is not None:
        t.radius_km = data.radius_km
    if data.status is not None:
        t.status = data.status

    session.add(t)
    await session.commit()
    await session.refresh(t)
    return t


async def delete_territory(territory_id: uuid.UUID, session: AsyncSession) -> None:
    """
    Refuse to delete a territory that is still referenced anywhere, rather
    than letting the FK behaviour decide the outcome by accident: a territory
    only referenced by the live Employee/Customer pointers (ondelete=SET
    NULL) would otherwise be deleted while silently orphaning those records,
    and one referenced by EmployeeTerritoryAssignment history
    (ondelete=RESTRICT, deliberately never nulled) would raise an unhandled
    IntegrityError -> HTTP 500. Mirrors the explicit reference-guard pattern
    already used by FormTemplateService.delete_template.
    """
    t = await get_territory(territory_id, session)

    from app.models.area import Area
    from app.models.customer import Customer
    from app.models.employee import Employee
    from app.models.employee_territory_assignment import EmployeeTerritoryAssignment

    area_count = await session.scalar(
        select(func.count()).select_from(Area).where(Area.territory_id == territory_id)
    )
    if area_count:
        raise BaseAPIException(
            status_code=409,
            detail="Cannot delete a zone that still has one or more areas under it",
            error_code="TERRITORY_IN_USE",
        )

    employee_count = await session.scalar(
        select(func.count()).select_from(Employee).where(Employee.territory_id == territory_id)
    )
    if employee_count:
        raise BaseAPIException(
            status_code=409,
            detail="Cannot delete a territory that is still assigned to one or more employees",
            error_code="TERRITORY_IN_USE",
        )

    customer_count = await session.scalar(
        select(func.count()).select_from(Customer).where(Customer.territory_id == territory_id)
    )
    if customer_count:
        raise BaseAPIException(
            status_code=409,
            detail="Cannot delete a territory that is still assigned to one or more customers",
            error_code="TERRITORY_IN_USE",
        )

    assignment_count = await session.scalar(
        select(func.count())
        .select_from(EmployeeTerritoryAssignment)
        .where(EmployeeTerritoryAssignment.territory_id == territory_id)
    )
    if assignment_count:
        raise BaseAPIException(
            status_code=409,
            detail="Cannot delete a territory that appears in employee reassignment history",
            error_code="TERRITORY_IN_USE",
        )

    await session.delete(t)
    await session.commit()
