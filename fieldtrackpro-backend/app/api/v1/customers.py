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
from app.schemas.account import AccountSummary
from app.schemas.customer import CustomerCreate, CustomerRead, CustomerUpdate
from app.schemas.invoice import InvoiceRead
from app.schemas.media import OrderRead
from app.services import account_service, customer_service, invoice_service, media_service

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
    current_user: CurrentUser,
    session: DbSession,
    territory_id: uuid.UUID | None = Query(default=None),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, le=200),
):
    """
    P0-1: an ADMIN sees the full outlet directory; an EMPLOYEE is confined
    server-side to outlets they have at least one visit assigned to (see
    customer_service.list_customers) - never the client-supplied
    territory_id alone.
    """
    customers = await customer_service.list_customers(session, current_user, territory_id, skip, limit)
    return [CustomerRead.from_model(c) for c in customers]


@router.get("/{customer_id}", response_model=CustomerRead, dependencies=[AnyAuth])
async def get_customer(customer_id: uuid.UUID, current_user: CurrentUser, session: DbSession):
    """
    P0-1: an EMPLOYEE may only view an outlet they have a visit assigned to -
    the same ownership rule already enforced for the account/invoices/orders
    endpoints below, now applied consistently to the base profile too.
    """
    await customer_service.assert_employee_can_view_customer(customer_id, current_user, session)
    customer = await customer_service.get_customer(customer_id, session)
    return CustomerRead.from_model(customer)


@router.patch("/{customer_id}", response_model=CustomerRead, dependencies=[AdminOnly])
async def update_customer(
    customer_id: uuid.UUID, data: CustomerUpdate, session: DbSession
):
    customer = await customer_service.update_customer(customer_id, data, session)
    return CustomerRead.from_model(customer)


@router.get("/{customer_id}/account", response_model=AccountSummary, dependencies=[AnyAuth])
async def get_customer_account(customer_id: uuid.UUID, current_user: CurrentUser, session: DbSession):
    """
    Outlet Account panel: outstanding/due/overdue, days outstanding,
    collection status, recent invoices/payments, brand-wise totals.

    An EMPLOYEE may only view this for an outlet they have a visit assigned
    to (see account_service.assert_employee_can_view_account) - an ADMIN can
    view any outlet's account.
    """
    return await account_service.get_account_summary(customer_id, current_user, session)


@router.get("/{customer_id}/invoices", response_model=list[InvoiceRead], dependencies=[AnyAuth])
async def list_customer_invoices(customer_id: uuid.UUID, current_user: CurrentUser, session: DbSession):
    """Full invoice history for an outlet, each annotated with real calculated aging."""
    await account_service.assert_employee_can_view_account(customer_id, current_user, session)
    invoices = await invoice_service.list_invoices_for_customer(customer_id, session)
    return [await invoice_service.to_invoice_read(inv, session) for inv in invoices]


@router.get("/{customer_id}/orders", response_model=list[OrderRead], dependencies=[AnyAuth])
async def list_customer_orders(customer_id: uuid.UUID, current_user: CurrentUser, session: DbSession):
    """Every order captured on this outlet, across its full visit history (P2-B)."""
    return await media_service.list_customer_orders(customer_id, current_user, session)
