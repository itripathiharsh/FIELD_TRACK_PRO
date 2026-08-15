"""
Geo verification endpoints: pre-check location verification and GIS utilities.
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps.auth import CurrentUser
from app.database import get_async_session
from app.schemas.geo import LocationVerifyRequest, LocationVerifyResponse
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

    FT-004: shares the exact verification path used by check-in and check-out,
    so a positive pre-check cannot disagree with the real submission.

    P0-1: scoped the same way as the base customer profile - an EMPLOYEE can
    only pre-check proximity against an outlet they have a visit assigned to.
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
