"""
User repository.
"""
from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(User, session)

    async def get_by_email(self, email: str) -> User | None:
        cleaned = email.strip()
        result = await self.session.execute(
            select(User).where(func.lower(User.email) == func.lower(cleaned))
        )
        return result.scalar_one_or_none()

    async def get_by_mobile(self, mobile: str) -> User | None:
        cleaned = mobile.strip()
        result = await self.session.execute(
            select(User).where(User.mobile_number == cleaned)
        )
        return result.scalar_one_or_none()

    async def email_exists(self, email: str) -> bool:
        return await self.get_by_email(email) is not None

    async def mobile_exists(self, mobile: str) -> bool:
        return await self.get_by_mobile(mobile) is not None
