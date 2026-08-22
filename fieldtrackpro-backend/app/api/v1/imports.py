"""
Imports router — /api/v1/imports

Full Excel/MIS import pipeline: preview -> validate -> resolve mappings -> commit -> history.
Includes FOS mapping management and employee credential spreadsheet generation.
"""
from __future__ import annotations

import csv
import io
import json
import uuid
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi.responses import StreamingResponse, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps.auth import CurrentUser, require_role
from app.database import get_async_session
from app.models.user import Role, User
from app.models.employee import Employee
from app.models.fos_mapping import FOSEmployeeMapping
from app.schemas.import_batch import (
    ImportBatchRead,
    ImportPreviewResponse,
    ImportValidateRequest,
    FOSEmployeeMappingRead,
    FOSEmployeeMappingCreate,
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
        fos_mapping_overrides=payload.fos_mapping_overrides,
    )
    return await _to_read(batch, session)


@router.get("/fos-mappings", dependencies=[AdminOnly])
async def list_fos_mappings(session: DbSession):
    """List all established raw FOS name to Employee ID mappings."""
    stmt = (
        select(FOSEmployeeMapping, Employee.full_name, Employee.employee_code)
        .join(Employee, FOSEmployeeMapping.employee_id == Employee.id)
        .order_by(FOSEmployeeMapping.raw_fos_name)
    )
    res = await session.execute(stmt)
    rows = []
    for mapping, emp_name, emp_code in res.all():
        rows.append({
            "id": mapping.id,
            "raw_fos_name": mapping.raw_fos_name,
            "employee_id": mapping.employee_id,
            "employee_name": emp_name,
            "employee_code": emp_code,
            "created_at": mapping.created_at,
        })
    return rows


@router.post("/fos-mappings", response_model=FOSEmployeeMappingRead, dependencies=[AdminOnly])
async def set_fos_mapping(
    payload: FOSEmployeeMappingCreate,
    session: DbSession,
):
    """Create or update a mapping between a raw source FOS string and an Employee."""
    norm_name = payload.raw_fos_name.strip()
    res = await session.execute(
        select(FOSEmployeeMapping).where(func.lower(FOSEmployeeMapping.raw_fos_name) == func.lower(norm_name))
    )
    existing = res.scalar_one_or_none()
    if existing:
        existing.employee_id = payload.employee_id
        await session.commit()
        await session.refresh(existing)
        return existing
    else:
        new_map = FOSEmployeeMapping(
            raw_fos_name=norm_name,
            employee_id=payload.employee_id,
        )
        session.add(new_map)
        await session.commit()
        await session.refresh(new_map)
        return new_map


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


@router.get("/{batch_id}/credentials.xlsx", dependencies=[AdminOnly])
async def download_import_credentials(batch_id: uuid.UUID, session: DbSession):
    """Download the onboarding credentials Excel file generated for imported employees."""
    batch = await import_service.get_import_batch(batch_id, session)
    creds = (batch.summary or {}).get("credentials", [])
    if not creds:
        # Fallback: fetch all employees and build credentials
        res = await session.execute(
            select(Employee, User.email, User.role)
            .join(User, Employee.user_id == User.id)
            .order_by(Employee.employee_code)
        )
        for emp, email, role in res.all():
            creds.append({
                "employee_name": emp.full_name,
                "employee_id": emp.employee_code or "",
                "email": email or "",
                "temporary_password": "ProvidedSeparately",
                "application_role": role.value if role else "EMPLOYEE",
                "working_profile": emp.working_profile or "",
                "cug": emp.cug or "",
            })

    excel_bytes = import_service.generate_onboarding_excel(creds)
    return Response(
        content=excel_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="employee_onboarding_credentials_{batch_id}.xlsx"'},
    )


@router.post("/{batch_id}/commit", response_model=ImportBatchRead, dependencies=[AdminOnly])
async def commit_import(batch_id: uuid.UUID, current_user: CurrentUser, session: DbSession):
    """The only endpoint that writes to territories/employees/customers/financial_snapshots."""
    batch = await import_service.commit_import_batch(batch_id, current_user, session)
    return await _to_read(batch, session)
