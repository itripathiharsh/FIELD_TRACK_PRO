"""
Employee repository.
"""
from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import func, or_, select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.employee import Employee
from app.models.user import Role, User
from app.models.employee_area_assignment import EmployeeAreaAssignment
from app.repositories.base import BaseRepository


def _escape_like_pattern(search: str) -> str:
    escaped = search.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


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

    async def code_exists(self, employee_code: str, exclude_id: uuid.UUID | None = None) -> bool:
        clean_code = employee_code.strip().upper()
        stmt = select(Employee).where(func.upper(Employee.employee_code) == clean_code)
        if exclude_id is not None:
            stmt = stmt.where(Employee.id != exclude_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def list_with_user(
        self,
        territory_id: uuid.UUID | None = None,
        skip: int = 0,
        limit: int = 50,
        search: str | None = None,
        is_active: bool | None = None,
        role: str | None = None,
        working_profile: str | None = None,
        area_id: uuid.UUID | None = None,
    ) -> tuple[list[Employee], int]:
        filters = []

        if territory_id is not None:
            filters.append(Employee.territory_id == territory_id)

        if working_profile:
            filters.append(Employee.working_profile == working_profile)

        if is_active is not None:
            filters.append(User.is_active == is_active)

        if role:
            try:
                role_enum = Role(role.upper())
                filters.append(User.role == role_enum)
            except ValueError:
                pass

        if area_id is not None:
            filters.append(
                Employee.id.in_(
                    select(EmployeeAreaAssignment.employee_id).where(
                        EmployeeAreaAssignment.area_id == area_id
                    )
                )
            )

        if search and search.strip():
            pattern = _escape_like_pattern(search)
            filters.append(
                or_(
                    Employee.full_name.ilike(pattern, escape="\\"),
                    Employee.employee_code.ilike(pattern, escape="\\"),
                    Employee.cug.ilike(pattern, escape="\\"),
                    User.email.ilike(pattern, escape="\\"),
                    User.mobile_number.ilike(pattern, escape="\\"),
                )
            )

        count_stmt = select(func.count(Employee.id)).join(User, User.id == Employee.user_id)
        if filters:
            count_stmt = count_stmt.where(*filters)
        total_count = (await self.session.execute(count_stmt)).scalar_one()

        stmt = (
            select(Employee)
            .join(User, User.id == Employee.user_id)
            .options(selectinload(Employee.user))
        )
        if filters:
            stmt = stmt.where(*filters)

        # Deterministic ordering: created_at DESC, id DESC
        stmt = (
            stmt.order_by(Employee.created_at.desc().nullslast(), Employee.id.desc())
            .offset(skip)
            .limit(limit)
        )

        result = await self.session.execute(stmt)
        return list(result.scalars().all()), total_count
