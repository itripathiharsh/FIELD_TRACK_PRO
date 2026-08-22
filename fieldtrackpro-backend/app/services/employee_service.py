"""
Employee service — refactored to support business Working Profile, CUG, DOB, and Address.
"""
from __future__ import annotations

import uuid
from datetime import date
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from sqlalchemy import select, func

from app.core.security import hash_password
from app.exceptions.custom import BaseAPIException, DuplicateResourceException
from app.models.employee import Employee
from app.models.user import User
from app.models.employee_customer_assignment import EmployeeCustomerAssignment
from app.repositories.employee_repo import EmployeeRepository
from app.repositories.user_repo import UserRepository
from app.repositories.token_repo import TokenRepository
from app.schemas.employee import EmployeeCreate, EmployeeRegistration, EmployeeUpdate


async def register_employee(data: EmployeeRegistration, session: AsyncSession) -> Employee:
    user_repo = UserRepository(session)
    emp_repo = EmployeeRepository(session)

    clean_email = data.user.email.strip().lower() if data.user.email else None
    clean_mobile = data.user.mobile_number.strip() if data.user.mobile_number else None

    if not clean_email and not clean_mobile:
        raise BaseAPIException(
            status_code=422,
            detail="email or mobile_number is required",
            error_code="USER_IDENTITY_REQUIRED",
        )
    if clean_email and await user_repo.email_exists(clean_email):
        raise DuplicateResourceException(f"Email '{clean_email}' is already in use. Please enter a unique email.")
    if clean_mobile and await user_repo.mobile_exists(clean_mobile):
        raise DuplicateResourceException(f"Mobile number '{clean_mobile}' is already in use. Please enter a unique mobile number.")
    if data.employee_code and await emp_repo.code_exists(data.employee_code):
        raise DuplicateResourceException(f"Employee code '{data.employee_code}' is already in use. Please enter a unique employee code.")

    user = User(
        email=clean_email,
        mobile_number=clean_mobile,
        password_hash=hash_password(data.user.password),
        role=data.user.role,
    )
    session.add(user)

    employee = Employee(
        user=user,
        full_name=data.full_name,
        territory_id=data.territory_id,
        employee_code=data.employee_code,
        working_profile=data.working_profile,
        cug=data.cug,
        date_of_birth=data.date_of_birth,
        address=data.address,
    )
    session.add(employee)

    try:
        await session.commit()
    except IntegrityError as e:
        await session.rollback()
        err_msg = str(e.orig).lower()
        if "employee_code" in err_msg:
            raise DuplicateResourceException(f"Employee code '{data.employee_code}' is already in use. Please enter a unique employee code.")
        elif "email" in err_msg:
            raise DuplicateResourceException(f"Email '{data.user.email}' is already in use. Please enter a unique email.")
        elif "mobile" in err_msg or "mobile_number" in err_msg:
            raise DuplicateResourceException(f"Mobile number '{data.user.mobile_number}' is already in use. Please enter a unique mobile number.")
        raise BaseAPIException(status_code=409, detail="Database conflict occurred.", error_code="DB_CONFLICT")

    await session.refresh(employee, ["user"])
    return employee


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
        working_profile=data.working_profile,
        cug=data.cug,
        date_of_birth=data.date_of_birth,
        address=data.address,
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
    if "territory_id" in data.model_fields_set:
        emp.territory_id = data.territory_id
    if data.employee_code is not None:
        emp.employee_code = data.employee_code
    if data.working_profile is not None:
        emp.working_profile = data.working_profile
    if data.cug is not None:
        emp.cug = data.cug
    if data.date_of_birth is not None:
        emp.date_of_birth = data.date_of_birth
    if data.address is not None:
        emp.address = data.address
    if data.must_change_password is not None:
        emp.must_change_password = data.must_change_password

    if data.email is not None and data.email != emp.user.email:
        user_repo = UserRepository(session)
        if await user_repo.email_exists(data.email):
            raise DuplicateResourceException(f"Email '{data.email}' is already in use.")
        emp.user.email = data.email
        session.add(emp.user)
        await TokenRepository(session).revoke_all_for_user(emp.user.id)

    if data.mobile_number is not None and data.mobile_number != emp.user.mobile_number:
        user_repo = UserRepository(session)
        if await user_repo.mobile_exists(data.mobile_number):
            raise DuplicateResourceException(f"Mobile number '{data.mobile_number}' is already in use.")
        emp.user.mobile_number = data.mobile_number
        session.add(emp.user)

    session.add(emp)
    await session.commit()
    await session.refresh(emp)
    return emp
