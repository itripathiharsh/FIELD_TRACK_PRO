"""
Customer service — refactored to use CustomerRepository with support for location_status and nullable GPS.
"""
from __future__ import annotations

import logging
import re
import uuid
from typing import Any

import math
from geoalchemy2.elements import WKBElement, WKTElement
from geoalchemy2.shape import to_shape
from shapely.wkb import loads as wkb_loads
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.context import get_current_request_id
from app.exceptions.custom import BaseAPIException
from app.models.customer import Customer
from app.models.customer_brand import CustomerBrand
from app.models.customer_location_proposal import CustomerLocationProposal, LocationProposalStatus
from app.models.customer_requirement import CustomerRequirement
from app.models.employee import Employee
from app.models.user import Role, User
from app.models.visit import Visit
from app.models.employee_customer_assignment import EmployeeCustomerAssignment
from app.repositories.customer_repo import CustomerRepository
from app.schemas.customer import CustomerCreate, CustomerProspectCreate, CustomerUpdate
from app.services.employee_service import get_employee_by_user_id
from app.services.geocoding_service import GeocodingError, geocode_address

logger = logging.getLogger("fieldtrackpro")

_WKT_POINT_RE = re.compile(
    r"^(?:SRID=\d+;)?\s*POINT\s*\(\s*(?P<lng>-?\d+(?:\.\d+)?)\s+(?P<lat>-?\d+(?:\.\d+)?)\s*\)$",
    re.IGNORECASE,
)

DEFAULT_MASTER_BRANDS = ["USHA", "Zebronics", "VU", "Havells", "Finolex", "Anchor"]


def calculate_distance_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Haversine formula for calculating distance between two coordinates in meters."""
    R = 6371000.0  # Earth's radius in meters
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_phi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
    )
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return round(R * c, 2)


async def get_master_brands(session: AsyncSession) -> list[str]:
    """Returns the list of master brands from the authoritative brands table."""
    from app.services import brand_service
    brands = await brand_service.list_brands(session, active_only=True)
    return [b.name for b in brands]


async def list_customers(
    session: AsyncSession,
    current_user: User,
    territory_id: uuid.UUID | None = None,
    skip: int = 0,
    limit: int = 50,
    area_id: uuid.UUID | None = None,
    search: str | None = None,
) -> tuple[list[Customer], int]:
    repo = CustomerRepository(session)
    if current_user.role == Role.EMPLOYEE:
        try:
            emp = await get_employee_by_user_id(current_user.id, session)
            return await repo.list_visited_by_employee(
                emp.id,
                territory_id=territory_id,
                skip=skip,
                limit=limit,
                area_id=area_id,
                search=search,
            )
        except BaseAPIException:
            # Fallback to directory search if employee record is unlinked
            return await repo.list_by_territory(
                territory_id=territory_id,
                skip=skip,
                limit=limit,
                area_id=area_id,
                search=search,
            )
    return await repo.list_by_territory(
        territory_id=territory_id,
        skip=skip,
        limit=limit,
        area_id=area_id,
        search=search,
    )



async def create_customer(data: CustomerCreate, created_by: uuid.UUID, session: AsyncSession) -> Customer:
    repo = CustomerRepository(session)

    cleaned_outlet_code = data.outlet_code.strip().upper() if data.outlet_code else None
    if cleaned_outlet_code:
        existing = await repo.get_by_outlet_code(cleaned_outlet_code)
        if existing is not None:
            raise BaseAPIException(
                status_code=409,
                detail=f"A customer with DMS Code '{cleaned_outlet_code}' already exists.",
                error_code="OUTLET_CODE_EXISTS",
            )

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
        gst_number=data.gst_number,
        address=data.address,
        location=location_wkt,
        geofence_radius_m=data.geofence_radius_m,
        location_status=loc_status,
        territory_id=territory_id,
        area_id=data.area_id,
        outlet_code=cleaned_outlet_code,
        created_by=created_by,
    )
    try:
        await repo.add(customer)
        await session.flush()

        if data.brands:
            from app.services import brand_service
            from app.schemas.brand import BrandCreate
            for brand_name in data.brands:
                b_stripped = brand_name.strip()
                if b_stripped:
                    brand_obj = await brand_service.get_brand_by_name(session, b_stripped)
                    if brand_obj is None:
                        brand_obj = await brand_service.create_brand(session, BrandCreate(name=b_stripped))
                    cb = CustomerBrand(
                        customer_id=customer.id,
                        brand=brand_obj.name,
                        brand_id=brand_obj.id,
                        is_active=True,
                    )
                    session.add(cb)

        await repo.commit()
        await session.refresh(customer)
    except IntegrityError as exc:
        await session.rollback()
        if "outlet_code" in str(exc).lower():
            logger.warning(
                "event=customer_create result=rejected reason=OUTLET_CODE_EXISTS request_id=%s outlet_code=%s",
                get_current_request_id(),
                cleaned_outlet_code,
            )
            raise BaseAPIException(
                status_code=409,
                detail=f"A customer with DMS Code '{cleaned_outlet_code}' already exists.",
                error_code="OUTLET_CODE_EXISTS",
            ) from exc
        raise

    logger.info(
        "event=customer_create result=success request_id=%s customer_id=%s name=%s outlet_code=%s",
        get_current_request_id(),
        customer.id,
        customer.name,
        customer.outlet_code or "-",
    )
    return customer


async def create_customer_prospect(
    data: CustomerProspectCreate,
    current_user: User,
    session: AsyncSession,
) -> Customer:
    """
    Onboards a new customer / outlet from field sales with duplicate protection,
    brand association, requirement logging, and pending location proposal.
    """
    repo = CustomerRepository(session)
    req_id = get_current_request_id()

    # 1. Duplicate check (unless force=True)
    if not data.force:
        dup_conditions = []
        if data.contact_number:
            dup_conditions.append(Customer.contact_number == data.contact_number)
        if data.gst_number:
            dup_conditions.append(Customer.gst_number == data.gst_number)
        if data.outlet_code:
            dup_conditions.append(Customer.outlet_code == data.outlet_code.strip().upper())

        if dup_conditions:
            dup_res = await session.execute(
                select(Customer).where(or_(*dup_conditions)).limit(1)
            )
            dup_cust = dup_res.scalar_one_or_none()
            if dup_cust is not None:
                logger.warning(
                    "event=customer_prospect_create result=rejected reason=DUPLICATE_CUSTOMER request_id=%s name=%s duplicate_of=%s",
                    req_id,
                    data.name,
                    dup_cust.id,
                )
                raise BaseAPIException(
                    status_code=409,
                    detail=f"Possible existing customer found: '{dup_cust.name}' (Phone: {dup_cust.contact_number}, GST: {dup_cust.gst_number or 'N/A'}).",
                    error_code="DUPLICATE_CUSTOMER",
                )

    cleaned_outlet_code = data.outlet_code.strip().upper() if data.outlet_code else None

    # 2. Location & Status Handling
    # For an Admin, coordinates entered directly are official & VERIFIED immediately.
    # For field employees, coordinates are submitted as PENDING_APPROVAL until admin review.
    is_admin = getattr(current_user, "role", None) in (Role.ADMIN, "ADMIN")
    if is_admin and data.location is not None:
        official_location = from_shape(Point(data.location.longitude, data.location.latitude), srid=4326)
        loc_status = "VERIFIED"
    else:
        official_location = None
        loc_status = "PENDING_APPROVAL" if data.location is not None else "MISSING"

    territory_id = data.territory_id
    if data.area_id is not None:
        from app.services.area_service import get_area
        area = await get_area(data.area_id, session)
        territory_id = area.territory_id

    customer = Customer(
        name=data.name,
        contact_number=data.contact_number,
        contact_person=data.contact_person,
        gst_number=data.gst_number,
        address=data.address,
        location=official_location,
        geofence_radius_m=75,
        location_status=loc_status,
        territory_id=territory_id,
        area_id=data.area_id,
        outlet_code=cleaned_outlet_code,
        created_by=current_user.id,
    )
    await repo.add(customer)
    await session.flush()

    # 3. Resolve employee ID if user is employee
    employee_id = None
    if current_user.role == Role.EMPLOYEE:
        emp_res = await session.execute(
            select(Employee).where(Employee.user_id == current_user.id)
        )
        emp = emp_res.scalar_one_or_none()
        if emp:
            employee_id = emp.id
            # Also create employee assignment so the employee can view/visit their prospect
            assignment = EmployeeCustomerAssignment(
                employee_id=employee_id,
                customer_id=customer.id,
                created_by=current_user.id,
            )
            session.add(assignment)

    # 4. Create Location Proposal if coordinates were captured
    if data.location is not None:
        proposal = CustomerLocationProposal(
            customer_id=customer.id,
            proposed_latitude=data.location.latitude,
            proposed_longitude=data.location.longitude,
            gps_accuracy_meters=data.gps_accuracy_meters,
            submitted_by=current_user.id,
            submitted_by_employee_id=employee_id,
            notes=data.notes or ("Official coordinates recorded during admin outlet creation." if is_admin else "Initial location captured during outlet onboarding."),
            status=LocationProposalStatus.APPROVED if is_admin else LocationProposalStatus.PENDING,
            reviewed_by=current_user.id if is_admin else None,
            reviewed_at=func.now() if is_admin else None,
        )
        session.add(proposal)

    # 5. Associate Brands
    if data.brands:
        from app.services import brand_service
        from app.schemas.brand import BrandCreate
        for brand_name in data.brands:
            b_stripped = brand_name.strip()
            if b_stripped:
                brand_obj = await brand_service.get_brand_by_name(session, b_stripped)
                if brand_obj is None:
                    brand_obj = await brand_service.create_brand(session, BrandCreate(name=b_stripped))
                cb = CustomerBrand(
                    customer_id=customer.id,
                    brand=brand_obj.name,
                    brand_id=brand_obj.id,
                    is_active=True,
                )
                session.add(cb)

    # 6. Create Customer Requirement if provided
    if data.requirement is not None:
        req_brand = data.requirement.brand
        if req_brand:
            from app.services import brand_service
            from app.schemas.brand import BrandCreate
            req_b_obj = await brand_service.get_brand_by_name(session, req_brand.strip())
            if req_b_obj is None:
                req_b_obj = await brand_service.create_brand(session, BrandCreate(name=req_brand.strip()))
            req_brand = req_b_obj.name

        req = CustomerRequirement(
            customer_id=customer.id,
            brand=req_brand,
            requirement_type=data.requirement.requirement_type,
            product_details=data.requirement.product_details,
            quantity=data.requirement.quantity,
            expected_value=data.requirement.expected_value,
            follow_up_date=data.requirement.follow_up_date,
            notes=data.requirement.notes,
            status="OPEN",
            created_by=current_user.id,
        )
        session.add(req)

    await session.commit()
    await session.refresh(customer)

    logger.info(
        "event=customer_prospect_create result=success request_id=%s customer_id=%s name=%s employee_id=%s has_location=%s",
        req_id,
        customer.id,
        customer.name,
        employee_id or "-",
        data.location is not None,
    )
    return customer



async def get_customer(customer_id: uuid.UUID, session: AsyncSession) -> Customer:
    repo = CustomerRepository(session)
    customer = await repo.get_by_id(customer_id)
    if customer is None:
        raise BaseAPIException(
            status_code=404,
            detail=f"Customer with id '{customer_id}' not found.",
            error_code="CUSTOMER_NOT_FOUND",
        )
    return customer


async def assert_employee_can_view_customer(
    customer_id: uuid.UUID, current_user: User, session: AsyncSession
) -> None:
    # Authenticated employees and admins can view active customer details to support off-beat / ad-hoc visits
    await get_customer(customer_id, session)


async def update_customer(
    customer_id: uuid.UUID, data: CustomerUpdate, session: AsyncSession
) -> Customer:
    repo = CustomerRepository(session)
    customer = await get_customer(customer_id, session)
    if data.name is not None:
        customer.name = data.name
    if data.contact_number is not None:
        customer.contact_number = data.contact_number
    if "contact_person" in data.model_fields_set:
        customer.contact_person = data.contact_person
    if "gst_number" in data.model_fields_set:
        customer.gst_number = data.gst_number
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
        cleaned_code = data.outlet_code.strip().upper() if data.outlet_code else None
        if cleaned_code:
            existing = await repo.get_by_outlet_code(cleaned_code, exclude_id=customer_id)
            if existing is not None:
                raise BaseAPIException(
                    status_code=409,
                    detail=f"A customer with DMS Code '{cleaned_code}' already exists.",
                    error_code="OUTLET_CODE_EXISTS",
                )
        customer.outlet_code = cleaned_code

    if data.brands is not None:
        from app.services import brand_service
        from app.models.customer_brand import CustomerBrand
        from sqlalchemy import delete

        # Safely remove existing brand allocations directly to avoid constraint collisions
        await session.execute(delete(CustomerBrand).where(CustomerBrand.customer_id == customer_id))
        await session.flush()
        session.expire(customer, ["brands"])

        seen_brands: set[str] = set()
        for brand_name in data.brands:
            b_stripped = brand_name.strip()
            if not b_stripped:
                continue
            brand_obj = await brand_service.ensure_brand(session, b_stripped)
            canonical = brand_obj.name if brand_obj else b_stripped
            norm = brand_obj.normalized_name if brand_obj else b_stripped.lower()
            if norm not in seen_brands:
                seen_brands.add(norm)
                session.add(CustomerBrand(
                    customer_id=customer_id,
                    brand=canonical,
                    brand_id=brand_obj.id if brand_obj else None,
                    is_active=True,
                ))
        await session.flush()

    try:
        session.add(customer)
        await session.commit()
        await session.refresh(customer, ["brands", "location_proposals", "requirements"])
    except IntegrityError as exc:
        await session.rollback()
        if "outlet_code" in str(exc).lower():
            code_display = data.outlet_code or ""
            raise BaseAPIException(
                status_code=409,
                detail=f"A customer with DMS Code '{code_display}' already exists.",
                error_code="OUTLET_CODE_EXISTS",
            ) from exc
        raise
    return customer


async def list_customer_map_locations(
    session: AsyncSession,
    territory_id: uuid.UUID | None = None,
    area_id: uuid.UUID | None = None,
) -> list[Customer]:
    repo = CustomerRepository(session)
    return await repo.list_map_locations(territory_id=territory_id, area_id=area_id)


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

    if customer.location is None:
        from app.services.geo_verification_service import GeoVerificationResult
        return GeoVerificationResult(
            is_valid=False,
            distance_m=0.0,
            geofence_radius_m=customer.geofence_radius_m or 100.0,
            is_mock=is_mock_location,
            accuracy_m=accuracy_m,
            failure_reason="Customer location not configured",
        )

    coordinates_in_range = -90.0 <= device_lat <= 90.0 and -180.0 <= device_lng <= 180.0
    measured: float | None = None
    if coordinates_in_range:
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
