from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps.auth import require_role
from app.database import get_async_session
from app.models.user import Role
from app.schemas.brand import BrandCreate, BrandOut, BrandUpdate
from app.services import brand_service

router = APIRouter(prefix="/brands", tags=["brands"])

DbSession = Annotated[AsyncSession, Depends(get_async_session)]
AnyAuth = Depends(require_role(Role.ADMIN, Role.EMPLOYEE))
# Read-only lists for the report filters (GET only).
ReadLists = Depends(require_role(Role.ADMIN, Role.EMPLOYEE, Role.ACCOUNTANT))
AdminAuth = Depends(require_role(Role.ADMIN))


FinanceRead = Depends(require_role(Role.ADMIN, Role.ACCOUNTANT))


@router.get("/filter-options", dependencies=[FinanceRead])
async def brand_filter_options(session: DbSession):
    """Brands to offer in the Dashboard / Reports brand filter: every brand that has Tally invoices or
    receipts (most records first), plus 'Unattributed' when Tally sends records without a brand."""
    from app.services.brand_reconciliation import brand_filter_options as _opts
    return await _opts(session)


@router.get("/reconciliation", dependencies=[FinanceRead])
async def brand_reconciliation(session: DbSession):
    """Read-only Tally vs FieldTrack brand table (Tally brand | FieldTrack brand | status | records)."""
    from app.services.brand_reconciliation import brand_reconciliation as _rec
    return await _rec(session)


@router.get("", response_model=list[BrandOut], dependencies=[ReadLists])
async def list_brands(
    session: DbSession,
    active_only: bool = Query(True, description="Filter only active brands"),
):
    """
    Returns the list of master brands.
    By default, returns active brands. Pass active_only=false to include inactive brands (for Admin management).
    """
    brands = await brand_service.list_brands(session, active_only=active_only)
    return brands


@router.post("", response_model=BrandOut, status_code=status.HTTP_201_CREATED, dependencies=[AdminAuth])
async def create_brand(
    data: BrandCreate,
    session: DbSession,
):
    """
    Create a new master brand (Admin only).
    Enforces case-insensitive duplicate prevention.
    """
    brand = await brand_service.create_brand(session, data)
    await session.commit()
    await session.refresh(brand)
    return brand


@router.get("/{brand_id}", response_model=BrandOut, dependencies=[AnyAuth])
async def get_brand(
    brand_id: uuid.UUID,
    session: DbSession,
):
    """Get brand details by ID."""
    brand = await brand_service.get_brand_by_id(session, brand_id)
    if brand is None:
        from app.exceptions.custom import BaseAPIException
        raise BaseAPIException(
            status_code=404,
            detail=f"Brand with id '{brand_id}' not found.",
            error_code="BRAND_NOT_FOUND",
        )
    return brand


@router.patch("/{brand_id}", response_model=BrandOut, dependencies=[AdminAuth])
async def update_brand(
    brand_id: uuid.UUID,
    data: BrandUpdate,
    session: DbSession,
):
    """Update brand properties or toggle active status (Admin only)."""
    brand = await brand_service.update_brand(session, brand_id, data)
    await session.commit()
    await session.refresh(brand)
    return brand
