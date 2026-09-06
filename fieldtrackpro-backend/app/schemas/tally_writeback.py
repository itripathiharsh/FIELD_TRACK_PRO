from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class TallyWritebackJobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    idempotency_key: str
    entity_type: str
    entity_id: uuid.UUID
    operation: str
    payload: Dict[str, Any]
    status: str
    retry_count: int
    next_retry_at: Optional[datetime] = None
    last_error: Optional[str] = None
    created_at: datetime


class TallyWritebackAckRequest(BaseModel):
    tally_guid: Optional[str] = Field(None, description="Tally voucher GUID")
    tally_master_id: Optional[str] = Field(None, description="Tally MasterID / LASTVCHID")
    tally_voucher_number: Optional[str] = Field(None, description="Tally voucher number")


class TallyWritebackFailRequest(BaseModel):
    error_message: str
    is_retryable: bool = Field(default=True, description="False if invalid ledger/permanent error")


class TallyWritebackActionResponse(BaseModel):
    status: str
    job_id: uuid.UUID
    message: Optional[str] = None
