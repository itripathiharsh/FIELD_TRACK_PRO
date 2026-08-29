"""
Employee service — refactored to support business Working Profile, CUG, DOB, Address, and server-side pagination.
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
    clean_code = data.employee_code.strip().upper() if data.employee_code else None

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
    if clean_code and await emp_repo.code_exists(clean_code):
        raise DuplicateResourceException(f"Employee code '{clean_code}' is already in use. Please enter a unique employee code.")

    user = User(
        email=clean_email,
        mobile_number=clean_mobile,
        password_hash=hash_password(data.user.password),
        role=data.user.role,
    )
    session.add(user)

    employee = Employee(
        user=user,
        full_name=data.full_name.strip(),
        territory_id=data.territory_id,
        employee_code=clean_code,
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
            raise DuplicateResourceException(f"Employee code '{clean_code}' is already in use. Please enter a unique employee code.")
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

    clean_code = data.employee_code.strip().upper() if data.employee_code else None
    if clean_code and await emp_repo.code_exists(clean_code):
        raise DuplicateResourceException(f"Employee code '{clean_code}' is already in use. Please enter a unique employee code.")

    employee = Employee(
        user_id=data.user_id,
        full_name=data.full_name.strip(),
        territory_id=data.territory_id,
        employee_code=clean_code,
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
    search: str | None = None,
    is_active: bool | None = None,
    role: str | None = None,
    working_profile: str | None = None,
    area_id: uuid.UUID | None = None,
) -> tuple[list[Employee], int]:
    repo = EmployeeRepository(session)
    return await repo.list_with_user(
        territory_id=territory_id,
        skip=skip,
        limit=limit,
        search=search,
        is_active=is_active,
        role=role,
        working_profile=working_profile,
        area_id=area_id,
    )


async def update_employee(employee_id: uuid.UUID, data: EmployeeUpdate, session: AsyncSession) -> Employee:
    repo = EmployeeRepository(session)
    emp = await get_employee(employee_id, session)

    if data.full_name is not None:
        emp.full_name = data.full_name.strip()

    if "territory_id" in data.model_fields_set:
        emp.territory_id = data.territory_id
        from app.services.employee_area_service import prune_invalid_area_assignments
        await prune_invalid_area_assignments(employee_id, session)

    if "employee_code" in data.model_fields_set:
        clean_code = data.employee_code.strip().upper() if data.employee_code else None
        if clean_code:
            if await repo.code_exists(clean_code, exclude_id=employee_id):
                raise BaseAPIException(
                    status_code=409,
                    detail=f"Employee code '{clean_code}' is already in use.",
                    error_code="EMPLOYEE_CODE_EXISTS",
                )
        emp.employee_code = clean_code

    if "working_profile" in data.model_fields_set:
        emp.working_profile = data.working_profile

    if "cug" in data.model_fields_set:
        emp.cug = data.cug

    if "date_of_birth" in data.model_fields_set:
        emp.date_of_birth = data.date_of_birth

    if "address" in data.model_fields_set:
        emp.address = data.address

    if data.must_change_password is not None:
        emp.must_change_password = data.must_change_password

    if "email" in data.model_fields_set:
        clean_email = data.email.strip().lower() if data.email else None
        if clean_email and clean_email != emp.user.email:
            user_repo = UserRepository(session)
            if await user_repo.email_exists(clean_email):
                raise BaseAPIException(
                    status_code=409,
                    detail=f"Email '{clean_email}' is already in use.",
                    error_code="EMAIL_EXISTS",
                )
            emp.user.email = clean_email
            session.add(emp.user)
            await TokenRepository(session).revoke_all_for_user(emp.user.id)
        elif clean_email is None and emp.user.email is not None:
            emp.user.email = None
            session.add(emp.user)

    if "mobile_number" in data.model_fields_set:
        clean_mobile = data.mobile_number.strip() if data.mobile_number else None
        if clean_mobile and clean_mobile != emp.user.mobile_number:
            user_repo = UserRepository(session)
            if await user_repo.mobile_exists(clean_mobile):
                raise BaseAPIException(
                    status_code=409,
                    detail=f"Mobile number '{clean_mobile}' is already in use.",
                    error_code="MOBILE_EXISTS",
                )
            emp.user.mobile_number = clean_mobile
            session.add(emp.user)
        elif clean_mobile is None and emp.user.mobile_number is not None:
            emp.user.mobile_number = None
            session.add(emp.user)

    session.add(emp)
    try:
        await session.commit()
        await session.refresh(emp, ["user"])
    except IntegrityError as exc:
        await session.rollback()
        err_str = str(exc).lower()
        if "employee_code" in err_str:
            raise BaseAPIException(
                status_code=409,
                detail=f"Employee code '{data.employee_code}' is already in use.",
                error_code="EMPLOYEE_CODE_EXISTS",
            ) from exc
        if "email" in err_str:
            raise BaseAPIException(
                status_code=409,
                detail=f"Email '{data.email}' is already in use.",
                error_code="EMAIL_EXISTS",
            ) from exc
        raise
    return emp
