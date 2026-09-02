from __future__ import annotations

import re
import uuid
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions.custom import BaseAPIException
from app.models.brand import Brand
from app.schemas.brand import BrandCreate, BrandUpdate


# Centralized alias mapping from external/legacy identifiers to canonical normalized brand keys
BRAND_ALIASES: dict[str, str] = {
    "zbr": "zebronics",
    "zebronics": "zebronics",
    "usha": "usha",
    "vu": "vu",
}

# Master canonical casing lookup
CANONICAL_BRAND_DISPLAY: dict[str, str] = {
    "zebronics": "Zebronics",
    "usha": "USHA",
    "vu": "VU",
    "havells": "Havells",
    "finolex": "Finolex",
    "anchor": "Anchor",
}


def normalize_brand_name(name: str) -> str:
    """Normalize a brand name by stripping leading/trailing whitespace, collapsing internal spaces, and lowercasing."""
    if not name:
        return ""
    cleaned = re.sub(r"\s+", " ", name.strip())
    return cleaned.lower()


def resolve_canonical_brand_name(name: str) -> str:
    """
    Resolve any brand name, alias (e.g. 'ZBR', 'zbr', 'usha'), or casing variant
    to its canonical master brand display name ('Zebronics', 'USHA', 'VU').
    If unknown, returns stripped original name.
    """
    if not name:
        return ""
    normalized = normalize_brand_name(name)
    resolved_key = BRAND_ALIASES.get(normalized, normalized)
    return CANONICAL_BRAND_DISPLAY.get(resolved_key, name.strip())


async def resolve_brand(session: AsyncSession, name: str) -> Optional[Brand]:
    """
    Retrieve an authoritative master Brand instance by resolving any alias or casing variant.
    """
    if not name:
        return None
    normalized = normalize_brand_name(name)
    resolved_key = BRAND_ALIASES.get(normalized, normalized)
    result = await session.execute(select(Brand).where(Brand.normalized_name == resolved_key))
    return result.scalar_one_or_none()


async def list_brands(session: AsyncSession, active_only: bool = True) -> list[Brand]:
    """List all registered brands, ordered alphabetically."""
    query = select(Brand).order_by(Brand.name.asc())
    if active_only:
        query = query.where(Brand.is_active.is_(True))
    result = await session.execute(query)
    return list(result.scalars().all())


async def get_brand_by_id(session: AsyncSession, brand_id: uuid.UUID) -> Optional[Brand]:
    """Retrieve a brand by its UUID."""
    result = await session.execute(select(Brand).where(Brand.id == brand_id))
    return result.scalar_one_or_none()


async def get_brand_by_name(session: AsyncSession, name: str) -> Optional[Brand]:
    """Retrieve a brand by its name (resolving aliases like ZBR -> Zebronics)."""
    return await resolve_brand(session, name)


async def create_brand(session: AsyncSession, data: BrandCreate) -> Brand:
    """
    Create a new master brand.
    Enforces case-insensitive duplicate prevention.
    """
    raw_name = data.name.strip()
    if not raw_name:
        raise BaseAPIException(
            status_code=422,
            detail="Brand name cannot be empty.",
            error_code="INVALID_BRAND_NAME",
        )

    normalized = normalize_brand_name(raw_name)
    if normalized == "lund":
        raise BaseAPIException(
            status_code=422,
            detail="Invalid brand name.",
            error_code="INVALID_BRAND_NAME",
        )

    # If brand already exists, reject with 409 duplicate
    existing = await get_brand_by_name(session, raw_name)
    if existing is not None:
        raise BaseAPIException(
            status_code=409,
            detail=f"Brand '{existing.name}' already exists.",
            error_code="BRAND_ALREADY_EXISTS",
        )

    new_brand = Brand(
        name=raw_name,
        normalized_name=normalized,
        is_active=True,
    )
    session.add(new_brand)
    await session.flush()
    return new_brand


async def update_brand(session: AsyncSession, brand_id: uuid.UUID, data: BrandUpdate) -> Brand:
    """Update brand properties (name, active status)."""
    brand = await get_brand_by_id(session, brand_id)
    if brand is None:
        raise BaseAPIException(
            status_code=404,
            detail=f"Brand with id '{brand_id}' not found.",
            error_code="BRAND_NOT_FOUND",
        )

    if data.name is not None:
        new_name = data.name.strip()
        if not new_name:
            raise BaseAPIException(
                status_code=422,
                detail="Brand name cannot be empty.",
                error_code="INVALID_BRAND_NAME",
            )
        normalized = normalize_brand_name(new_name)
        if normalized == "lund":
            raise BaseAPIException(
                status_code=422,
                detail="Invalid brand name.",
                error_code="INVALID_BRAND_NAME",
            )
        if normalized != brand.normalized_name:
            existing = await get_brand_by_name(session, new_name)
            if existing is not None and existing.id != brand.id:
                raise BaseAPIException(
                    status_code=409,
                    detail="This brand already exists.",
                    error_code="BRAND_ALREADY_EXISTS",
                )
            brand.name = new_name
            brand.normalized_name = normalized

    if data.is_active is not None:
        brand.is_active = data.is_active

    await session.flush()
    return brand


async def validate_brand_for_transaction(session: AsyncSession, brand_name: str) -> Brand:
    """
    Validate that a brand exists and is active for transactions (e.g. payment allocations).
    Raises 422/404 if invalid or inactive.
    """
    brand = await get_brand_by_name(session, brand_name)
    if brand is None:
        raise BaseAPIException(
            status_code=422,
            detail=f"Brand '{brand_name}' does not exist. Please add the brand first.",
            error_code="UNKNOWN_BRAND",
        )
    if not brand.is_active:
        raise BaseAPIException(
            status_code=422,
            detail=f"Brand '{brand.name}' is inactive and cannot be used for new transactions.",
            error_code="INACTIVE_BRAND",
        )
    return brand
