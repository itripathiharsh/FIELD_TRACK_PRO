from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class OutletProofRead(BaseModel):
    """
    One outlet proof (live photo + the GPS fix taken at the same click).

    `image_url` is a short-lived signed/presigned URL (never stored); it is null
    when the object is unavailable. The auth-protected stream is always
    GET /customers/outlet-proofs/{id}/image.
    The "admin extras" below are only populated by the admin list endpoint.
    """

    id: uuid.UUID
    customer_id: uuid.UUID | None = None
    prospect_id: uuid.UUID | None = None
    kind: str
    status: str
    is_primary: bool = False
    latitude: float
    longitude: float
    accuracy_m: float
    captured_at: datetime
    received_at: datetime
    is_mock_location: bool = False
    device_info: str | None = None
    content_type: str
    size_bytes: int
    storage_provider: str
    submitted_by: uuid.UUID
    submitted_by_name: str | None = None
    distance_from_verified_m: float | None = None
    reviewed_by: uuid.UUID | None = None
    reviewed_at: datetime | None = None
    rejection_reason: str | None = None
    image_url: str | None = None
    created_at: datetime

    # --- admin extras (null on employee-facing responses) ---
    customer_name: str | None = None
    customer_outlet_code: str | None = None
    territory_name: str | None = None
    area_name: str | None = None
    prospect_name: str | None = None
    customer_latitude: float | None = None   # current official pin, if any
    customer_longitude: float | None = None
    nearby_pending_proofs: int | None = None  # OTHER pending proofs of this outlet within the confirm radius


class OutletProofRejectRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=255)
