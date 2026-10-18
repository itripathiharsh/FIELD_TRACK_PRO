"""
Live outlet proof endpoints - /api/v1/customers/outlet-proofs...

Registered BEFORE the customers router (see app/api/v1/router.py) so the literal
"outlet-proofs" path segment is never captured by /customers/{customer_id}.
"""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps.auth import CurrentUser, require_role
from app.database import get_async_session
from app.exceptions.custom import BaseAPIException
from app.models.user import Role
from app.schemas.outlet_proof import OutletProofRead, OutletProofRejectRequest
from app.services import customer_service, outlet_proof_service

router = APIRouter(prefix="/customers", tags=["outlet-proofs"])

DbSession = Annotated[AsyncSession, Depends(get_async_session)]
AdminOnly = Depends(require_role(Role.ADMIN))
AnyAuth = Depends(require_role(Role.ADMIN, Role.EMPLOYEE))


@router.post("/outlet-proofs", response_model=OutletProofRead, status_code=201, dependencies=[AnyAuth])
async def upload_outlet_proof(
    current_user: CurrentUser,
    session: DbSession,
    photo: UploadFile = File(..., description="Live camera photo (JPEG/PNG/WEBP, <= 10 MB)"),
    latitude: float | None = Form(default=None),
    longitude: float | None = Form(default=None),
    accuracy_m: float | None = Form(default=None),
    captured_at: str | None = Form(default=None, description="ISO-8601 with timezone, device capture time"),
    is_mock_location: bool | None = Form(default=None),
    idempotency_key: str = Form(min_length=8, max_length=100),
    device_info: str | None = Form(default=None, max_length=200),
    customer_id: uuid.UUID | None = Form(
        default=None, description="Existing outlet; omit for a NEW outlet (UNATTACHED proof, then POST /customers/prospect)"
    ),
):
    """
    Upload ONE outlet proof: the live photo and the GPS fix taken at that same click.

    * customer_id given: kind/status are derived server-side (INITIAL/PENDING, CONFIRMATION/CONFIRMED
      within the confirm radius of a verified location, or CHANGE_REQUEST/PENDING farther away).
    * customer_id omitted: UNATTACHED proof for a new outlet, valid for 48 h; pass its id as
      `outlet_proof_id` to POST /customers/prospect.
    Idempotent on (user, idempotency_key): a replay returns the stored proof with 201.
    """
    proof = await outlet_proof_service.create_outlet_proof(
        photo=photo,
        latitude=latitude,
        longitude=longitude,
        accuracy_m=accuracy_m,
        captured_at_raw=captured_at,
        is_mock_location=is_mock_location,
        device_info=device_info,
        idempotency_key=idempotency_key,
        customer_id=customer_id,
        current_user=current_user,
        session=session,
    )
    return await outlet_proof_service.to_read(proof, session)


@router.get("/outlet-proofs", response_model=list[OutletProofRead], dependencies=[AdminOnly])
async def list_outlet_proofs(
    response: Response,
    session: DbSession,
    status: str | None = Query(default=None, description="PENDING|APPROVED|REJECTED|SUPERSEDED|CONFIRMED|UNATTACHED|ALL"),
    customer_id: uuid.UUID | None = Query(default=None),
    kind: str | None = Query(default=None, description="INITIAL|CONFIRMATION|CHANGE_REQUEST"),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
):
    """Admin review queue. X-Total-Count carries the total for pagination."""
    proofs, total = await outlet_proof_service.list_outlet_proofs(
        session, status=status, customer_id=customer_id, kind=kind, skip=skip, limit=limit
    )
    response.headers["X-Total-Count"] = str(total)
    return await outlet_proof_service.to_reads(proofs, session, admin_extras=True)


@router.get("/outlet-proofs/{proof_id}/image", dependencies=[AnyAuth])
async def get_outlet_proof_image(proof_id: uuid.UUID, current_user: CurrentUser, session: DbSession):
    """Authenticated byte stream (the bucket stays private). Admin: any; employee: only their own."""
    proof = await outlet_proof_service.get_proof_for_viewer(proof_id, current_user, session)
    data = await outlet_proof_service.read_image_bytes(proof)
    return Response(
        content=data,
        media_type=proof.content_type or "image/jpeg",
        headers={"Cache-Control": "private, max-age=300", "X-Content-Type-Options": "nosniff"},
    )


@router.post("/outlet-proofs/{proof_id}/approve", response_model=OutletProofRead, dependencies=[AdminOnly])
async def approve_outlet_proof(proof_id: uuid.UUID, current_user: CurrentUser, session: DbSession):
    proof = await outlet_proof_service.approve_outlet_proof(proof_id, current_user, session)
    return await outlet_proof_service.to_read(proof, session)


@router.post("/outlet-proofs/{proof_id}/reject", response_model=OutletProofRead, dependencies=[AdminOnly])
async def reject_outlet_proof(
    proof_id: uuid.UUID, data: OutletProofRejectRequest, current_user: CurrentUser, session: DbSession
):
    proof = await outlet_proof_service.reject_outlet_proof(proof_id, data.reason, current_user, session)
    return await outlet_proof_service.to_read(proof, session)


@router.get("/{customer_id}/outlet-proofs", response_model=list[OutletProofRead], dependencies=[AnyAuth])
async def list_customer_outlet_proofs(customer_id: uuid.UUID, current_user: CurrentUser, session: DbSession):
    """Admin: every proof of this outlet. Employee: only their own, and only for outlets in their scope."""
    await customer_service.assert_employee_can_view_customer(customer_id, current_user, session)
    is_admin = current_user.is_admin
    proofs, _ = await outlet_proof_service.list_outlet_proofs(
        session, status="ALL", customer_id=customer_id,
        submitted_by=None if is_admin else current_user.id, skip=0, limit=500,
    )
    return await outlet_proof_service.to_reads(proofs, session, admin_extras=is_admin)


@router.get("/{customer_id}/outlet-image", dependencies=[AnyAuth])
async def get_customer_primary_outlet_image(customer_id: uuid.UUID, current_user: CurrentUser, session: DbSession):
    """The outlet's approved primary photo (any caller who may view the outlet). 404 when none."""
    await customer_service.assert_employee_can_view_customer(customer_id, current_user, session)
    proof = await outlet_proof_service.primary_proof_for_customer(customer_id, session)
    if proof is None:
        raise BaseAPIException(status_code=404, detail="No outlet photo yet", error_code="OUTLET_IMAGE_NOT_FOUND")
    data = await outlet_proof_service.read_image_bytes(proof)
    return Response(
        content=data,
        media_type=proof.content_type or "image/jpeg",
        headers={"Cache-Control": "private, max-age=300", "X-Content-Type-Options": "nosniff"},
    )
