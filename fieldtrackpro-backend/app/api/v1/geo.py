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
from app.services.customer_service import _extract_coords_from_wkt, get_customer
from app.services.geo_verification_service import GeoVerificationService

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
    customer = await get_customer(data.customer_id, session)
    cust_lat, cust_lng = _extract_coords_from_wkt(getattr(customer, "location", None))

    result = GeoVerificationService.verify_location(
        device_lat=data.latitude,
        device_lon=data.longitude,
        target_lat=cust_lat,
        target_lon=cust_lng,
        geofence_radius_m=customer.geofence_radius_m,
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
