from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps.auth import CurrentUser
from app.database import get_async_session
from app.schemas.device import DeviceRead, DeviceRegisterRequest, DeviceUnregisterRequest
from app.services.device_service import device_service

router = APIRouter(prefix="/devices", tags=["Devices"])


@router.post("/register", response_model=DeviceRead, status_code=status.HTTP_200_OK)
async def register_device(
    payload: DeviceRegisterRequest,
    current_user: CurrentUser = None,
    session: AsyncSession = Depends(get_async_session),
) -> DeviceRead:
    """
    Register or update an FCM push notification token for the authenticated user.
    """
    device = await device_service.register_device(
        user_id=current_user.id,
        fcm_token=payload.fcm_token,
        device_type=payload.device_type,
        device_id=payload.device_id,
        session=session,
    )
    return DeviceRead.model_validate(device)


@router.post("/unregister", status_code=status.HTTP_200_OK)
async def unregister_device(
    payload: DeviceUnregisterRequest,
    current_user: CurrentUser = None,
    session: AsyncSession = Depends(get_async_session),
) -> dict:
    """
    Unregister/deactivate an FCM push notification token (e.g. upon user logout).
    """
    success = await device_service.unregister_device(
        fcm_token=payload.fcm_token,
        user_id=current_user.id,
        session=session,
    )
    return {"status": "ok", "unregistered": success}


@router.get("/me", response_model=list[DeviceRead])
async def list_my_devices(
    current_user: CurrentUser = None,
    session: AsyncSession = Depends(get_async_session),
) -> list[DeviceRead]:
    """
    List all active registered devices for the current user.
    """
    devices = await device_service.list_user_devices(
        user_id=current_user.id,
        session=session,
    )
    return [DeviceRead.model_validate(d) for d in devices]
