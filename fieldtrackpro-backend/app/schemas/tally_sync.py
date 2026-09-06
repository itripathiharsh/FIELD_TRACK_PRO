from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class SyncAgentCreate(BaseModel):
    name: str = Field(..., max_length=150)
    organization_id: str = Field(default="default", max_length=100)
    tally_company_guid: Optional[str] = None
    tally_company_name: Optional[str] = None


class SyncAgentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    organization_id: str
    tally_company_guid: Optional[str] = None
    tally_company_name: Optional[str] = None
    is_active: bool
    agent_version: Optional[str] = None
    last_heartbeat_at: Optional[datetime] = None
    last_sync_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class SyncAgentRegistrationResponse(BaseModel):
    agent: SyncAgentRead
    api_key: str = Field(..., description="One-time raw API secret key for the agent")


class TallyIntegrationStatusResponse(BaseModel):
    is_connected: bool
    agent_status: str  # "ONLINE", "OFFLINE", "NOT_CONFIGURED"
    agent_id: Optional[uuid.UUID] = None
    agent_name: Optional[str] = None
    agent_version: Optional[str] = None
    tally_company_name: Optional[str] = None
    tally_company_guid: Optional[str] = None
    last_heartbeat_at: Optional[datetime] = None
    last_sync_at: Optional[datetime] = None
    total_invoices_synced: int = 0
    total_payments_synced: int = 0
    total_customers_synced: int = 0
    message: Optional[str] = None


class HeartbeatRequest(BaseModel):
    agent_version: str
    tally_status: str
    company_name: Optional[str] = None
    company_guid: Optional[str] = None
    checkpoints: Optional[dict[str, Any]] = None


class HeartbeatResponse(BaseModel):
    status: str = "OK"
    server_time: datetime
    agent_id: uuid.UUID
    organization_id: str


# ---------------------------------------------------------------------------
# Customer Sync
# ---------------------------------------------------------------------------

class CustomerSyncItem(BaseModel):
    source_reference: Optional[str] = None
    outlet_code: Optional[str] = None
    name: str
    parent_group: Optional[str] = None
    brand: Optional[str] = None
    address: Optional[str] = None
    state: Optional[str] = None
    pincode: Optional[str] = None
    gst_number: Optional[str] = None
    contact_number: Optional[str] = None
    contact_person: Optional[str] = None
    zone: Optional[str] = None
    area: Optional[str] = None


class CustomerSyncBatch(BaseModel):
    batch_id: str
    company_guid: Optional[str] = None
    customers: list[CustomerSyncItem]


# ---------------------------------------------------------------------------
# Invoice Sync
# ---------------------------------------------------------------------------

class InvoiceSyncItem(BaseModel):
    source_reference: str
    invoice_number: str
    outlet_code: Optional[str] = None
    customer_name: str
    invoice_date: date
    due_date: Optional[date] = None
    amount: Decimal
    brand: Optional[str] = None
    voucher_type: Optional[str] = "Sales"
    imported_outstanding_amount: Optional[Decimal] = None


class InvoiceSyncBatch(BaseModel):
    batch_id: str
    company_guid: Optional[str] = None
    invoices: list[InvoiceSyncItem]


# ---------------------------------------------------------------------------
# Payment Sync
# ---------------------------------------------------------------------------

class PaymentBrandItem(BaseModel):
    brand: str
    allocated_amount: Decimal


class PaymentBillAllocationItem(BaseModel):
    bill_type: Optional[str] = None  # Agst Ref, On Account, New Ref, Advance
    bill_name: str  # Tally bill reference / invoice number
    amount: Decimal


class PaymentSyncItem(BaseModel):
    source_reference: str
    receipt_number: Optional[str] = None
    outlet_code: Optional[str] = None
    customer_name: str
    payment_date: date
    amount: Decimal
    payment_method: str = "ONLINE"
    cheque_number: Optional[str] = None
    cheque_bank_name: Optional[str] = None
    utr_reference: Optional[str] = None
    notes: Optional[str] = None
    brand_allocations: list[PaymentBrandItem] = Field(default_factory=list)
    bill_allocations: list[PaymentBillAllocationItem] = Field(default_factory=list)


class PaymentSyncBatch(BaseModel):
    batch_id: str
    company_guid: Optional[str] = None
    payments: list[PaymentSyncItem]


# ---------------------------------------------------------------------------
# Sync Result Response
# ---------------------------------------------------------------------------

class SyncErrorDetail(BaseModel):
    identifier: str
    error: str


class SyncResultResponse(BaseModel):
    status: str = "COMPLETED"
    batch_id: str
    total_received: int
    created_count: int
    updated_count: int
    failed_count: int
    errors: list[SyncErrorDetail] = Field(default_factory=list)
