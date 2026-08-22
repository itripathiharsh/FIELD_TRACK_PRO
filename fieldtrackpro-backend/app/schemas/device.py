from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class DeviceRegisterRequest(BaseModel):
    fcm_token: str = Field(..., min_length=10, max_length=512, description="FCM device registration token")
    device_type: str = Field(default="ANDROID", max_length=50, description="Device platform (e.g. ANDROID, IOS, WEB)")
    device_id: Optional[str] = Field(default=None, max_length=255, description="Client device hardware/installation ID")


class DeviceUnregisterRequest(BaseModel):
    fcm_token: str = Field(..., min_length=10, max_length=512, description="FCM device registration token to unregister")


class DeviceRead(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    fcm_token: str
    device_type: str
    device_id: Optional[str] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime
    last_used_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)
