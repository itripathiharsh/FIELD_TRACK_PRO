"""
Excel/MIS import schemas.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel

from app.models.import_batch import ImportStatus


class ImportPreviewResponse(BaseModel):
    sheet_name: str
    all_sheets: list[str]
    columns: list[str]
    sample_rows: list[list[str]]
    total_data_rows: int
    truncated: bool
    suggested_mapping: dict[str, Optional[str]]
    target_fields: dict[str, Any]


class ImportValidateRequest(BaseModel):
    sheet_name: str
    column_mapping: dict[str, str]
    outlet_match_strategy: str = "outlet_code"
    allow_generated_invoice_numbers: bool = False


class ImportBatchRead(BaseModel):
    id: uuid.UUID
    filename: str
    sheet_name: str
    uploaded_by: uuid.UUID
    uploaded_at: datetime
    column_mapping: dict[str, Any]
    outlet_match_strategy: str
    status: ImportStatus
    summary: Optional[dict] = None
    error_report: Optional[list] = None
    rows_processed: int
    rows_created: int
    rows_updated: int
    rows_skipped: int
    rows_error: int
    committed_at: Optional[datetime] = None
    committed_by: Optional[uuid.UUID] = None
    failure_reason: Optional[str] = None

    # Denormalized for the history list (populated by the service layer).
    uploaded_by_email: Optional[str] = None

    model_config = {"from_attributes": True}
