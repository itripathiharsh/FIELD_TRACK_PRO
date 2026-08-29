"""
Geo verification endpoints: pre-check location verification and master audit logs.
"""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps.auth import CurrentUser, require_role
from app.database import get_async_session
from app.models.user import Role
from app.schemas.geo import (
    GeoLogWithContextRead,
    GeoVerificationLogRead,
    LocationVerifyRequest,
    LocationVerifyResponse,
)
from app.services.customer_service import (
    assert_employee_can_view_customer,
    get_customer,
    verify_device_against_customer,
)

router = APIRouter(prefix="/geo", tags=["Geo Verification"])


@router.post("/verify-location", response_model=LocationVerifyResponse)
async def verify_location_endpoint(
    data: LocationVerifyRequest,
    current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> LocationVerifyResponse:
    """
    Standalone endpoint for mobile apps to pre-verify current device coordinates
    against a target customer geofence before submitting check-in/out.
    """
    await assert_employee_can_view_customer(data.customer_id, current_user, session)
    customer = await get_customer(data.customer_id, session)

    result = await verify_device_against_customer(
        customer,
        session,
        device_lat=data.latitude,
        device_lng=data.longitude,
        accuracy_m=data.accuracy_m,
        is_mock_location=data.is_mock_location,
    )

    return LocationVerifyResponse(
        is_valid=result.is_valid,
        distance_m=result.distance_m,
        geofence_radius_m=result.geofence_radius_m,
        is_mock=result.is_mock,
        accuracy_m=result.accuracy_m,
        failure_reason=result.failure_reason,
    )


@router.get(
    "/logs",
    response_model=list[GeoLogWithContextRead],
    dependencies=[Depends(require_role(Role.ADMIN))],
)
async def list_geo_logs_endpoint(
    response: Response,
    session: Annotated[AsyncSession, Depends(get_async_session)],
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, le=200),
    visit_id: uuid.UUID | None = Query(default=None),
) -> list[GeoLogWithContextRead]:
    """
    WEB-MAP-012: Admin paginated master geo verification audit log endpoint with
    customer, employee, and visit context. Prevents N+1 query fan-out.
    """
    from app.repositories.geo_log_repo import GeoLogRepository

    repo = GeoLogRepository(session)
    rows, total_count = await repo.list_paginated(skip=skip, limit=limit, visit_id=visit_id)
    response.headers["X-Total-Count"] = str(total_count)

    result = []
    for log, cust_id, cust_name, emp_id, emp_name in rows:
        base_read = GeoVerificationLogRead.from_model(log)
        result.append(
            GeoLogWithContextRead(
                **base_read.model_dump(),
                customer_id=cust_id,
                customer_name=cust_name,
                employee_id=emp_id,
                employee_name=emp_name,
            )
        )
    return result
