"""
Signature repository: data access operations for VisitSignature entity.
Follows: Router -> Service -> Repository -> DB
"""
from __future__ import annotations

import uuid
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.visit_signature import VisitSignature
from app.repositories.base import BaseRepository


class SignatureRepository(BaseRepository[VisitSignature]):
    """Repository handling database operations for VisitSignature."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(VisitSignature, session)

    async def list_by_visit(self, visit_id: uuid.UUID) -> Sequence[VisitSignature]:
        """Fetch all signatures attached to a specific visit."""
        result = await self.session.execute(
            select(VisitSignature)
            .where(VisitSignature.visit_id == visit_id)
            .order_by(VisitSignature.signed_at.desc())
        )
        return result.scalars().all()

    async def find_current_by_visit_and_type(
        self, visit_id: uuid.UUID, signature_type: str
    ) -> VisitSignature | None:
        """Return the CURRENT (not superseded/replaced) signature of this type for this visit, if any."""
        result = await self.session.execute(
            select(VisitSignature).where(
                VisitSignature.visit_id == visit_id,
                VisitSignature.signature_type == signature_type,
                VisitSignature.superseded_at.is_(None),
            )
        )
        return result.scalar_one_or_none()
