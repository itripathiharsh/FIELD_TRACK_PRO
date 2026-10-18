"""
Shared money-position fields (additive) used by the outlet Account summary, its
brand rows, and the Collections overview rows + totals. All numbers come from
app/services/account_position.py - one calculation, no per-screen formulas.

    opening_balance + total_invoiced - paid_in_tally == total_outstanding

(see account_position.py for the full definitions).
"""
from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, Field


class AgeingBreakdown(BaseModel):
    """Outstanding split by age. The five buckets always sum to total_outstanding."""

    normal: Decimal = Decimal("0.00")      # live invoices aged < 21 days
    warning: Decimal = Decimal("0.00")     # live invoices aged 21-25 days
    overdue: Decimal = Decimal("0.00")     # live invoices aged >= 26 days
    # Tally baseline (OutletFinancialSnapshot) carried-forward balance; the
    # snapshot age bands cannot be mapped onto 21/26 so it has its own buckets.
    baseline_current: Decimal = Decimal("0.00")   # baseline aged < 30 days / unaged residual
    baseline_overdue: Decimal = Decimal("0.00")   # baseline aged 30+ days (counts as overdue)


class PositionFields(BaseModel):
    opening_balance: Decimal = Field(
        default=Decimal("0.00"),
        description="Tally baseline carried forward (derived): total_outstanding - total_invoiced + paid_in_tally. "
        "Includes advance_credit (over-payment is never shown as negative outstanding).",
    )
    baseline_invoiced: Decimal = Field(default=Decimal("0.00"), description="Part of total_invoiced from the Tally snapshot sales.")
    baseline_collected: Decimal = Field(default=Decimal("0.00"), description="Part of paid_in_tally from the Tally snapshot collection.")
    paid_in_tally: Decimal = Field(
        default=Decimal("0.00"),
        description="Snapshot collection + payments POSTED to Tally. Excludes verified_awaiting_tally.",
    )
    advance_credit: Decimal = Field(default=Decimal("0.00"), description="On-account credit beyond what is owed (clamped out of outstanding).")
    ageing: AgeingBreakdown = Field(default_factory=AgeingBreakdown)
    reconciles: bool = Field(
        default=True,
        description="Derived check: opening + invoiced - paid_in_tally == outstanding, ageing sums to outstanding, 0 <= overdue <= outstanding.",
    )
