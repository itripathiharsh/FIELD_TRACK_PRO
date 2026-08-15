"""
Invoices router — /api/v1/invoices

Manual invoice entry. Bulk/import creation is handled separately by the
Excel/MIS import endpoints (app/api/v1/imports.py) once a real client file
is available.
"""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps.auth import CurrentUser, require_role
from app.database import get_async_session
from app.models.user import Role
from app.schemas.invoice import InvoiceCreate, InvoiceRead
from app.services import invoice_service

router = APIRouter(prefix="/invoices", tags=["invoices"])

DbSession = Annotated[AsyncSession, Depends(get_async_session)]
AdminOnly = Depends(require_role(Role.ADMIN))


@router.post("", response_model=InvoiceRead, status_code=201, dependencies=[AdminOnly])
async def create_invoice(data: InvoiceCreate, current_user: CurrentUser, session: DbSession):
    invoice = await invoice_service.create_invoice(data, current_user, session)
    return await invoice_service.to_invoice_read(invoice, session)


@router.get("/{invoice_id}", response_model=InvoiceRead, dependencies=[AdminOnly])
async def get_invoice(invoice_id: uuid.UUID, session: DbSession):
    invoice = await invoice_service.get_invoice(invoice_id, session)
    return await invoice_service.to_invoice_read(invoice, session)
