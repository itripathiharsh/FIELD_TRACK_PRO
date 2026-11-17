"""Physical outlet <-> Tally ledger mapping API (release 2.1.0, CONTRACTS_2.1.0 C5).

Reads and single writes: ADMIN (and SUPER_ADMIN). Bulk apply / revert: SUPER_ADMIN only.
Nothing here links ledgers automatically: every link is an explicit request or a workbook row
the client answered Y."""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any, Optional

from fastapi import APIRouter, Depends, File, Query, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps.auth import CurrentUser, require_role
from app.database import get_async_session
from app.models.user import Role
from app.services import outlet_link_service as svc

router = APIRouter(prefix="/outlet-mapping", tags=["outlet-mapping"])
DbSession = Annotated[AsyncSession, Depends(get_async_session)]
AdminOnly = Depends(require_role(Role.ADMIN))
SuperOnly = Depends(require_role(Role.SUPER_ADMIN))
MAX_WORKBOOK_BYTES = 20 * 1024 * 1024


class LinkEventRead(BaseModel):
    id: uuid.UUID
    action: str
    ledger_id: Optional[uuid.UUID] = None
    ledger_name: Optional[str] = None
    from_customer_id: Optional[uuid.UUID] = None
    to_customer_id: Optional[uuid.UUID] = None
    batch_id: Optional[uuid.UUID] = None
    actor: Optional[str] = None
    note: Optional[str] = None
    created_at: Optional[datetime] = None


class LinkIn(BaseModel):
    ledger_id: uuid.UUID
    target_customer_id: uuid.UUID
    note: Optional[str] = Field(default=None, max_length=1000)


class LedgerIn(BaseModel):
    ledger_id: uuid.UUID
    note: Optional[str] = Field(default=None, max_length=1000)


class BrandIn(BaseModel):
    ledger_id: uuid.UUID
    brand: Optional[str] = Field(default=None, max_length=100)


class CodeIn(BaseModel):
    customer_id: uuid.UUID
    outlet_code: Optional[str] = Field(default=None, max_length=50)


class RenameIn(BaseModel):
    customer_id: uuid.UUID
    name: str = Field(min_length=1, max_length=150)


class ReviewIn(BaseModel):
    ledger_id: uuid.UUID
    decision: str = "KEEP_SEPARATE"


class ApplyIn(BaseModel):
    preview_id: uuid.UUID


class RevertIn(BaseModel):
    batch_id: uuid.UUID


class ImportPreview(BaseModel):
    preview_id: uuid.UUID
    expires_at: datetime
    rows: int
    confirmed_rows: int
    ignored_rows: int
    links: list[dict[str, Any]]
    brand_updates: list[dict[str, Any]]
    code_updates: list[dict[str, Any]]
    errors: list[dict[str, Any]]
    warnings: list[dict[str, Any]]
    outlets_before: int
    outlets_after: int
    totals_before: dict[str, Decimal]
    totals_after: dict[str, Decimal]
    invariants_ok: bool


async def _done(session: AsyncSession, ev) -> LinkEventRead:
    await session.commit()
    return LinkEventRead(**await svc.event_read(session, ev))


@router.get("/queues", dependencies=[AdminOnly])
async def get_queues(session: DbSession) -> dict:
    return await svc.queues(session)


@router.post("/link", response_model=LinkEventRead, dependencies=[AdminOnly])
async def post_link(body: LinkIn, user: CurrentUser, session: DbSession):
    return await _done(session, await svc.link(session, body.ledger_id, body.target_customer_id, user, body.note))


@router.post("/unlink", response_model=LinkEventRead, dependencies=[AdminOnly])
async def post_unlink(body: LedgerIn, user: CurrentUser, session: DbSession):
    return await _done(session, await svc.unlink(session, body.ledger_id, user, body.note))


@router.post("/primary", response_model=LinkEventRead, dependencies=[AdminOnly])
async def post_primary(body: LedgerIn, user: CurrentUser, session: DbSession):
    return await _done(session, await svc.set_primary(session, body.ledger_id, user))


@router.post("/brand", response_model=LinkEventRead, dependencies=[AdminOnly])
async def post_brand(body: BrandIn, user: CurrentUser, session: DbSession):
    return await _done(session, await svc.set_brand(session, body.ledger_id, body.brand, user))


@router.post("/outlet-code", response_model=LinkEventRead, dependencies=[AdminOnly])
async def post_outlet_code(body: CodeIn, user: CurrentUser, session: DbSession):
    return await _done(session, await svc.set_outlet_code(session, body.customer_id, body.outlet_code, user))


@router.post("/rename", response_model=LinkEventRead, dependencies=[AdminOnly])
async def post_rename(body: RenameIn, user: CurrentUser, session: DbSession):
    return await _done(session, await svc.rename(session, body.customer_id, body.name, user))


@router.post("/review", response_model=LinkEventRead, dependencies=[AdminOnly])
async def post_review(body: ReviewIn, user: CurrentUser, session: DbSession):
    return await _done(session, await svc.review(session, body.ledger_id, body.decision, user))


@router.post("/import/preview", response_model=ImportPreview, dependencies=[AdminOnly])
async def post_import_preview(user: CurrentUser, session: DbSession, file: UploadFile = File(...)):
    content = await file.read(MAX_WORKBOOK_BYTES + 1)
    if len(content) > MAX_WORKBOOK_BYTES:
        from app.exceptions.custom import BaseAPIException
        raise BaseAPIException(status_code=413, detail="Workbook too large", error_code="PAYLOAD_TOO_LARGE")
    return await svc.build_preview(session, content, user)


@router.post("/import/apply", dependencies=[SuperOnly])
async def post_import_apply(body: ApplyIn, user: CurrentUser, session: DbSession) -> dict:
    return await svc.apply_preview(session, body.preview_id, user)


@router.post("/import/revert", dependencies=[SuperOnly])
async def post_import_revert(body: RevertIn, user: CurrentUser, session: DbSession) -> dict:
    return await svc.revert_batch(session, body.batch_id, user)


@router.get("/events", response_model=list[LinkEventRead], dependencies=[AdminOnly])
async def get_events(session: DbSession, batch_id: Optional[uuid.UUID] = Query(default=None),
                     ledger_id: Optional[uuid.UUID] = Query(default=None), limit: int = Query(default=200, le=2000)):
    return [LinkEventRead(**await svc.event_read(session, e))
            for e in await svc.list_events(session, batch_id, ledger_id, limit)]
