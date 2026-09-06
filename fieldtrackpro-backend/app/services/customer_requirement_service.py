from __future__ import annotations

import logging
import mimetypes
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import select, or_, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions.custom import BaseAPIException
from app.models.customer import Customer
from app.models.customer_requirement import CustomerRequirement
from app.models.employee import Employee
from app.models.user import Role, User
from app.models.visit import Visit
from app.models.visit_media import MediaType, VisitMedia
from app.schemas.customer_requirement import (
    CustomerRequirementCreate,
    CustomerRequirementRead,
    CustomerRequirementUpdate,
    RequirementDecisionAction,
    RequirementDecisionRequest,
)
from app.services.media_service import _compress_image
from app.services.storage_service import storage_service

logger = logging.getLogger("fieldtrackpro")


async def _enrich_requirement_read(
    req: CustomerRequirement,
    session: AsyncSession,
) -> CustomerRequirementRead:
    cust_res = await session.execute(select(Customer).where(Customer.id == req.customer_id))
    customer = cust_res.scalar_one_or_none()

    creator_name = None
    if req.created_by:
        user_res = await session.execute(select(User).where(User.id == req.created_by))
        user = user_res.scalar_one_or_none()
        if user:
            emp_res = await session.execute(select(Employee).where(Employee.user_id == user.id))
            emp = emp_res.scalar_one_or_none()
            creator_name = emp.full_name if emp else user.email

    decider_name = None
    if req.decided_by:
        d_user_res = await session.execute(select(User).where(User.id == req.decided_by))
        d_user = d_user_res.scalar_one_or_none()
        if d_user:
            d_emp_res = await session.execute(select(Employee).where(Employee.user_id == d_user.id))
            d_emp = d_emp_res.scalar_one_or_none()
            decider_name = d_emp.full_name if d_emp else d_user.email

    visit_date = None
    if req.visit_id:
        v_res = await session.execute(select(Visit).where(Visit.id == req.visit_id))
        visit = v_res.scalar_one_or_none()
        if visit and visit.scheduled_at:
            visit_date = visit.scheduled_at.date()

    # Generate presigned URL for photo if available
    photo_url = None
    storage_key = req.photo_storage_key
    if not storage_key and req.photo_media_id:
        vm_res = await session.execute(select(VisitMedia).where(VisitMedia.id == req.photo_media_id))
        vm = vm_res.scalar_one_or_none()
        if vm:
            storage_key = vm.storage_key

    if storage_key:
        try:
            photo_url = await storage_service.generate_presigned_url(storage_key, expiry_minutes=60)
        except Exception as ex:
            logger.warning(f"Failed to generate presigned URL for requirement {req.id}: {ex}")

    # Standardize legacy OPEN status to PENDING
    status_display = req.status
    if status_display.upper() == "OPEN":
        status_display = "PENDING"

    return CustomerRequirementRead(
        id=req.id,
        customer_id=req.customer_id,
        customer_name=customer.name if customer else None,
        outlet_code=customer.outlet_code if customer else None,
        visit_id=req.visit_id,
        visit_date=visit_date,
        brand=req.brand,
        requirement_type=req.requirement_type,
        product_details=req.product_details,
        quantity=req.quantity,
        expected_value=float(req.expected_value) if req.expected_value is not None else None,
        follow_up_date=req.follow_up_date,
        notes=req.notes,
        photo_storage_key=storage_key,
        photo_media_id=req.photo_media_id,
        photo_url=photo_url,
        status=status_display,
        approved_quantity=req.approved_quantity,
        approved_value=float(req.approved_value) if req.approved_value is not None else None,
        admin_notes=req.admin_notes,
        decided_by=req.decided_by,
        decider_name=decider_name,
        decided_at=req.decided_at,
        created_by=req.created_by,
        creator_name=creator_name,
        created_at=req.created_at,
        updated_at=req.updated_at,
    )


async def create_requirement(
    customer_id: uuid.UUID,
    data: CustomerRequirementCreate,
    current_user: User,
    session: AsyncSession,
) -> CustomerRequirementRead:
    cust_res = await session.execute(select(Customer).where(Customer.id == customer_id))
    if cust_res.scalar_one_or_none() is None:
        raise BaseAPIException(
            status_code=404,
            detail="Customer not found",
            error_code="CUSTOMER_NOT_FOUND",
        )

    # Optional visit validation
    visit_id = data.visit_id
    if visit_id:
        v_res = await session.execute(select(Visit).where(Visit.id == visit_id))
        if v_res.scalar_one_or_none() is None:
            raise BaseAPIException(
                status_code=404,
                detail="Visit not found",
                error_code="VISIT_NOT_FOUND",
            )

    req_brand = data.brand
    if req_brand:
        from app.services import brand_service
        from app.schemas.brand import BrandCreate
        brand_obj = await brand_service.get_brand_by_name(session, req_brand.strip())
        if brand_obj is None:
            brand_obj = await brand_service.create_brand(session, BrandCreate(name=req_brand.strip()))
        req_brand = brand_obj.name

    photo_storage_key = None
    if data.photo_media_id:
        vm_res = await session.execute(select(VisitMedia).where(VisitMedia.id == data.photo_media_id))
        vm = vm_res.scalar_one_or_none()
        if vm:
            photo_storage_key = vm.storage_key

    req = CustomerRequirement(
        customer_id=customer_id,
        visit_id=visit_id,
        brand=req_brand,
        requirement_type=data.requirement_type,
        product_details=data.product_details,
        quantity=data.quantity,
        expected_value=data.expected_value,
        follow_up_date=data.follow_up_date,
        notes=data.notes,
        photo_media_id=data.photo_media_id,
        photo_storage_key=photo_storage_key,
        status="PENDING",
        created_by=current_user.id,
    )
    session.add(req)
    await session.commit()
    await session.refresh(req)

    return await _enrich_requirement_read(req, session)


async def get_requirement_by_id(
    requirement_id: uuid.UUID,
    session: AsyncSession,
) -> CustomerRequirementRead:
    res = await session.execute(
        select(CustomerRequirement).where(CustomerRequirement.id == requirement_id)
    )
    req = res.scalar_one_or_none()
    if req is None:
        raise BaseAPIException(
            status_code=404,
            detail="Requirement not found",
            error_code="REQUIREMENT_NOT_FOUND",
        )
    return await _enrich_requirement_read(req, session)


async def list_requirements_for_customer(
    customer_id: uuid.UUID,
    session: AsyncSession,
) -> list[CustomerRequirementRead]:
    query = (
        select(CustomerRequirement)
        .where(CustomerRequirement.customer_id == customer_id)
        .order_by(CustomerRequirement.created_at.desc())
    )
    res = await session.execute(query)
    reqs = res.scalars().all()
    return [await _enrich_requirement_read(r, session) for r in reqs]


async def list_all_requirements(
    session: AsyncSession,
    brand: Optional[str] = None,
    status: Optional[str] = None,
    customer_id: Optional[uuid.UUID] = None,
    created_by: Optional[uuid.UUID] = None,
    follow_up_date: Optional[date] = None,
    search: Optional[str] = None,
    skip: int = 0,
    limit: int = 50,
) -> list[CustomerRequirementRead]:
    query = select(CustomerRequirement).order_by(CustomerRequirement.created_at.desc())

    if customer_id:
        query = query.where(CustomerRequirement.customer_id == customer_id)
    if created_by:
        query = query.where(CustomerRequirement.created_by == created_by)
    if brand:
        query = query.where(CustomerRequirement.brand.ilike(f"%{brand}%"))
    if follow_up_date:
        query = query.where(CustomerRequirement.follow_up_date == follow_up_date)

    if status and status.upper() != "ALL":
        target_status = status.upper()
        if target_status == "PENDING":
            query = query.where(
                or_(
                    CustomerRequirement.status == "PENDING",
                    CustomerRequirement.status == "OPEN",
                )
            )
        else:
            query = query.where(CustomerRequirement.status == target_status)

    if search and search.strip():
        term = f"%{search.strip()}%"
        # Join Customer to search customer name as well
        query = query.join(Customer, CustomerRequirement.customer_id == Customer.id, isouter=True)
        query = query.where(
            or_(
                CustomerRequirement.product_details.ilike(term),
                CustomerRequirement.notes.ilike(term),
                CustomerRequirement.brand.ilike(term),
                Customer.name.ilike(term),
            )
        )

    query = query.offset(skip).limit(limit)
    res = await session.execute(query)
    reqs = res.scalars().all()
    return [await _enrich_requirement_read(r, session) for r in reqs]


async def decide_requirement(
    requirement_id: uuid.UUID,
    decision: RequirementDecisionRequest,
    admin_user: User,
    session: AsyncSession,
) -> CustomerRequirementRead:
    """
    Approve, Partially Approve, or Reject a requirement.
    Preserves original employee request while recording admin decision independently.
    """
    res = await session.execute(
        select(CustomerRequirement).where(CustomerRequirement.id == requirement_id)
    )
    req = res.scalar_one_or_none()
    if req is None:
        raise BaseAPIException(
            status_code=404,
            detail="Requirement not found",
            error_code="REQUIREMENT_NOT_FOUND",
        )

    action = decision.action
    now_utc = datetime.now(timezone.utc)

    if action == RequirementDecisionAction.APPROVE:
        req.status = "APPROVED"
        # Default approved quantity and value to requested if not explicitly overridden
        req.approved_quantity = (
            decision.approved_quantity if decision.approved_quantity is not None else req.quantity
        )
        req.approved_value = (
            Decimal(str(decision.approved_value))
            if decision.approved_value is not None
            else req.expected_value
        )
        if decision.admin_notes:
            req.admin_notes = decision.admin_notes.strip()

    elif action == RequirementDecisionAction.PARTIALLY_APPROVE:
        if decision.approved_quantity is None:
            raise BaseAPIException(
                status_code=400,
                detail="Approved quantity is required for partial approval",
                error_code="APPROVED_QUANTITY_REQUIRED",
            )
        req.status = "PARTIALLY_APPROVED"
        req.approved_quantity = decision.approved_quantity
        req.approved_value = (
            Decimal(str(decision.approved_value))
            if decision.approved_value is not None
            else req.expected_value
        )
        req.admin_notes = decision.admin_notes.strip() if decision.admin_notes else None

    elif action == RequirementDecisionAction.REJECT:
        req.status = "REJECTED"
        req.admin_notes = decision.admin_notes.strip() if decision.admin_notes else None
        req.approved_quantity = None
        req.approved_value = None

    req.decided_by = admin_user.id
    req.decided_at = now_utc

    await session.commit()
    await session.refresh(req)
    return await _enrich_requirement_read(req, session)


async def attach_requirement_photo(
    requirement_id: uuid.UUID,
    file_bytes: bytes,
    filename: str,
    current_user: User,
    session: AsyncSession,
) -> CustomerRequirementRead:
    """
    Attaches a client requirement photo to the requirement.
    Compresses image and saves to object storage.
    """
    res = await session.execute(
        select(CustomerRequirement).where(CustomerRequirement.id == requirement_id)
    )
    req = res.scalar_one_or_none()
    if req is None:
        raise BaseAPIException(
            status_code=404,
            detail="Requirement not found",
            error_code="REQUIREMENT_NOT_FOUND",
        )

    # Validate and compress
    mime_type = mimetypes.guess_type(filename)[0] or "image/jpeg"
    compressed_bytes = _compress_image(file_bytes)

    # Storage key convention: requirements/{req_id}/{uuid}_{filename}
    file_id = uuid.uuid4().hex[:8]
    clean_filename = filename.replace(" ", "_")
    storage_key = f"requirements/{req.id}/{file_id}_{clean_filename}"

    await storage_service.upload(compressed_bytes, storage_key, mime_type)

    req.photo_storage_key = storage_key

    # If linked to a visit, also cross-register with visit_media
    if req.visit_id:
        import hashlib
        checksum = hashlib.sha256(compressed_bytes).hexdigest()
        visit_media = VisitMedia(
            visit_id=req.visit_id,
            media_type=MediaType.ORDER,
            storage_key=storage_key,
            file_size_bytes=len(compressed_bytes),
            checksum_sha256=checksum,
            original_filename=clean_filename,
            note=f"Client Requirement Photo (Req: {req.id})",
            uploaded_by=current_user.id,
        )
        session.add(visit_media)
        await session.flush()
        req.photo_media_id = visit_media.id

    await session.commit()
    await session.refresh(req)
    return await _enrich_requirement_read(req, session)


async def update_requirement(
    requirement_id: uuid.UUID,
    data: CustomerRequirementUpdate,
    session: AsyncSession,
) -> CustomerRequirementRead:
    res = await session.execute(
        select(CustomerRequirement).where(CustomerRequirement.id == requirement_id)
    )
    req = res.scalar_one_or_none()
    if req is None:
        raise BaseAPIException(
            status_code=404,
            detail="Requirement not found",
            error_code="REQUIREMENT_NOT_FOUND",
        )

    if data.brand is not None:
        req.brand = data.brand
    if data.requirement_type is not None:
        req.requirement_type = data.requirement_type
    if data.product_details is not None:
        req.product_details = data.product_details
    if data.quantity is not None:
        req.quantity = data.quantity
    if data.expected_value is not None:
        req.expected_value = Decimal(str(data.expected_value))
    if data.follow_up_date is not None:
        req.follow_up_date = data.follow_up_date
    if data.notes is not None:
        req.notes = data.notes
    if data.status is not None:
        req.status = data.status.upper()

    await session.commit()
    await session.refresh(req)
    return await _enrich_requirement_read(req, session)
