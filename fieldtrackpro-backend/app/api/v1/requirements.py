from __future__ import annotations

import uuid
from datetime import date
from typing import Annotated, Optional

from fastapi import APIRouter, Body, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps.auth import CurrentUser, require_role
from app.database import get_async_session
from app.models.user import Role
from app.schemas.customer_requirement import (
    CustomerRequirementCreate,
    CustomerRequirementRead,
    CustomerRequirementUpdate,
    RequirementApproveRequest,
    RequirementDecisionAction,
    RequirementDecisionRequest,
    RequirementPartiallyApproveRequest,
    RequirementRejectRequest,
)
from app.services import customer_requirement_service

router = APIRouter(prefix="/requirements", tags=["requirements"])

DbSession = Annotated[AsyncSession, Depends(get_async_session)]
AdminOnly = Depends(require_role(Role.ADMIN))
AnyAuth = Depends(require_role(Role.ADMIN, Role.EMPLOYEE))


@router.get("", response_model=list[CustomerRequirementRead], dependencies=[AnyAuth])
async def list_all_requirements(
    session: DbSession,
    current_user: CurrentUser,
    brand: Optional[str] = Query(default=None, description="Filter by brand"),
    status: Optional[str] = Query(default=None, description="Filter by status (PENDING, APPROVED, PARTIALLY_APPROVED, REJECTED, FULFILLED, or ALL)"),
    customer_id: Optional[uuid.UUID] = Query(default=None, description="Filter by customer ID"),
    employee_id: Optional[uuid.UUID] = Query(default=None, description="Filter by employee/creator user ID"),
    search: Optional[str] = Query(default=None, description="Search term for product, notes, customer, or brand"),
    follow_up_date: Optional[date] = Query(default=None, description="Filter by exact follow-up date"),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, le=200),
):
    """
    List requirements across outlets for review, approval, and management.
    Employees see only requirements they submitted.
    Admins and Managers see all requirements across outlets.
    """
    creator_filter = employee_id
    if current_user.role == Role.EMPLOYEE:
        # Scoped to employee's own submitted requirements
        creator_filter = current_user.id

    return await customer_requirement_service.list_all_requirements(
        session=session,
        brand=brand,
        status=status,
        customer_id=customer_id,
        created_by=creator_filter,
        follow_up_date=follow_up_date,
        search=search,
        skip=skip,
        limit=limit,
    )


@router.get("/{requirement_id}", response_model=CustomerRequirementRead, dependencies=[AnyAuth])
async def get_requirement(
    requirement_id: uuid.UUID,
    session: DbSession,
    current_user: CurrentUser,
):
    """
    Retrieve single requirement details including requested product/quantity/value,
    admin decision, and photo URL.
    """
    req = await customer_requirement_service.get_requirement_by_id(requirement_id, session)
    if current_user.role == Role.EMPLOYEE and req.created_by != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to view this requirement",
        )
    return req


@router.post(
    "/{requirement_id}/decision",
    response_model=CustomerRequirementRead,
    dependencies=[AdminOnly],
)
async def decide_requirement(
    requirement_id: uuid.UUID,
    decision: RequirementDecisionRequest,
    current_user: CurrentUser,
    session: DbSession,
):
    """
    Admin decision on requirement: Approve, Partially Approve, or Reject.
    Preserves original employee request while recording approved quantity, value, and admin notes.
    """
    return await customer_requirement_service.decide_requirement(
        requirement_id=requirement_id,
        decision=decision,
        admin_user=current_user,
        session=session,
    )


@router.post(
    "/{requirement_id}/approve",
    response_model=CustomerRequirementRead,
    dependencies=[AdminOnly],
)
async def approve_requirement(
    requirement_id: uuid.UUID,
    current_user: CurrentUser,
    session: DbSession,
    payload: Optional[RequirementApproveRequest] = Body(default=None),
    approved_quantity: Optional[int] = Query(default=None),
    approved_value: Optional[float] = Query(default=None),
    admin_notes: Optional[str] = Query(default=None),
):
    """
    Admin helper to approve a requirement. Defaults approved quantity & value to requested.
    Supports payload via JSON request body or query parameters.
    """
    qty = payload.approved_quantity if (payload and payload.approved_quantity is not None) else approved_quantity
    val = payload.approved_value if (payload and payload.approved_value is not None) else approved_value
    notes = payload.admin_notes if (payload and payload.admin_notes is not None) else admin_notes

    decision = RequirementDecisionRequest(
        action=RequirementDecisionAction.APPROVE,
        approved_quantity=qty,
        approved_value=val,
        admin_notes=notes,
    )
    return await customer_requirement_service.decide_requirement(
        requirement_id=requirement_id,
        decision=decision,
        admin_user=current_user,
        session=session,
    )


@router.post(
    "/{requirement_id}/partially-approve",
    response_model=CustomerRequirementRead,
    dependencies=[AdminOnly],
)
async def partially_approve_requirement(
    requirement_id: uuid.UUID,
    current_user: CurrentUser,
    session: DbSession,
    payload: Optional[RequirementPartiallyApproveRequest] = Body(default=None),
    approved_quantity: Optional[int] = Query(default=None),
    approved_value: Optional[float] = Query(default=None),
    admin_notes: Optional[str] = Query(default=None),
):
    """
    Admin helper to partially approve a requirement with independent quantity, value, and notes.
    Supports payload via JSON request body or query parameters.
    """
    qty = payload.approved_quantity if (payload and payload.approved_quantity is not None) else approved_quantity
    val = payload.approved_value if (payload and payload.approved_value is not None) else approved_value
    notes = payload.admin_notes if (payload and payload.admin_notes is not None) else admin_notes

    if qty is None or qty <= 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="approved_quantity must be greater than 0",
        )
    if val is None or val <= 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="approved_value must be greater than 0",
        )

    decision = RequirementDecisionRequest(
        action=RequirementDecisionAction.PARTIALLY_APPROVE,
        approved_quantity=qty,
        approved_value=val,
        admin_notes=notes,
    )
    return await customer_requirement_service.decide_requirement(
        requirement_id=requirement_id,
        decision=decision,
        admin_user=current_user,
        session=session,
    )


@router.post(
    "/{requirement_id}/reject",
    response_model=CustomerRequirementRead,
    dependencies=[AdminOnly],
)
async def reject_requirement(
    requirement_id: uuid.UUID,
    current_user: CurrentUser,
    session: DbSession,
    payload: Optional[RequirementRejectRequest] = Body(default=None),
    admin_notes: Optional[str] = Query(default=None),
):
    """
    Admin helper to reject a requirement with reason notes.
    Supports payload via JSON request body or query parameters.
    """
    notes = payload.admin_notes if (payload and payload.admin_notes is not None) else admin_notes

    decision = RequirementDecisionRequest(
        action=RequirementDecisionAction.REJECT,
        admin_notes=notes,
    )
    return await customer_requirement_service.decide_requirement(
        requirement_id=requirement_id,
        decision=decision,
        admin_user=current_user,
        session=session,
    )


@router.post(
    "/{requirement_id}/photo",
    response_model=CustomerRequirementRead,
    dependencies=[AnyAuth],
)
async def upload_requirement_photo(
    requirement_id: uuid.UUID,
    file: UploadFile = File(...),
    current_user: CurrentUser = None,
    session: DbSession = None,
):
    """
    Upload and attach a client requirement document or photo.
    """
    file_bytes = await file.read()
    filename = file.filename or "requirement_photo.jpg"
    return await customer_requirement_service.attach_requirement_photo(
        requirement_id=requirement_id,
        file_bytes=file_bytes,
        filename=filename,
        current_user=current_user,
        session=session,
    )


@router.patch("/{requirement_id}", response_model=CustomerRequirementRead, dependencies=[AnyAuth])
async def update_requirement(
    requirement_id: uuid.UUID,
    data: CustomerRequirementUpdate,
    session: DbSession,
):
    """
    Update requirement status, notes, or details.
    """
    return await customer_requirement_service.update_requirement(
        requirement_id=requirement_id,
        data=data,
        session=session,
    )
