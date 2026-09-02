from __future__ import annotations

import uuid
from datetime import date
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps.auth import CurrentUser, require_role
from app.database import get_async_session
from app.models.user import Role
from app.schemas.customer_requirement import (
    CustomerRequirementCreate,
    CustomerRequirementRead,
    CustomerRequirementUpdate,
)
from app.services import customer_requirement_service

router = APIRouter(prefix="/requirements", tags=["requirements"])

DbSession = Annotated[AsyncSession, Depends(get_async_session)]
AnyAuth = Depends(require_role(Role.ADMIN, Role.EMPLOYEE))


@router.get("", response_model=list[CustomerRequirementRead], dependencies=[AnyAuth])
async def list_all_requirements(
    session: DbSession,
    brand: Optional[str] = Query(default=None, description="Filter by brand"),
    status: Optional[str] = Query(default=None, description="Filter by status (OPEN, IN_PROGRESS, FULFILLED, CANCELLED, or ALL)"),
    follow_up_date: Optional[date] = Query(default=None, description="Filter by exact follow-up date"),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, le=200),
):
    """
    List customer requirements across all outlets for follow-up tracking and management.
    """
    return await customer_requirement_service.list_all_requirements(
        session=session,
        brand=brand,
        status=status,
        follow_up_date=follow_up_date,
        skip=skip,
        limit=limit,
    )


@router.patch("/{requirement_id}", response_model=CustomerRequirementRead, dependencies=[AnyAuth])
async def update_requirement(
    requirement_id: uuid.UUID,
    data: CustomerRequirementUpdate,
    session: DbSession,
):
    """
    Update requirement status, notes, or details.
    """
    return await customer_requirement_service.update_requirement(
        requirement_id=requirement_id,
        data=data,
        session=session,
    )
