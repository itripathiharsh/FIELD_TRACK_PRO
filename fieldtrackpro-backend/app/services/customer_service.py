"""
Customer service — refactored to use CustomerRepository.
"""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions.custom import BaseAPIException
from app.models.customer import Customer
from app.repositories.customer_repo import CustomerRepository
from app.schemas.customer import CustomerCreate, CustomerUpdate


async def create_customer(data: CustomerCreate, created_by: uuid.UUID, session: AsyncSession) -> Customer:
    repo = CustomerRepository(session)
    customer = Customer(
        name=data.name,
        contact_number=data.contact_number,
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


def _extract_coords_from_wkt(wkt_str: str | None) -> tuple[float, float]:
    """Parse WKT POINT string 'POINT(lng lat)' into (lat, lng)."""
    if not wkt_str:
        return (0.0, 0.0)
    cleaned = str(wkt_str).replace("POINT(", "").replace(")", "").strip()
    parts = cleaned.split()
    if len(parts) >= 2:
        return float(parts[1]), float(parts[0])  # (lat, lon)
    return (0.0, 0.0)


async def verify_geo_proximity(
    customer: Customer,
    device_lat: float,
    device_lng: float,
    session: AsyncSession,
) -> tuple[bool, float]:
    """
    Calculate distance between device and customer using PostGIS or Haversine fallback.
    Returns (is_within_geofence, distance_meters).
    """
    from app.services.geo_verification_service import GeoVerificationService

    try:
        from geoalchemy2.functions import ST_Distance, ST_GeogFromText
        device_wkt = f"POINT({device_lng} {device_lat})"
        result = await session.execute(
            select(
                ST_Distance(
                    Customer.location,
                    ST_GeogFromText(device_wkt),
                )
            ).where(Customer.id == customer.id)
        )
        distance_m: float = float(result.scalar_one())
    except Exception:
        # Fallback to geodesic Haversine calculation
        cust_lat, cust_lng = _extract_coords_from_wkt(getattr(customer, "location", None))
        distance_m = GeoVerificationService.calculate_haversine_distance(
            device_lat, device_lng, cust_lat, cust_lng
        )

    is_valid = distance_m <= customer.geofence_radius_m
    return is_valid, round(distance_m, 2)
