"""
Customer service — refactored to use CustomerRepository.
"""
from __future__ import annotations

import re
import uuid
from typing import Any

from geoalchemy2.elements import WKBElement, WKTElement
from geoalchemy2.shape import to_shape
from shapely.wkb import loads as wkb_loads
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions.custom import BaseAPIException
from app.models.customer import Customer
from app.repositories.customer_repo import CustomerRepository
from app.schemas.customer import CustomerCreate, CustomerUpdate

# Matches "POINT(lng lat)" and "SRID=4326;POINT(lng lat)".
_WKT_POINT_RE = re.compile(
    r"^(?:SRID=\d+;)?\s*POINT\s*\(\s*(?P<lng>-?\d+(?:\.\d+)?)\s+(?P<lat>-?\d+(?:\.\d+)?)\s*\)$",
    re.IGNORECASE,
)


async def create_customer(data: CustomerCreate, created_by: uuid.UUID, session: AsyncSession) -> Customer:
    repo = CustomerRepository(session)
    customer = Customer(
        name=data.name,
        contact_number=data.contact_number,
        contact_person=data.contact_person,
        address=data.address,
        location=data.location.to_wkt(),
        geofence_radius_m=data.geofence_radius_m,
        territory_id=data.territory_id,
        created_by=created_by,
    )
    await repo.add(customer)
    await repo.commit()
    return customer


async def get_customer(customer_id: uuid.UUID, session: AsyncSession) -> Customer:
    repo = CustomerRepository(session)
    c = await repo.get_by_id(customer_id)
    if c is None:
        raise BaseAPIException(status_code=404, detail="Customer not found", error_code="CUSTOMER_NOT_FOUND")
    return c


async def list_customers(
    session: AsyncSession,
    territory_id: uuid.UUID | None = None,
    skip: int = 0,
    limit: int = 50,
) -> list[Customer]:
    repo = CustomerRepository(session)
    return await repo.list_by_territory(territory_id, skip, limit)


async def update_customer(customer_id: uuid.UUID, data: CustomerUpdate, session: AsyncSession) -> Customer:
    customer = await get_customer(customer_id, session)
    if data.name is not None:
        customer.name = data.name
    if data.contact_number is not None:
        customer.contact_number = data.contact_number
    if data.contact_person is not None:
        customer.contact_person = data.contact_person
    if data.address is not None:
        customer.address = data.address
    if data.location is not None:
        customer.location = data.location.to_wkt()
    if data.geofence_radius_m is not None:
        customer.geofence_radius_m = data.geofence_radius_m
    if data.territory_id is not None:
        customer.territory_id = data.territory_id
    session.add(customer)
    await session.commit()
    await session.refresh(customer)
    return customer


def extract_coords(location: Any) -> tuple[float, float]:
    """
    Return ``(latitude, longitude)`` for a stored customer/device location.

    FT-004 (CRITICAL). The previous implementation assumed the value was a WKT
    string ``POINT(lng lat)``. SQLAlchemy actually hands back a geoalchemy2
    ``WKBElement`` whose ``str()`` is hex-encoded WKB
    (``0101000000e78c28ed...``). Parsing that as WKT failed, and the function
    silently returned ``(0.0, 0.0)`` - so every geofence check was measured
    against Null Island. The effect was an *inverted* geofence: standing on the
    customer's doorstep was rejected as ~8,663 km away, while a check-in from
    the Gulf of Guinea was accepted.

    This version understands the representations that actually occur and
    **raises** when a location cannot be interpreted. A security-critical
    parse must never degrade to a permissive default (repair rule 9).

    Accepted inputs:
      * ``WKBElement``            - decoded via geoalchemy2's shapely bridge
      * ``"POINT(lng lat)"``      - EWKT/WKT text, optionally ``SRID=4326;``
      * hex WKB string            - decoded via shapely
      * ``(lat, lng)`` mapping/tuple with explicit keys

    Raises
    ------
    ValueError
        If *location* is None, empty, or cannot be decoded to a coordinate.
    """
    if location is None:
        raise ValueError("Location is not set; cannot determine coordinates")

    # 1. Native geoalchemy2 element (the normal ORM path).
    if isinstance(location, (WKBElement, WKTElement)):
        point = to_shape(location)
        return float(point.y), float(point.x)  # shapely: x=lng, y=lat

    # 2. Explicit mapping, e.g. from a request payload.
    if isinstance(location, dict):
        try:
            return float(location["latitude"]), float(location["longitude"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"Unrecognised location mapping: {location!r}") from exc

    text = str(location).strip()
    if not text:
        raise ValueError("Location is empty; cannot determine coordinates")

    # 3. WKT / EWKT text.
    match = _WKT_POINT_RE.match(text)
    if match:
        lng, lat = float(match.group("lng")), float(match.group("lat"))
        return lat, lng

    # 4. Hex-encoded WKB text.
    try:
        point = wkb_loads(bytes.fromhex(text))
        return float(point.y), float(point.x)
    except Exception as exc:
        raise ValueError(f"Unrecognised location value: {text[:64]!r}") from exc


def _extract_coords_from_wkt(location: Any) -> tuple[float, float]:
    """Backwards-compatible alias for :func:`extract_coords`."""
    return extract_coords(location)


async def measure_distance_to_customer(
    customer: Customer,
    device_lat: float,
    device_lng: float,
    session: AsyncSession,
) -> float:
    """
    Return the geodesic distance in metres between a device position and the
    customer's stored geofence centre.

    PostGIS is the source of truth: ``ST_Distance`` on ``geography(POINT, 4326)``
    returns metres on the WGS-84 spheroid, which is more accurate than a
    spherical Haversine approximation and uses the exact value held in the
    database rather than a re-parsed copy of it.

    FT-004: the previous implementation wrapped this in a bare ``except`` that
    fell back to Haversine over coordinates produced by a parser that always
    failed - so the fallback silently measured from ``(0, 0)``. There is no
    silent fallback now: a spatial failure propagates and the caller rejects
    the attempt rather than approving it on bad data.
    """
    from geoalchemy2.functions import ST_Distance, ST_GeogFromText

    device_wkt = f"SRID=4326;POINT({device_lng} {device_lat})"
    result = await session.execute(
        select(ST_Distance(Customer.location, ST_GeogFromText(device_wkt))).where(
            Customer.id == customer.id
        )
    )
    distance = result.scalar_one_or_none()
    if distance is None:
        raise ValueError(
            f"Unable to compute distance for customer {customer.id}: no stored location"
        )
    return round(float(distance), 2)


async def verify_geo_proximity(
    customer: Customer,
    device_lat: float,
    device_lng: float,
    session: AsyncSession,
) -> tuple[bool, float]:
    """
    Return ``(is_within_geofence, distance_metres)`` using PostGIS.

    Kept as the single proximity helper used by the geo verification service.
    """
    distance_m = await measure_distance_to_customer(customer, device_lat, device_lng, session)
    return distance_m <= customer.geofence_radius_m, distance_m


async def verify_device_against_customer(
    customer: Customer,
    session: AsyncSession,
    *,
    device_lat: float,
    device_lng: float,
    accuracy_m: float | None = None,
    is_mock_location: bool = False,
):
    """
    Single entry point for "is this device at this customer's site?".

    Used by check-in, check-out and ``POST /geo/verify-location`` so all three
    apply the same rules to the same PostGIS-derived distance. Returns a
    :class:`GeoVerificationResult`.

    FT-004: coordinate range and mock/accuracy rules are evaluated first, so an
    out-of-range coordinate is rejected before it reaches PostGIS. The distance
    itself always comes from the database.
    """
    from app.services.geo_verification_service import GeoVerificationService

    coordinates_in_range = -90.0 <= device_lat <= 90.0 and -180.0 <= device_lng <= 180.0

    measured: float | None = None
    if coordinates_in_range:
        measured = await measure_distance_to_customer(
            customer, device_lat, device_lng, session
        )

    # Target coordinates are reported for context/logging only; the decision
    # uses `measured`, which PostGIS computed from the stored geography.
    target_lat, target_lng = extract_coords(getattr(customer, "location", None))

    return GeoVerificationService.verify_location(
        device_lat=device_lat,
        device_lon=device_lng,
        target_lat=target_lat,
        target_lon=target_lng,
        geofence_radius_m=customer.geofence_radius_m,
        accuracy_m=accuracy_m,
        is_mock_location=is_mock_location,
        measured_distance_m=measured,
    )
