"""
Aging Service: the single authoritative implementation of invoice aging.

P1 requirement: aging must be a real calculated value, never duplicated in
the frontend, and never collapsed to a simple PAID/UNPAID flag. Every caller
(account summary, invoice history, brand aggregation, reports) must go
through this module rather than recomputing days/status independently.

Business rules (from the client meetings, not invented):
- Age is always computed from `invoice_date`, never `due_date`. `due_date` is
  informational/display-only.
- Normal:    age <= 20 days
  Warning:   21-25 days ("payment approaching due" - the client's 21-25 day
             payment cycle)
  Overdue:   > 25 days
- A fully-paid invoice's aging_status is PAID regardless of its age - aging
  only describes outstanding money.
- Separately, MIS buckets (0-15 / 16-30 / 31-60 / 61-90 / 90+) are computed
  for reporting/visibility into old debt, independent of the Normal/Warning/
  Overdue UI status above. The client explicitly asked for both.
"""
from __future__ import annotations

import enum
from dataclasses import dataclass
from datetime import date
from decimal import Decimal


class PaymentStatusLabel(str, enum.Enum):
    UNPAID = "UNPAID"
    PARTIALLY_PAID = "PARTIALLY_PAID"
    PAID = "PAID"


class AgingStatus(str, enum.Enum):
    NORMAL = "NORMAL"
    WARNING = "WARNING"
    OVERDUE = "OVERDUE"
    PAID = "PAID"


class MisBucket(str, enum.Enum):
    DAYS_0_15 = "0-15"
    DAYS_16_30 = "16-30"
    DAYS_31_60 = "31-60"
    DAYS_61_90 = "61-90"
    DAYS_90_PLUS = "90+"


WARNING_THRESHOLD_DAYS = 21
OVERDUE_THRESHOLD_DAYS = 26


@dataclass(frozen=True)
class InvoiceAging:
    days_outstanding: int
    remaining_amount: Decimal
    payment_status: PaymentStatusLabel
    aging_status: AgingStatus
    mis_bucket: MisBucket


def compute_mis_bucket(days_outstanding: int) -> MisBucket:
    if days_outstanding <= 15:
        return MisBucket.DAYS_0_15
    if days_outstanding <= 30:
        return MisBucket.DAYS_16_30
    if days_outstanding <= 60:
        return MisBucket.DAYS_31_60
    if days_outstanding <= 90:
        return MisBucket.DAYS_61_90
    return MisBucket.DAYS_90_PLUS


def compute_invoice_aging(
    invoice_date: date,
    amount: Decimal,
    verified_paid_amount: Decimal,
    today: date,
) -> InvoiceAging:
    """
    The one authoritative aging calculation. `verified_paid_amount` must be
    the sum of only VERIFIED payments applied to this invoice - a
    PENDING_VERIFICATION or REJECTED payment must never reduce outstanding.
    """
    days_outstanding = (today - invoice_date).days
    remaining = amount - verified_paid_amount

    if remaining <= 0:
        return InvoiceAging(
            days_outstanding=days_outstanding,
            remaining_amount=Decimal("0.00"),
            payment_status=PaymentStatusLabel.PAID,
            aging_status=AgingStatus.PAID,
            mis_bucket=compute_mis_bucket(days_outstanding),
        )

    payment_status = (
        PaymentStatusLabel.PARTIALLY_PAID if verified_paid_amount > 0 else PaymentStatusLabel.UNPAID
    )

    if days_outstanding < WARNING_THRESHOLD_DAYS:
        aging_status = AgingStatus.NORMAL
    elif days_outstanding < OVERDUE_THRESHOLD_DAYS:
        aging_status = AgingStatus.WARNING
    else:
        aging_status = AgingStatus.OVERDUE

    return InvoiceAging(
        days_outstanding=days_outstanding,
        remaining_amount=remaining,
        payment_status=payment_status,
        aging_status=aging_status,
        mis_bucket=compute_mis_bucket(days_outstanding),
    )
