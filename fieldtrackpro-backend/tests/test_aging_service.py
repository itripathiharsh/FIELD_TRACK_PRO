"""
Unit tests for the single authoritative aging calculation (app/services/aging_service.py).

Pins the exact boundary cases discussed with the client: 20 days normal,
21-25 days warning, 26+ days overdue, plus the MIS buckets.
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.services.aging_service import (
    AgingStatus,
    MisBucket,
    PaymentStatusLabel,
    compute_invoice_aging,
    compute_mis_bucket,
)

TODAY = date(2026, 8, 13)


def _aged(days_ago: int, amount=Decimal("100000"), paid=Decimal("0")):
    return compute_invoice_aging(TODAY - timedelta(days=days_ago), amount, paid, TODAY)


@pytest.mark.parametrize(
    "days_ago,expected_status",
    [
        (0, AgingStatus.NORMAL),
        (20, AgingStatus.NORMAL),
        (21, AgingStatus.WARNING),
        (25, AgingStatus.WARNING),
        (26, AgingStatus.OVERDUE),
        (60, AgingStatus.OVERDUE),
        (90, AgingStatus.OVERDUE),
        (91, AgingStatus.OVERDUE),
    ],
)
def test_aging_status_boundaries(days_ago, expected_status):
    result = _aged(days_ago)
    assert result.aging_status == expected_status
    assert result.days_outstanding == days_ago


@pytest.mark.parametrize(
    "days_ago,expected_bucket",
    [
        (0, MisBucket.DAYS_0_15),
        (15, MisBucket.DAYS_0_15),
        (16, MisBucket.DAYS_16_30),
        (30, MisBucket.DAYS_16_30),
        (31, MisBucket.DAYS_31_60),
        (60, MisBucket.DAYS_31_60),
        (61, MisBucket.DAYS_61_90),
        (90, MisBucket.DAYS_61_90),
        (91, MisBucket.DAYS_90_PLUS),
        (365, MisBucket.DAYS_90_PLUS),
    ],
)
def test_mis_bucket_boundaries(days_ago, expected_bucket):
    assert compute_mis_bucket(days_ago) == expected_bucket


def test_fully_paid_invoice_is_paid_regardless_of_age():
    """A 200-day-old invoice that has been fully paid is PAID, not OVERDUE."""
    result = _aged(200, amount=Decimal("100000"), paid=Decimal("100000"))
    assert result.aging_status == AgingStatus.PAID
    assert result.payment_status == PaymentStatusLabel.PAID
    assert result.remaining_amount == Decimal("0.00")


def test_overpayment_does_not_produce_negative_remaining():
    result = _aged(10, amount=Decimal("100000"), paid=Decimal("150000"))
    assert result.remaining_amount == Decimal("0.00")
    assert result.aging_status == AgingStatus.PAID


def test_partial_payment_reduces_remaining_but_keeps_aging_status():
    """Invoice = 200,000, Payment = 50,000 -> Outstanding = 150,000 (P1 example)."""
    result = _aged(30, amount=Decimal("200000"), paid=Decimal("50000"))
    assert result.remaining_amount == Decimal("150000.00")
    assert result.payment_status == PaymentStatusLabel.PARTIALLY_PAID
    assert result.aging_status == AgingStatus.OVERDUE

    # A second payment brings it down further, history intact via separate rows
    # (verified at the integration level, not here) - this unit only checks
    # that the aging calc reflects the latest total correctly.
    result2 = _aged(30, amount=Decimal("200000"), paid=Decimal("150000"))
    assert result2.remaining_amount == Decimal("50000.00")


def test_unpaid_vs_partially_paid_distinction():
    unpaid = _aged(5, amount=Decimal("1000"), paid=Decimal("0"))
    assert unpaid.payment_status == PaymentStatusLabel.UNPAID

    partial = _aged(5, amount=Decimal("1000"), paid=Decimal("1"))
    assert partial.payment_status == PaymentStatusLabel.PARTIALLY_PAID
