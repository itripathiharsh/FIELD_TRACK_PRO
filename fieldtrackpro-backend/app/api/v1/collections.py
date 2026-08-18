"""
Collections Overview router — /api/v1/collections/overview

Admin-only, mirroring PaymentReviewPage/ReportsPage/ImportWizardPage: this is
a management view across every outlet, not a per-visit employee workflow.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps.auth import CurrentUser, require_role
from app.database import get_async_session
from app.models.user import Role
from app.schemas.collections import CollectionsOverviewResponse
from app.services.aging_service import AgingStatus
from app.services.collections_service import get_collections_overview

router = APIRouter(prefix="/collections", tags=["collections"], dependencies=[Depends(require_role(Role.ADMIN))])


@router.get("/overview", response_model=CollectionsOverviewResponse)
async def collections_overview(
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_async_session),
    search: str | None = Query(default=None, description="Match against outlet name or outlet code"),
    territory_id: uuid.UUID | None = Query(default=None, description="Zone"),
    area_id: uuid.UUID | None = Query(default=None),
    employee_id: uuid.UUID | None = Query(default=None),
    collection_status: AgingStatus | None = Query(default=None),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
) -> CollectionsOverviewResponse:
    """
    Outlet-list financial overview: outstanding, ageing bucket, last
    payment/visit, per outlet - the client's Excel-screenshot replacement.
    Every ageing number is computed by the same aging_service function the
    per-outlet Account Summary already uses.
    """
    return await get_collections_overview(
        session,
        search=search,
        territory_id=territory_id,
        area_id=area_id,
        employee_id=employee_id,
        collection_status=collection_status,
        skip=skip,
        limit=limit,
    )
