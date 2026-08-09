"""
Requirement Form service — business logic for categories and form submissions.
"""
from __future__ import annotations

import logging
import uuid
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions.custom import BaseAPIException
from app.models.requirement_category import RequirementCategory
from app.models.requirement_form import Priority, RequirementForm

logger = logging.getLogger("fieldtrackpro")


class RequirementService:
    """Service managing requirement categories and form submissions."""

    @staticmethod
    async def list_categories(session: AsyncSession) -> Sequence[RequirementCategory]:
        """Return all active requirement categories."""
        result = await session.execute(
            select(RequirementCategory).where(RequirementCategory.is_active == True)
        )
        return result.scalars().all()

    @staticmethod
    async def create_category(name: str, session: AsyncSession) -> RequirementCategory:
        """Create a new requirement category."""
        category = RequirementCategory(name=name, is_active=True)
        session.add(category)
        try:
            await session.commit()
            await session.refresh(category)
            return category
        except IntegrityError:
            await session.rollback()
            raise BaseAPIException(
                status_code=409,
                detail=f"Category '{name}' already exists",
                error_code="DUPLICATE_CATEGORY",
            )

    @staticmethod
    async def submit_form(
        visit_id: uuid.UUID,
        category_id: uuid.UUID,
        description: str,
        priority: str,
        expected_timeline: str,
        budget_range: str | None = None,
        notes: str | None = None,
        session: AsyncSession | None = None,
    ) -> RequirementForm:
        """Submit a requirement form for a visit.

        Enforces uniqueness: one form per visit.
        """
        try:
            priority_enum = Priority(priority)
        except ValueError:
            raise BaseAPIException(
                status_code=422,
                detail="priority must be one of: LOW, MEDIUM, HIGH",
                error_code="INVALID_PRIORITY",
            )

        existing = await session.execute(
            select(RequirementForm).where(RequirementForm.visit_id == visit_id)
        )
        if existing.scalar_one_or_none() is not None:
            raise BaseAPIException(
                status_code=409,
                detail="A requirement form has already been submitted for this visit",
                error_code="FORM_ALREADY_EXISTS",
            )

        category = await session.execute(
            select(RequirementCategory).where(RequirementCategory.id == category_id)
        )
        if category.scalar_one_or_none() is None:
            raise BaseAPIException(
                status_code=404,
                detail="Requirement category not found",
                error_code="CATEGORY_NOT_FOUND",
            )

        form = RequirementForm(
            visit_id=visit_id,
            category_id=category_id,
            description=description,
            priority=priority_enum,
            expected_timeline=expected_timeline,
            budget_range=budget_range,
            notes=notes,
        )
        session.add(form)
        try:
            await session.commit()
            await session.refresh(form)
            return form
        except IntegrityError:
            await session.rollback()
            raise BaseAPIException(
                status_code=409,
                detail="Failed to submit requirement form",
                error_code="FORM_SUBMISSION_ERROR",
            )

    @staticmethod
    async def get_form_by_visit(
        visit_id: uuid.UUID, session: AsyncSession
    ) -> RequirementForm | None:
        """Retrieve the requirement form for a specific visit."""
        result = await session.execute(
            select(RequirementForm).where(RequirementForm.visit_id == visit_id)
        )
        return result.scalar_one_or_none()


requirement_service = RequirementService()
