from __future__ import annotations

import logging
import uuid
from typing import Sequence

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user_device import UserDevice

logger = logging.getLogger("fieldtrackpro")


class DeviceService:
    """Service managing user device tokens for push notifications."""

    async def register_device(
        self,
        user_id: uuid.UUID,
        fcm_token: str,
        device_type: str = "ANDROID",
        device_id: str | None = None,
        session: AsyncSession = None,
    ) -> UserDevice:
        """
        Register or update an FCM token for a user.
        Handles token updates, user switches on the same device, and token refresh.
        """
        clean_token = fcm_token.strip()

        # 1. Check if the token already exists
        stmt = select(UserDevice).where(UserDevice.fcm_token == clean_token)
        result = await session.execute(stmt)
        device = result.scalar_one_or_none()

        if device is not None:
            # Token already in DB: update ownership and activate
            device.user_id = user_id
            device.device_type = device_type
            if device_id:
                device.device_id = device_id
            device.is_active = True
            device.last_used_at = func.now()
            await session.commit()
            await session.refresh(device)
            logger.info(f"Updated existing FCM token for user={user_id}, device_id={device_id}")
            return device

        # 2. If device_id provided, check if that physical device had a previous token for this user
        if device_id:
            device_stmt = select(UserDevice).where(
                UserDevice.user_id == user_id,
                UserDevice.device_id == device_id,
            )
            dev_result = await session.execute(device_stmt)
            existing_dev = dev_result.scalar_one_or_none()
            if existing_dev is not None:
                existing_dev.fcm_token = clean_token
                existing_dev.device_type = device_type
                existing_dev.is_active = True
                existing_dev.last_used_at = func.now()
                await session.commit()
                await session.refresh(existing_dev)
                logger.info(f"Refreshed FCM token for device_id={device_id}, user={user_id}")
                return existing_dev

        # 3. Create new device record
        new_device = UserDevice(
            user_id=user_id,
            fcm_token=clean_token,
            device_type=device_type,
            device_id=device_id,
            is_active=True,
            last_used_at=func.now(),
        )
        session.add(new_device)
        await session.commit()
        await session.refresh(new_device)
        logger.info(f"Registered new FCM token for user={user_id}, device_id={device_id}")
        return new_device

    async def unregister_device(
        self,
        fcm_token: str,
        user_id: uuid.UUID | None = None,
        session: AsyncSession = None,
    ) -> bool:
        """
        Deactivate a device token upon logout.
        """
        clean_token = fcm_token.strip()
        conditions = [UserDevice.fcm_token == clean_token]
        if user_id is not None:
            conditions.append(UserDevice.user_id == user_id)

        stmt = select(UserDevice).where(*conditions)
        result = await session.execute(stmt)
        device = result.scalar_one_or_none()

        if device is not None:
            device.is_active = False
            await session.commit()
            logger.info(f"Deactivated FCM token for user={user_id}")
            return True
        return False

    async def get_active_tokens_for_user(
        self,
        user_id: uuid.UUID,
        session: AsyncSession,
    ) -> list[str]:
        """
        Return all active FCM tokens for a given user.
        """
        stmt = select(UserDevice.fcm_token).where(
            UserDevice.user_id == user_id,
            UserDevice.is_active.is_(True),
        )
        result = await session.execute(stmt)
        return [str(token) for token in result.scalars().all() if token]

    async def list_user_devices(
        self,
        user_id: uuid.UUID,
        session: AsyncSession,
    ) -> Sequence[UserDevice]:
        """
        List all active devices for a user.
        """
        stmt = (
            select(UserDevice)
            .where(UserDevice.user_id == user_id, UserDevice.is_active.is_(True))
            .order_by(UserDevice.updated_at.desc())
        )
        result = await session.execute(stmt)
        return result.scalars().all()

    async def deactivate_stale_tokens(
        self,
        stale_tokens: list[str],
        session: AsyncSession,
    ) -> None:
        """
        Bulk deactivate invalid or expired tokens identified by FCM.
        """
        if not stale_tokens:
            return

        stmt = (
            update(UserDevice)
            .where(UserDevice.fcm_token.in_(stale_tokens))
            .values(is_active=False)
        )
        await session.execute(stmt)
        await session.commit()
        logger.info(f"Deactivated {len(stale_tokens)} stale FCM tokens")


device_service = DeviceService()
