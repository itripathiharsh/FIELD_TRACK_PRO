from __future__ import annotations

import logging
import uuid
from datetime import date
from typing import Optional

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions.custom import BaseAPIException
from app.models.customer import Customer
from app.models.customer_requirement import CustomerRequirement
from app.models.employee import Employee
from app.models.user import Role, User
from app.schemas.customer_requirement import (
    CustomerRequirementCreate,
    CustomerRequirementRead,
    CustomerRequirementUpdate,
)

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

    return CustomerRequirementRead(
        id=req.id,
        customer_id=req.customer_id,
        customer_name=customer.name if customer else None,
        outlet_code=customer.outlet_code if customer else None,
        brand=req.brand,
        requirement_type=req.requirement_type,
        product_details=req.product_details,
        quantity=req.quantity,
        expected_value=float(req.expected_value) if req.expected_value is not None else None,
        follow_up_date=req.follow_up_date,
        notes=req.notes,
        status=req.status,
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

    req_brand = data.brand
    if req_brand:
        from app.services import brand_service
        from app.schemas.brand import BrandCreate
        brand_obj = await brand_service.get_brand_by_name(session, req_brand.strip())
        if brand_obj is None:
            brand_obj = await brand_service.create_brand(session, BrandCreate(name=req_brand.strip()))
        req_brand = brand_obj.name

    req = CustomerRequirement(
        customer_id=customer_id,
        brand=req_brand,
        requirement_type=data.requirement_type,
        product_details=data.product_details,
        quantity=data.quantity,
        expected_value=data.expected_value,
        follow_up_date=data.follow_up_date,
        notes=data.notes,
        status="OPEN",
        created_by=current_user.id,
    )
    session.add(req)
    await session.commit()
    await session.refresh(req)

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
    follow_up_date: Optional[date] = None,
    skip: int = 0,
    limit: int = 50,
) -> list[CustomerRequirementRead]:
    query = select(CustomerRequirement).order_by(CustomerRequirement.created_at.desc())

    if brand:
        query = query.where(CustomerRequirement.brand.ilike(f"%{brand}%"))
    if status and status.upper() != "ALL":
        query = query.where(CustomerRequirement.status == status.upper())
    if follow_up_date:
        query = query.where(CustomerRequirement.follow_up_date == follow_up_date)

    query = query.offset(skip).limit(limit)
    res = await session.execute(query)
    reqs = res.scalars().all()
    return [await _enrich_requirement_read(r, session) for r in reqs]


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
        req.expected_value = data.expected_value
    if data.follow_up_date is not None:
        req.follow_up_date = data.follow_up_date
    if data.notes is not None:
        req.notes = data.notes
    if data.status is not None:
        req.status = data.status.upper()

    session.add(req)
    await session.commit()
    await session.refresh(req)

    return await _enrich_requirement_read(req, session)
