"""
Requirement Forms router: REST endpoints for categories and form submissions.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps.auth import CurrentUser, require_role
from app.database import get_async_session
from app.models.requirement_category import RequirementCategory
from app.models.user import Role
from app.models.visit import Visit
from app.schemas.requirement import (
    RequirementCategoryCreate,
    RequirementCategoryRead,
    RequirementFormCreate,
    RequirementFormRead,
)
from app.services import requirement_service
from app.services.visit_service import assert_visit_access, get_visit_for_user

router = APIRouter(tags=["Requirement Forms"])

AdminOnly = Depends(require_role(Role.ADMIN))
AnyAuth = Depends(require_role(Role.ADMIN, Role.EMPLOYEE))


@router.get("/requirement-categories", response_model=list[RequirementCategoryRead], dependencies=[AnyAuth])
async def list_categories(
    session: AsyncSession = Depends(get_async_session),
) -> list[RequirementCategoryRead]:
    """List all active requirement categories."""
    try:
        categories = await requirement_service.list_categories(session)
        return [RequirementCategoryRead.model_validate(c) for c in categories]
    except Exception as e:
        import logging
        logging.getLogger("fieldtrackpro").exception("Failed to list categories: %s", e)
        raise


@router.post(
    "/requirement-categories",
    response_model=RequirementCategoryRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[AdminOnly],
)
async def create_category(
    payload: RequirementCategoryCreate,
    session: AsyncSession = Depends(get_async_session),
) -> RequirementCategoryRead:
    """Create a new requirement category (admin-only)."""
    category = await requirement_service.create_category(payload.name, session)
    return RequirementCategoryRead.model_validate(category)


@router.post(
    "/visits/{visit_id}/requirement-form",
    response_model=RequirementFormRead,
    status_code=status.HTTP_201_CREATED,
)
async def submit_form(
    visit_id: uuid.UUID,
    payload: RequirementFormCreate,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_async_session),
) -> RequirementFormRead:
    """Submit a requirement form for a visit.

    Employees may only submit a form for a visit assigned to them.
    Admins may submit for any visit.
    """
    # P2-1: single authoritative visit-ownership check (was reimplemented
    # inline here) - raises 404 VISIT_NOT_FOUND / 403 VISIT_NOT_ASSIGNED
    # exactly as before.
    await get_visit_for_user(visit_id, current_user, session)

    form = await requirement_service.submit_form(
        visit_id=visit_id,
        category_id=payload.category_id,
        description=payload.description,
        priority=payload.priority,
        expected_timeline=payload.expected_timeline,
        budget_range=payload.budget_range,
        notes=payload.notes,
        session=session,
    )

    # Load category name for response
    result = RequirementFormRead.model_validate(form)
    cat_result = await session.execute(
        select(RequirementCategory).where(RequirementCategory.id == form.category_id)
    )
    cat = cat_result.scalar_one_or_none()
    if cat:
        result.category_name = cat.name
    return result


@router.get(
    "/visits/{visit_id}/requirement-form",
    response_model=RequirementFormRead | None,
)
async def get_form(
    visit_id: uuid.UUID,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_async_session),
) -> RequirementFormRead | None:
    """Retrieve the requirement form for a specific visit.

    Employees may only read forms for visits assigned to them.
    Admins may read any form.
    """
    visit_result = await session.execute(select(Visit).where(Visit.id == visit_id))
    visit = visit_result.scalar_one_or_none()

    # Existence check stays inline (a missing visit here falls through to a
    # 200 with a null form, not a 404 - unlike submit_form above). Only the
    # ownership comparison itself (P2-1) delegates to the single
    # authoritative implementation in visit_service.
    if visit is not None:
        await assert_visit_access(visit, current_user, session)

    form = await requirement_service.get_form_by_visit(visit_id, session)
    if form is None:
        return None

    result = RequirementFormRead.model_validate(form)
    cat_result = await session.execute(
        select(RequirementCategory).where(RequirementCategory.id == form.category_id)
    )
    cat = cat_result.scalar_one_or_none()
    if cat:
        result.category_name = cat.name
    return result
