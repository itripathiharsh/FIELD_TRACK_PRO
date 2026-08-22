"""
Excel/MIS import schemas.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict

from app.models.import_batch import ImportStatus


class ImportPreviewResponse(BaseModel):
    sheet_name: str
    all_sheets: list[str]
    columns: list[str]
    sample_rows: list[list[str]]
    total_data_rows: int
    truncated: bool
    detected_type: str = "generic" # "employee_master", "dms_outlet_financial", "combined_bi", "generic"
    suggested_mapping: dict[str, Optional[str]]
    target_fields: dict[str, Any]
    unmatched_fos_names: list[str] = []
    header_row_index: int = 1
    is_confident: bool = False
    matched_columns_count: int = 0
    total_columns_count: int = 0
    detected_entity_count: int = 0


class ImportValidateRequest(BaseModel):
    sheet_name: str
    column_mapping: dict[str, str]
    import_type: str = "auto" # "auto", "employee_master", "dms_outlet_financial", "invoice_payment"
    outlet_match_strategy: str = "outlet_code"
    allow_generated_invoice_numbers: bool = False
    fos_mapping_overrides: dict[str, uuid.UUID] = {}


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

    model_config = ConfigDict(from_attributes=True)


class FOSEmployeeMappingRead(BaseModel):
    id: uuid.UUID
    raw_fos_name: str
    employee_id: uuid.UUID
    employee_name: Optional[str] = None
    employee_code: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class FOSEmployeeMappingCreate(BaseModel):
    raw_fos_name: str
    employee_id: uuid.UUID
