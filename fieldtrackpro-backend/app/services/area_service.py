"""
Area service - CRUD for the Zone -> Area -> Outlet geographic hierarchy's
middle layer. See app/models/area.py.
"""
from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions.custom import BaseAPIException
from app.models.area import Area
from app.repositories.area_repo import AreaRepository
from app.schemas.area import AreaCreate, AreaRead, AreaUpdate
from app.services.territory_service import get_territory


def to_area_read(area: Area) -> AreaRead:
    return AreaRead(
        id=area.id,
        name=area.name,
        territory_id=area.territory_id,
        territory_name=area.territory.name if area.territory is not None else None,
        created_at=area.created_at,
        updated_at=area.updated_at,
    )


async def create_area(data: AreaCreate, session: AsyncSession) -> Area:
    await get_territory(data.territory_id, session)  # 404s if the zone doesn't exist

    repo = AreaRepository(session)
    existing = await repo.find_by_name_ci(data.territory_id, data.name)
    if existing is not None:
        raise BaseAPIException(
            status_code=409,
            detail=f"An area named '{existing.name}' already exists in this zone - "
                    "if this is a spelling/casing variant of the same place, use the existing one "
                    "rather than creating a duplicate.",
            error_code="AREA_ALREADY_EXISTS",
        )

    area = Area(name=data.name, territory_id=data.territory_id)
    await repo.add(area)
    await repo.commit()
    await session.refresh(area, attribute_names=["territory"])
    return area


async def get_area(area_id: uuid.UUID, session: AsyncSession) -> Area:
    repo = AreaRepository(session)
    area = await repo.get_by_id(area_id)
    if area is None:
        raise BaseAPIException(status_code=404, detail="Area not found", error_code="AREA_NOT_FOUND")
    return area


async def list_areas(session: AsyncSession, territory_id: uuid.UUID | None = None) -> list[Area]:
    repo = AreaRepository(session)
    return await repo.list_by_territory(territory_id)


async def update_area(area_id: uuid.UUID, data: AreaUpdate, session: AsyncSession) -> Area:
    area = await get_area(area_id, session)
    if data.name is not None:
        repo = AreaRepository(session)
        existing = await repo.find_by_name_ci(area.territory_id, data.name)
        if existing is not None and existing.id != area.id:
            raise BaseAPIException(
                status_code=409,
                detail=f"An area named '{existing.name}' already exists in this zone",
                error_code="AREA_ALREADY_EXISTS",
            )
        area.name = data.name
    session.add(area)
    await session.commit()
    await session.refresh(area)
    return area


async def delete_area(area_id: uuid.UUID, session: AsyncSession) -> None:
    """
    Refuse to delete an area still referenced by an outlet or an employee's
    coverage assignment, mirroring territory_service.delete_territory's
    explicit reference-guard pattern - rather than letting ondelete=SET
    NULL/CASCADE silently orphan/erase those references.
    """
    area = await get_area(area_id, session)

    from app.models.customer import Customer
    from app.models.employee_area_assignment import EmployeeAreaAssignment

    customer_count = await session.scalar(
        select(func.count()).select_from(Customer).where(Customer.area_id == area_id)
    )
    if customer_count:
        raise BaseAPIException(
            status_code=409,
            detail="Cannot delete an area that is still assigned to one or more outlets",
            error_code="AREA_IN_USE",
        )

    assignment_count = await session.scalar(
        select(func.count()).select_from(EmployeeAreaAssignment).where(EmployeeAreaAssignment.area_id == area_id)
    )
    if assignment_count:
        raise BaseAPIException(
            status_code=409,
            detail="Cannot delete an area that one or more employees are assigned to cover",
            error_code="AREA_IN_USE",
        )

    await session.delete(area)
    await session.commit()
