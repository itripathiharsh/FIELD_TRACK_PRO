"""
Areas router — /api/v1/areas

The geographic layer between a Zone (Territory) and an Outlet (Customer).
"""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps.auth import require_role
from app.database import get_async_session
from app.models.user import Role
from app.schemas.area import AreaCreate, AreaRead, AreaUpdate
from app.services import area_service

router = APIRouter(prefix="/areas", tags=["areas"])

DbSession = Annotated[AsyncSession, Depends(get_async_session)]
AdminOnly = Depends(require_role(Role.ADMIN))
AnyAuth = Depends(require_role(Role.ADMIN, Role.EMPLOYEE))


@router.post("", response_model=AreaRead, status_code=201, dependencies=[AdminOnly])
async def create_area(data: AreaCreate, session: DbSession):
    area = await area_service.create_area(data, session)
    return area_service.to_area_read(area)


@router.get("", response_model=list[AreaRead], dependencies=[AnyAuth])
async def list_areas(session: DbSession, territory_id: uuid.UUID | None = Query(default=None)):
    areas = await area_service.list_areas(session, territory_id)
    return [area_service.to_area_read(a) for a in areas]


@router.get("/{area_id}", response_model=AreaRead, dependencies=[AnyAuth])
async def get_area(area_id: uuid.UUID, session: DbSession):
    area = await area_service.get_area(area_id, session)
    return area_service.to_area_read(area)


@router.patch("/{area_id}", response_model=AreaRead, dependencies=[AdminOnly])
async def update_area(area_id: uuid.UUID, data: AreaUpdate, session: DbSession):
    area = await area_service.update_area(area_id, data, session)
    return area_service.to_area_read(area)


@router.delete("/{area_id}", status_code=204, dependencies=[AdminOnly])
async def delete_area(area_id: uuid.UUID, session: DbSession):
    await area_service.delete_area(area_id, session)
