"""
Imports router — /api/v1/imports

Full Excel/MIS import pipeline: preview -> validate (full parse + mapping +
resolution + validation, writes only an audit/staging ImportBatch row) ->
commit (the only step that writes to territories/employees/customers/
invoices/payments, transactionally) -> history.

Route order matters: static paths (`/preview`, `/target-fields`, `""`) must
be declared before the `/{batch_id}` family below them, or Starlette's
suffix matcher would capture them as a batch id (same class of bug fixed
earlier in media.py's local-file route).
"""
from __future__ import annotations

import csv
import io
import json
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps.auth import CurrentUser, require_role
from app.database import get_async_session
from app.models.user import Role, User
from app.schemas.import_batch import (
    ImportBatchRead,
    ImportPreviewResponse,
    ImportValidateRequest,
)
from app.services import import_service

router = APIRouter(prefix="/imports", tags=["imports"])

DbSession = Annotated[AsyncSession, Depends(get_async_session)]
AdminOnly = Depends(require_role(Role.ADMIN))


async def _to_read(batch, session: DbSession) -> ImportBatchRead:
    result = await session.execute(select(User.email).where(User.id == batch.uploaded_by))
    email = result.scalar_one_or_none()
    read = ImportBatchRead.model_validate(batch)
    read.uploaded_by_email = email
    return read


@router.get("/target-fields", dependencies=[AdminOnly])
async def get_target_fields():
    """The fixed set of FieldTrack fields an Excel column can be mapped to."""
    return import_service.TARGET_FIELDS


@router.post("/preview", response_model=ImportPreviewResponse, dependencies=[AdminOnly])
async def preview_import_file(
    file: UploadFile = File(...),
    sheet_name: str | None = Form(default=None),
):
    """Inspect an uploaded Excel file's real headers/sample rows and get a suggested column mapping."""
    file_bytes = await file.read()
    filename = file.filename or "upload.xlsx"
    return import_service.preview_excel_file(file_bytes, filename, sheet_name)


@router.post("/validate", response_model=ImportBatchRead, dependencies=[AdminOnly])
async def validate_import(
    current_user: CurrentUser,
    session: DbSession,
    file: UploadFile = File(...),
    request: str = Form(..., description="JSON-encoded ImportValidateRequest"),
):
    """
    Full parse + mapping + resolution + validation against the confirmed
    mapping. Writes nothing to the business tables - only creates the
    ImportBatch audit/staging row (status=VALIDATED) that /commit reads back.
    """
    payload = ImportValidateRequest.model_validate(json.loads(request))
    file_bytes = await file.read()
    filename = file.filename or "upload.xlsx"
    batch = await import_service.create_import_batch(
        file_bytes=file_bytes,
        filename=filename,
        sheet_name=payload.sheet_name,
        column_mapping=payload.column_mapping,
        outlet_match_strategy=payload.outlet_match_strategy,
        allow_generated_invoice_numbers=payload.allow_generated_invoice_numbers,
        current_user=current_user,
        session=session,
    )
    return await _to_read(batch, session)


@router.get("", response_model=list[ImportBatchRead], dependencies=[AdminOnly])
async def list_imports(
    session: DbSession,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, le=200),
):
    """Import history/audit trail."""
    batches = await import_service.list_import_batches(session, skip=skip, limit=limit)
    return [await _to_read(b, session) for b in batches]


@router.get("/{batch_id}", response_model=ImportBatchRead, dependencies=[AdminOnly])
async def get_import(batch_id: uuid.UUID, session: DbSession):
    batch = await import_service.get_import_batch(batch_id, session)
    return await _to_read(batch, session)


@router.get("/{batch_id}/errors.csv", dependencies=[AdminOnly])
async def download_import_errors(batch_id: uuid.UUID, session: DbSession):
    batch = await import_service.get_import_batch(batch_id, session)
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["Row", "Error", "Suggested Fix"])
    for err in batch.error_report or []:
        writer.writerow([err.get("row", ""), err.get("error", ""), err.get("suggested_fix", "")])
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="import_{batch_id}_errors.csv"'},
    )


@router.post("/{batch_id}/commit", response_model=ImportBatchRead, dependencies=[AdminOnly])
async def commit_import(batch_id: uuid.UUID, current_user: CurrentUser, session: DbSession):
    """The only endpoint that writes to territories/employees/customers/invoices/payments."""
    batch = await import_service.commit_import_batch(batch_id, current_user, session)
    return await _to_read(batch, session)
