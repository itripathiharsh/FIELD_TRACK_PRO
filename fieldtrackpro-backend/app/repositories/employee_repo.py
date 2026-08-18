"""
Employee repository.
"""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.employee import Employee
from app.repositories.base import BaseRepository


class EmployeeRepository(BaseRepository[Employee]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Employee, session)

    async def get_with_user(self, employee_id: uuid.UUID) -> Employee | None:
        result = await self.session.execute(
            select(Employee)
            .options(selectinload(Employee.user))
            .where(Employee.id == employee_id)
        )
        return result.scalar_one_or_none()

    async def get_by_user_id(self, user_id: uuid.UUID) -> Employee | None:
        result = await self.session.execute(
            select(Employee)
            .options(selectinload(Employee.user))
            .where(Employee.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def user_has_profile(self, user_id: uuid.UUID) -> bool:
        return await self.get_by_user_id(user_id) is not None

    async def code_exists(self, employee_code: str) -> bool:
        result = await self.session.execute(
            select(Employee).where(Employee.employee_code == employee_code)
        )
        return result.scalar_one_or_none() is not None

    async def list_with_user(
        self,
        territory_id: uuid.UUID | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> list[Employee]:
        stmt = (
            select(Employee)
            .options(selectinload(Employee.user))
            .offset(skip)
            .limit(limit)
        )
        if territory_id:
            stmt = stmt.where(Employee.territory_id == territory_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
