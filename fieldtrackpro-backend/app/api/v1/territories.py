"""
Territories router — /api/v1/territories
"""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps.auth import require_role
from app.database import get_async_session
from app.models.user import Role
from app.schemas.territory import TerritoryCreate, TerritoryRead, TerritoryUpdate
from app.services import territory_service

router = APIRouter(prefix="/territories", tags=["territories"])

DbSession = Annotated[AsyncSession, Depends(get_async_session)]
AdminOnly = Depends(require_role(Role.ADMIN))
AnyAuth = Depends(require_role(Role.ADMIN, Role.EMPLOYEE))


@router.post("", response_model=TerritoryRead, status_code=201, dependencies=[AdminOnly])
async def create_territory(data: TerritoryCreate, session: DbSession):
    return await territory_service.create_territory(data, session)


@router.get("", response_model=list[TerritoryRead], dependencies=[AnyAuth])
async def list_territories(session: DbSession):
    return await territory_service.list_territories(session)


@router.get("/{territory_id}", response_model=TerritoryRead, dependencies=[AnyAuth])
async def get_territory(territory_id: uuid.UUID, session: DbSession):
    return await territory_service.get_territory(territory_id, session)


@router.patch("/{territory_id}", response_model=TerritoryRead, dependencies=[AdminOnly])
async def update_territory(
    territory_id: uuid.UUID, data: TerritoryUpdate, session: DbSession
):
    return await territory_service.update_territory(territory_id, data, session)


@router.delete("/{territory_id}", status_code=204, dependencies=[AdminOnly])
async def delete_territory(territory_id: uuid.UUID, session: DbSession):
    await territory_service.delete_territory(territory_id, session)
