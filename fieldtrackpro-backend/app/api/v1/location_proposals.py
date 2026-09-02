from __future__ import annotations

import uuid
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps.auth import CurrentUser, require_role
from app.database import get_async_session
from app.models.user import Role
from app.schemas.location_proposal import (
    LocationProposalCreate,
    LocationProposalRead,
    LocationProposalReview,
)
from app.services import location_proposal_service

router = APIRouter(prefix="/location-proposals", tags=["location-proposals"])

DbSession = Annotated[AsyncSession, Depends(get_async_session)]
AdminOnly = Depends(require_role(Role.ADMIN))
AnyAuth = Depends(require_role(Role.ADMIN, Role.EMPLOYEE))


@router.get("", response_model=list[LocationProposalRead], dependencies=[AnyAuth])
async def list_location_proposals(
    session: DbSession,
    status: Optional[str] = Query(default="PENDING", description="Filter by status: PENDING, APPROVED, REJECTED, or ALL"),
    customer_id: Optional[uuid.UUID] = Query(default=None),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, le=200),
):
    """
    List customer location proposals for Admin review and audit history.
    """
    return await location_proposal_service.list_location_proposals(
        session=session,
        status=status,
        customer_id=customer_id,
        skip=skip,
        limit=limit,
    )


@router.post("/{proposal_id}/approve", response_model=LocationProposalRead, dependencies=[AdminOnly])
async def approve_location_proposal(
    proposal_id: uuid.UUID,
    current_user: CurrentUser,
    session: DbSession,
):
    """
    Admin: Approve a pending location proposal. Updates the official customer GPS coordinates.
    """
    return await location_proposal_service.approve_location_proposal(
        proposal_id=proposal_id,
        admin_user=current_user,
        session=session,
    )


@router.post("/{proposal_id}/reject", response_model=LocationProposalRead, dependencies=[AdminOnly])
async def reject_location_proposal(
    proposal_id: uuid.UUID,
    data: LocationProposalReview,
    current_user: CurrentUser,
    session: DbSession,
):
    """
    Admin: Reject a pending location proposal with reason. Official coordinates remain untouched.
    """
    return await location_proposal_service.reject_location_proposal(
        proposal_id=proposal_id,
        review_data=data,
        admin_user=current_user,
        session=session,
    )
