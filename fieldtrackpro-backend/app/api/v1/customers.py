"""
Customers router — /api/v1/customers
"""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps.auth import CurrentUser, require_role
from app.database import get_async_session
from app.models.user import Role
from app.schemas.customer import CustomerCreate, CustomerRead, CustomerUpdate
from app.services import customer_service

router = APIRouter(prefix="/customers", tags=["customers"])

DbSession = Annotated[AsyncSession, Depends(get_async_session)]
AdminOnly = Depends(require_role(Role.ADMIN))
AnyAuth = Depends(require_role(Role.ADMIN, Role.EMPLOYEE))


@router.post("", response_model=CustomerRead, status_code=201, dependencies=[AdminOnly])
async def create_customer(
    data: CustomerCreate,
    current_user: CurrentUser,
    session: DbSession,
):
    customer = await customer_service.create_customer(data, current_user.id, session)
    return CustomerRead.from_model(customer)


@router.get("", response_model=list[CustomerRead], dependencies=[AnyAuth])
async def list_customers(
    session: DbSession,
    territory_id: uuid.UUID | None = Query(default=None),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, le=200),
):
    customers = await customer_service.list_customers(session, territory_id, skip, limit)
    return [CustomerRead.from_model(c) for c in customers]


@router.get("/{customer_id}", response_model=CustomerRead, dependencies=[AnyAuth])
async def get_customer(customer_id: uuid.UUID, session: DbSession):
    customer = await customer_service.get_customer(customer_id, session)
    return CustomerRead.from_model(customer)


@router.patch("/{customer_id}", response_model=CustomerRead, dependencies=[AdminOnly])
async def update_customer(
    customer_id: uuid.UUID, data: CustomerUpdate, session: DbSession
):
    customer = await customer_service.update_customer(customer_id, data, session)
    return CustomerRead.from_model(customer)
