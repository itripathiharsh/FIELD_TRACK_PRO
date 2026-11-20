"""
Agent 2.0 payloads. The agent sends Tally facts; the backend classifies them
(services/tally_v2_sync.py), so the business rules live in one tested place.

Amounts are exactly as Tally exports them: a debit is negative.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field


class _Batch(BaseModel):
    batch_id: str
    company_guid: Optional[str] = None


# ---------------------------------------------------------------------------
# Ledgers
# ---------------------------------------------------------------------------

class LedgerItem(BaseModel):
    guid: str = Field(..., min_length=1, max_length=255)
    name: str = Field(..., min_length=1, max_length=150)
    parent: Optional[str] = None
    is_debtor: bool
    aliases: list[str] = Field(default_factory=list)
    # Debtor details (ignored for non-debtors)
    outlet_code: Optional[str] = None
    brand: Optional[str] = None
    address: Optional[str] = None
    state: Optional[str] = None
    pincode: Optional[str] = None
    gst_number: Optional[str] = None
    contact_number: Optional[str] = None
    mobile: Optional[str] = None
    email: Optional[str] = None
    contact_person: Optional[str] = None
    zone: Optional[str] = None
    area: Optional[str] = None
    is_bill_wise: Optional[bool] = None
    credit_period: Optional[str] = None
    opening_balance: Optional[Decimal] = None
    closing_balance: Optional[Decimal] = None
    alter_id: Optional[int] = None


class LedgerSyncBatch(_Batch):
    # Full snapshot (every ledger, chunked, same snapshot_id) or an incremental
    # batch of changed debtors (snapshot_id None). Only a completed full snapshot
    # marks ledgers that disappeared from Tally.
    snapshot_id: Optional[str] = None
    is_final_chunk: bool = False
    as_of: Optional[datetime] = None
    period_start: Optional[date] = None  # date the ledger opening balances refer to
    ledgers: list[LedgerItem]


# ---------------------------------------------------------------------------
# Vouchers
# ---------------------------------------------------------------------------

class BillAllocation(BaseModel):
    name: Optional[str] = None
    bill_type: Optional[str] = None  # Agst Ref | New Ref | Advance | On Account
    amount: Decimal
    credit_period: Optional[str] = None


class BankAllocation(BaseModel):
    transaction_type: Optional[str] = None
    payment_mode: Optional[str] = None
    instrument_number: Optional[str] = None
    instrument_date: Optional[date] = None
    unique_reference: Optional[str] = None
    bank_name: Optional[str] = None
    amount: Optional[Decimal] = None


class DebtorLine(BaseModel):
    ledger_name: str = Field(..., min_length=1)
    ledger_guid: Optional[str] = None
    amount: Decimal  # Tally sign: negative = debit
    brand: Optional[str] = None
    bill_allocations: list[BillAllocation] = Field(default_factory=list)
    bank_allocations: list[BankAllocation] = Field(default_factory=list)


class CounterLine(BaseModel):
    ledger_name: str
    ledger_class: str = "OTHER"  # CASH | BANK | OTHER
    amount: Decimal
    bank_allocations: list[BankAllocation] = Field(default_factory=list)


class VoucherItem(BaseModel):
    guid: str = Field(..., min_length=1, max_length=100)
    alter_id: Optional[int] = None
    date: date
    voucher_type: str
    voucher_parent: Optional[str] = None
    voucher_number: Optional[str] = None
    party_ledger: Optional[str] = None
    narration: Optional[str] = None
    is_cancelled: bool = False
    is_optional: bool = False
    debtor_lines: list[DebtorLine] = Field(default_factory=list)
    counter_lines: list[CounterLine] = Field(default_factory=list)


class VoucherSyncBatch(_Batch):
    vouchers: list[VoucherItem]


# ---------------------------------------------------------------------------
# Bills Receivable
# ---------------------------------------------------------------------------

class OpenBillItem(BaseModel):
    ledger_name: str
    ledger_guid: Optional[str] = None
    bill_name: str
    bill_date: Optional[date] = None
    due_date: Optional[date] = None
    pending_amount: Decimal  # Tally sign: negative = receivable (Dr)
    overdue_days: Optional[int] = None


class BillsSyncBatch(_Batch):
    snapshot_id: str
    as_of_date: date
    is_final_chunk: bool = False
    bills: list[OpenBillItem]


# ---------------------------------------------------------------------------
# Voucher GUID manifest
# ---------------------------------------------------------------------------

class ReconcileEntry(BaseModel):
    guid: str = Field(..., min_length=1, max_length=100)
    alter_id: int = 0


class ReconcileBatch(_Batch):
    """Release 3.0: EVERY voucher header (GUID, AlterID) Tally holds dated window_from..window_to. FieldTrack answers
    what it is missing, holds in an older version, or holds although Tally no longer lists it."""
    window_from: date
    window_to: date
    entries: list[ReconcileEntry] = Field(default_factory=list, max_length=50000)


class ReconcileResult(BaseModel):
    batch_id: str
    window_from: date
    window_to: date
    listed: int
    held_in_window: int
    missing: list[str] = Field(default_factory=list)
    stale: list[str] = Field(default_factory=list)
    extra: list[str] = Field(default_factory=list)


class ManifestSyncBatch(_Batch):
    snapshot_id: str
    window_from: date
    window_to: date
    is_final_chunk: bool = False
    guids: list[str]


class V2SyncResult(BaseModel):
    status: str = "COMPLETED"
    batch_id: str
    total_received: int
    created_count: int = 0
    updated_count: int = 0
    retired_count: int = 0
    failed_count: int = 0
    details: dict = Field(default_factory=dict)
    errors: list[dict] = Field(default_factory=list)
