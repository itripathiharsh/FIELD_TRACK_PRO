"""
Visits router — /api/v1/visits
"""
from __future__ import annotations

from datetime import datetime
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps.auth import CurrentUser, require_role
from app.database import get_async_session
from app.models.user import Role
from app.models.visit import VisitStatus
from app.schemas.geo import GeoVerificationLogRead
from app.schemas.visit import (
    BulkVisitCreate,
    CheckInRequest,
    CheckOutRequest,
    VisitCreate,
    VisitRead,
    VisitRequiredFormUpdate,
    VisitStatusUpdate,
)
from app.services import visit_service

router = APIRouter(prefix="/visits", tags=["visits"])

DbSession = Annotated[AsyncSession, Depends(get_async_session)]
AdminOnly = Depends(require_role(Role.ADMIN))
AnyAuth = Depends(require_role(Role.ADMIN, Role.EMPLOYEE))


@router.post("", response_model=VisitRead, status_code=201, dependencies=[AdminOnly])
async def create_visit(
    data: VisitCreate,
    current_user: CurrentUser,
    session: DbSession,
):
    """Admin: schedule a new visit."""
    return await visit_service.create_visit(data, current_user.id, session)


@router.get("", response_model=list[VisitRead], dependencies=[AnyAuth])
async def list_visits(
    response: Response,
    current_user: CurrentUser,
    session: DbSession,
    search: str | None = Query(default=None, description="Search by customer name, code, ID, employee name, or visit ID"),
    status: list[VisitStatus] | None = Query(default=None, description="Filter by one or multiple statuses"),
    employee_id: uuid.UUID | None = Query(default=None),
    territory_id: uuid.UUID | None = Query(default=None, description="Zone / Territory"),
    area_id: uuid.UUID | None = Query(default=None),
    from_date: datetime | None = Query(default=None, description="Scheduled on or after"),
    to_date: datetime | None = Query(default=None, description="Scheduled on or before"),
    sort_order: str = Query(default="desc", pattern="^(asc|desc|ASC|DESC)$"),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, le=200),
):
    """
    List visits with real database-level search, filtering, and deterministic sorting.

    FT-002: results are scoped to the caller. An EMPLOYEE receives only their
    own visits; an ADMIN receives all and may filter by `employee_id`.
    Returns X-Total-Count header for scalable server-side pagination.
    """
    visits, total_count = await visit_service.list_visits(
        session=session,
        current_user=current_user,
        employee_id=employee_id,
        status=status,
        territory_id=territory_id,
        area_id=area_id,
        from_date=from_date,
        to_date=to_date,
        search=search,
        sort_order=sort_order,
        skip=skip,
        limit=limit,
    )
    response.headers["X-Total-Count"] = str(total_count)
    return visits


@router.get("/me/today", response_model=list[VisitRead])
async def my_today_visits(
    response: Response,
    current_user: CurrentUser,
    session: DbSession,
    search: str | None = Query(default=None, description="Search by customer name, code, etc."),
    status: list[VisitStatus] | None = Query(default=None, description="Filter by status"),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, le=200),
):
    """Employee: get today's visits assigned to me with real server-side search, filtering and pagination."""
    visits, total_count = await visit_service.get_my_today_visits(
        current_user=current_user,
        session=session,
        status=status,
        search=search,
        skip=skip,
        limit=limit,
    )
    response.headers["X-Total-Count"] = str(total_count)
    return visits


@router.get("/{visit_id}", response_model=VisitRead, dependencies=[AnyAuth])
async def get_visit(
    visit_id: uuid.UUID,
    current_user: CurrentUser,
    session: DbSession,
):
    """FT-002: object-level ownership is enforced, not just role membership."""
    return await visit_service.get_visit_for_user(visit_id, current_user, session)


@router.post("/{visit_id}/check-in", response_model=VisitRead)
async def check_in(
    visit_id: uuid.UUID,
    data: CheckInRequest,
    current_user: CurrentUser,
    session: DbSession,
):
    """Employee: geo-verified check-in."""
    return await visit_service.check_in(visit_id, data, current_user, session)


@router.post("/{visit_id}/check-out", response_model=VisitRead)
async def check_out(
    visit_id: uuid.UUID,
    data: CheckOutRequest,
    current_user: CurrentUser,
    session: DbSession,
):
    """Employee: check-out to mark visit COMPLETED."""
    return await visit_service.check_out(visit_id, data, current_user, session)


@router.get("/{visit_id}/geo-logs", response_model=list[GeoVerificationLogRead])
async def get_visit_geo_logs(
    visit_id: uuid.UUID,
    current_user: CurrentUser,
    session: DbSession,
):
    """Retrieve immutable geo verification audit logs for a visit."""
    logs = await visit_service.get_visit_geo_logs(visit_id, current_user, session)
    return [GeoVerificationLogRead.from_model(log) for log in logs]


@router.patch("/{visit_id}/status", response_model=VisitRead, dependencies=[AdminOnly])
async def force_status(
    visit_id: uuid.UUID,
    data: VisitStatusUpdate,
    session: DbSession,
):
    """Admin: force override visit status."""
    return await visit_service.admin_force_status(visit_id, data.status, session)


@router.patch("/{visit_id}/required-form", response_model=VisitRead, dependencies=[AdminOnly])
async def set_required_form(
    visit_id: uuid.UUID,
    data: VisitRequiredFormUpdate,
    session: DbSession,
):
    """Admin: assign/change/clear the form template required for this visit."""
    return await visit_service.update_visit_required_form(visit_id, data.required_form_id, session)


@router.post("/bulk", response_model=list[VisitRead], status_code=201, dependencies=[AdminOnly])
async def bulk_create_visits(
    data: BulkVisitCreate,
    current_user: CurrentUser,
    session: DbSession,
) -> list[VisitRead]:
    """Admin: bulk schedule visits for multiple customers."""
    visits = await visit_service.bulk_create_visits(data, current_user.id, session)
    return [VisitRead.model_validate(v) for v in visits]
