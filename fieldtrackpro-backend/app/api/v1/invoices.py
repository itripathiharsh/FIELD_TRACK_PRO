"""
Invoices router — /api/v1/invoices

Sales invoices come only from Tally (imported by the sync agent); there is no
manual invoice entry. Field Track Pro orders are not invoices until the
accountant records them in Tally.
"""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps.auth import require_role
from app.database import get_async_session
from app.models.user import Role
from app.schemas.invoice import InvoiceRead
from app.services import invoice_service

router = APIRouter(prefix="/invoices", tags=["invoices"])

DbSession = Annotated[AsyncSession, Depends(get_async_session)]
AdminOnly = Depends(require_role(Role.ADMIN))


@router.get("/{invoice_id}", response_model=InvoiceRead, dependencies=[AdminOnly])
async def get_invoice(invoice_id: uuid.UUID, session: DbSession):
    invoice = await invoice_service.get_invoice(invoice_id, session)
    return await invoice_service.to_invoice_read(invoice, session)
