from __future__ import annotations

import uuid
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps.auth import CurrentUser, require_role
from app.database import get_async_session
from app.models.order import Order
from app.models.user import Role
from app.schemas.customer_requirement import OrderRead
from app.services import customer_requirement_service

router = APIRouter(prefix="/orders", tags=["orders"])

DbSession = Annotated[AsyncSession, Depends(get_async_session)]
AnyAuth = Depends(require_role(Role.ADMIN, Role.EMPLOYEE))


@router.get("", response_model=list[OrderRead], dependencies=[AnyAuth])
async def list_orders(
    session: DbSession,
    current_user: CurrentUser,
    customer_id: Optional[uuid.UUID] = Query(default=None, description="Filter by customer ID"),
    status: Optional[str] = Query(default=None, description="Filter by status (PENDING_TALLY, SENT_TO_TALLY, TALLY_CONFIRMED, TALLY_FAILED, or ALL)"),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, le=200),
):
    """
    List confirmed customer orders and their Tally synchronization status.
    ADMIN: all orders. EMPLOYEE: only orders raised from their own visits.
    """
    return await customer_requirement_service.list_orders(
        session=session,
        customer_id=customer_id,
        status=status,
        skip=skip,
        limit=limit,
        employee_id=await _employee_scope(current_user, session),
    )


async def _employee_scope(current_user, session):
    if current_user.has_global_scope:
        return None
    from app.services.employee_service import get_employee_by_user_id

    return (await get_employee_by_user_id(current_user.id, session)).id


@router.get("/{order_id}", response_model=OrderRead, dependencies=[AnyAuth])
async def get_order(
    order_id: uuid.UUID,
    session: DbSession,
    current_user: CurrentUser,
):
    """
    Get detailed confirmed order with line items and Tally confirmation details.
    An EMPLOYEE can only read orders from their own visits (404 otherwise).
    """
    orders = await customer_requirement_service.list_orders(
        session=session,
        skip=0,
        limit=1,
        order_id=order_id,
        employee_id=await _employee_scope(current_user, session),
    )
    if not orders:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found",
        )
    return orders[0]
