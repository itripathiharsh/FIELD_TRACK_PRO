from __future__ import annotations
from typing import Annotated
from fastapi import APIRouter, Depends
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.deps.auth import require_role
from app.database import get_async_session
from app.models.area import Area
from app.models.brand import Brand
from app.models.customer import Customer
from app.models.employee import Employee
from app.models.territory import Territory
from app.models.user import Role
from app.schemas.organization import OrganizationProfile

router = APIRouter(prefix="/organization", tags=["organization"])
DbSession = Annotated[AsyncSession, Depends(get_async_session)]
AnyAuth = Depends(require_role(Role.ADMIN, Role.EMPLOYEE))


@router.get("", response_model=OrganizationProfile, dependencies=[AnyAuth])
async def get_organization_profile(session: DbSession) -> OrganizationProfile:
    """
    Returns authoritative, dynamic organization profile & master entity statistics.
    Single source of truth for Web & Android clients.
    """
    emp_count = (await session.execute(select(func.count(Employee.id)))).scalar() or 0
    cust_count = (await session.execute(select(func.count(Customer.id)))).scalar() or 0
    terr_count = (await session.execute(select(func.count(Territory.id)))).scalar() or 0
    area_count = (await session.execute(select(func.count(Area.id)))).scalar() or 0

    # Dynamically fetch active master brands from database
    brand_res = await session.execute(
        select(Brand.name).where(Brand.is_active == True).order_by(Brand.name)
    )
    master_brands = [name for name in brand_res.scalars().all()]

    return OrganizationProfile(
        organization_name=settings.organization_name,
        operational_hub=settings.organization_hub,
        divisions=settings.organization_divisions,
        contact_email=settings.organization_contact_email,
        contact_phone=settings.organization_contact_phone,
        gstin=settings.organization_gstin,
        timezone=settings.organization_timezone,
        currency=settings.organization_currency,
        total_employees=emp_count,
        total_customers=cust_count,
        total_territories=terr_count,
        total_areas=area_count,
        master_brands=master_brands,
    )
