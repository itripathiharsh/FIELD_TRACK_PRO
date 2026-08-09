"""
Requirement Forms router: REST endpoints for categories and form submissions.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps.auth import CurrentUser
from app.database import get_async_session
from app.schemas.requirement import (
    RequirementCategoryCreate,
    RequirementCategoryRead,
    RequirementFormCreate,
    RequirementFormRead,
)
from app.services import requirement_service

router = APIRouter(tags=["Requirement Forms"])


@router.get("/requirement-categories", response_model=list[RequirementCategoryRead])
async def list_categories(
    session: AsyncSession = Depends(get_async_session),
) -> list[RequirementCategoryRead]:
    """List all active requirement categories."""
    categories = await requirement_service.list_categories(session)
    return [RequirementCategoryRead.model_validate(c) for c in categories]


@router.post(
    "/requirement-categories",
    response_model=RequirementCategoryRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_category(
    payload: RequirementCategoryCreate,
    current_user: CurrentUser = None,
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
    current_user: CurrentUser = None,
    session: AsyncSession = Depends(get_async_session),
) -> RequirementFormRead:
    """Submit a requirement form for a visit."""
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
    from sqlalchemy import select
    from app.models.requirement_category import RequirementCategory
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
    current_user: CurrentUser = None,
    session: AsyncSession = Depends(get_async_session),
) -> RequirementFormRead | None:
    """Retrieve the requirement form for a specific visit."""
    form = await requirement_service.get_form_by_visit(visit_id, session)
    if form is None:
        return None

    result = RequirementFormRead.model_validate(form)
    from sqlalchemy import select
    from app.models.requirement_category import RequirementCategory
    cat_result = await session.execute(
        select(RequirementCategory).where(RequirementCategory.id == form.category_id)
    )
    cat = cat_result.scalar_one_or_none()
    if cat:
        result.category_name = cat.name
    return result
