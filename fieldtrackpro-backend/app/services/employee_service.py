"""
Employee service — refactored to use EmployeeRepository.
"""
from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions.custom import BaseAPIException, DuplicateResourceException
from app.models.employee import Employee
from app.repositories.employee_repo import EmployeeRepository
from app.repositories.user_repo import UserRepository
from app.schemas.employee import EmployeeCreate, EmployeeUpdate


async def create_employee(data: EmployeeCreate, session: AsyncSession) -> Employee:
    user_repo = UserRepository(session)
    emp_repo = EmployeeRepository(session)

    if await user_repo.get_by_id(data.user_id) is None:
        raise BaseAPIException(status_code=404, detail="User not found", error_code="USER_NOT_FOUND")
    if await emp_repo.user_has_profile(data.user_id):
        raise DuplicateResourceException("Employee profile already exists for this user")

    employee = Employee(
        user_id=data.user_id,
        full_name=data.full_name,
        territory_id=data.territory_id,
        employee_code=data.employee_code,
    )
    await emp_repo.add(employee)
    await emp_repo.commit()
    return employee


async def get_employee(employee_id: uuid.UUID, session: AsyncSession) -> Employee:
    repo = EmployeeRepository(session)
    emp = await repo.get_with_user(employee_id)
    if emp is None:
        raise BaseAPIException(status_code=404, detail="Employee not found", error_code="EMPLOYEE_NOT_FOUND")
    return emp


async def get_employee_by_user_id(user_id: uuid.UUID, session: AsyncSession) -> Employee:
    repo = EmployeeRepository(session)
    emp = await repo.get_by_user_id(user_id)
    if emp is None:
        raise BaseAPIException(status_code=404, detail="Employee profile not found", error_code="EMPLOYEE_NOT_FOUND")
    return emp


async def list_employees(
    session: AsyncSession,
    territory_id: uuid.UUID | None = None,
    skip: int = 0,
    limit: int = 50,
) -> list[Employee]:
    repo = EmployeeRepository(session)
    return await repo.list_with_user(territory_id, skip, limit)


async def update_employee(employee_id: uuid.UUID, data: EmployeeUpdate, session: AsyncSession) -> Employee:
    emp = await get_employee(employee_id, session)
    if data.full_name is not None:
        emp.full_name = data.full_name
    if data.territory_id is not None:
        emp.territory_id = data.territory_id
    if data.employee_code is not None:
        emp.employee_code = data.employee_code
    session.add(emp)
    await session.commit()
    await session.refresh(emp)
    return emp
