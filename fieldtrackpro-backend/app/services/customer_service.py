"""
Customer service — refactored to use CustomerRepository with support for location_status and nullable GPS.
"""
from __future__ import annotations

import re
import uuid
from typing import Any

from geoalchemy2.elements import WKBElement, WKTElement
from geoalchemy2.shape import to_shape
from shapely.wkb import loads as wkb_loads
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.exceptions.custom import BaseAPIException
from app.models.customer import Customer
from app.models.user import Role, User
from app.models.visit import Visit
from app.models.employee_customer_assignment import EmployeeCustomerAssignment
from app.repositories.customer_repo import CustomerRepository
from app.schemas.customer import CustomerCreate, CustomerUpdate
from app.services.employee_service import get_employee_by_user_id
from app.services.geocoding_service import GeocodingError, geocode_address

_WKT_POINT_RE = re.compile(
    r"^(?:SRID=\d+;)?\s*POINT\s*\(\s*(?P<lng>-?\d+(?:\.\d+)?)\s+(?P<lat>-?\d+(?:\.\d+)?)\s*\)$",
    re.IGNORECASE,
)


async def create_customer(data: CustomerCreate, created_by: uuid.UUID, session: AsyncSession) -> Customer:
    repo = CustomerRepository(session)

    location_wkt = None
    loc_status = data.location_status or "MISSING"
    if data.location is not None:
        location_wkt = data.location.to_wkt()
        loc_status = "VERIFIED"
    elif data.auto_geocode and data.address:
        try:
            lat, lng = await geocode_address(data.address)
            location_wkt = f"POINT({lng} {lat})"
            loc_status = "VERIFIED"
        except GeocodingError:
            loc_status = "NEEDS_REVIEW"

    territory_id = data.territory_id
    if data.area_id is not None:
        from app.services.area_service import get_area
        area = await get_area(data.area_id, session)
        territory_id = area.territory_id

    customer = Customer(
        name=data.name,
        contact_number=data.contact_number,
        contact_person=data.contact_person,
        address=data.address,
        location=location_wkt,
        geofence_radius_m=data.geofence_radius_m,
        location_status=loc_status,
        territory_id=territory_id,
        area_id=data.area_id,
        outlet_code=data.outlet_code,
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
    current_user: User,
    territory_id: uuid.UUID | None = None,
    skip: int = 0,
    limit: int = 50,
    area_id: uuid.UUID | None = None,
) -> list[Customer]:
    repo = CustomerRepository(session)

    if current_user.role == Role.ADMIN:
        return await repo.list_by_territory(territory_id, skip, limit, area_id)

    employee = await get_employee_by_user_id(current_user.id, session)
    return await repo.list_visited_by_employee(employee.id, territory_id, skip, limit, area_id)


async def assert_employee_can_view_customer(
    customer_id: uuid.UUID, current_user: User, session: AsyncSession
) -> None:
    if current_user.role == Role.ADMIN:
        return

    employee = await get_employee_by_user_id(current_user.id, session)
    count = await session.scalar(
        select(func.count())
        .select_from(Visit)
        .where(Visit.customer_id == customer_id, Visit.employee_id == employee.id)
    )
    if not count:
        raise BaseAPIException(
            status_code=403,
            detail="You have no visit assigned to this outlet",
            error_code="OUTLET_NOT_ASSIGNED",
        )


async def update_customer(
    customer_id: uuid.UUID, data: CustomerUpdate, session: AsyncSession
) -> Customer:
    customer = await get_customer(customer_id, session)
    if data.name is not None:
        customer.name = data.name
    if data.contact_number is not None:
        customer.contact_number = data.contact_number
    if "contact_person" in data.model_fields_set:
        customer.contact_person = data.contact_person
    if data.address is not None:
        customer.address = data.address
    if data.location is not None:
        customer.location = data.location.to_wkt()
        customer.location_status = "VERIFIED"
    elif data.auto_geocode and data.address:
        try:
            lat, lng = await geocode_address(data.address)
            customer.location = f"POINT({lng} {lat})"
            customer.location_status = "VERIFIED"
        except GeocodingError as e:
            raise BaseAPIException(
                status_code=422,
                detail=e.message,
                error_code=e.reason,
            )
    if data.location_status is not None:
        customer.location_status = data.location_status
    if data.geofence_radius_m is not None:
        customer.geofence_radius_m = data.geofence_radius_m
    if "area_id" in data.model_fields_set:
        if data.area_id is not None:
            from app.services.area_service import get_area
            area = await get_area(data.area_id, session)
            customer.area_id = data.area_id
            customer.territory_id = area.territory_id
        else:
            customer.area_id = None
            if "territory_id" in data.model_fields_set:
                customer.territory_id = data.territory_id
    elif "territory_id" in data.model_fields_set:
        customer.territory_id = data.territory_id
    if "outlet_code" in data.model_fields_set:
        customer.outlet_code = data.outlet_code

    session.add(customer)
    await session.commit()
    await session.refresh(customer)
    return customer


def extract_coords(location: Any) -> tuple[float, float]:
    if location is None:
        return 0.0, 0.0

    if isinstance(location, (WKBElement, WKTElement)):
        point = to_shape(location)
        return float(point.y), float(point.x)

    if isinstance(location, dict):
        try:
            return float(location["latitude"]), float(location["longitude"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"Unrecognised location mapping: {location!r}") from exc

    text = str(location).strip()
    if not text:
        return 0.0, 0.0

    match = _WKT_POINT_RE.match(text)
    if match:
        lng, lat = float(match.group("lng")), float(match.group("lat"))
        return lat, lng

    try:
        point = wkb_loads(bytes.fromhex(text))
        return float(point.y), float(point.x)
    except Exception as exc:
        raise ValueError(f"Unrecognised location value: {text[:64]!r}") from exc


def _extract_coords_from_wkt(location: Any) -> tuple[float, float]:
    return extract_coords(location)


async def measure_distance_to_customer(
    customer: Customer,
    device_lat: float,
    device_lng: float,
    session: AsyncSession,
) -> float:
    if customer.location is None:
        raise ValueError(f"Unable to compute distance for customer {customer.id}: no stored location")
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
    captured_at=None,
):
    from app.services.geo_verification_service import GeoVerificationService

    coordinates_in_range = -90.0 <= device_lat <= 90.0 and -180.0 <= device_lng <= 180.0
    measured: float | None = None
    if coordinates_in_range and customer.location is not None:
        measured = await measure_distance_to_customer(customer, device_lat, device_lng, session)

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
        captured_at=captured_at,
    )
