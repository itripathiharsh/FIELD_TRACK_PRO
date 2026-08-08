"""
User management service — refactored to use UserRepository.
"""
from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password, verify_password
from app.exceptions.custom import BaseAPIException, DuplicateResourceException
from app.models.user import User
from app.repositories.user_repo import UserRepository
from app.schemas.user import UserCreate, UserUpdatePassword


async def create_user(data: UserCreate, session: AsyncSession) -> User:
    repo = UserRepository(session)

    if not data.email and not data.mobile_number:
        raise BaseAPIException(
            status_code=422,
            detail="email or mobile_number is required",
            error_code="USER_IDENTITY_REQUIRED",
        )
    if data.email and await repo.email_exists(data.email):
        raise DuplicateResourceException("Email already registered")
    if data.mobile_number and await repo.mobile_exists(data.mobile_number):
        raise DuplicateResourceException("Mobile number already registered")

    user = User(
        email=data.email,
        mobile_number=data.mobile_number,
        password_hash=hash_password(data.password),
        role=data.role,
    )
    await repo.add(user)
    await repo.commit()
    return user


async def get_user_by_id(user_id: uuid.UUID, session: AsyncSession) -> User:
    repo = UserRepository(session)
    user = await repo.get_by_id(user_id)
    if user is None:
        raise BaseAPIException(status_code=404, detail="User not found", error_code="USER_NOT_FOUND")
    return user


async def update_password(user: User, data: UserUpdatePassword, session: AsyncSession) -> None:
    if not verify_password(data.old_password, user.password_hash):
        raise BaseAPIException(
            status_code=400,
            detail="Old password is incorrect",
            error_code="AUTH_WRONG_OLD_PASSWORD",
        )
    user.password_hash = hash_password(data.new_password)
    session.add(user)
    await session.commit()


async def toggle_active(user_id: uuid.UUID, active: bool, session: AsyncSession) -> User:
    repo = UserRepository(session)
    user = await repo.get_by_id(user_id)
    if user is None:
        raise BaseAPIException(status_code=404, detail="User not found", error_code="USER_NOT_FOUND")
    user.is_active = active
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user
