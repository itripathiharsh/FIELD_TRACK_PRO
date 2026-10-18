"""Single-source ageing rule: normal < day 21; YELLOW 21..25 inclusive; RED > 25."""
from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.services.aging_service import AgingStatus, classify_age_days, compute_invoice_aging


@pytest.mark.parametrize(
    "days,expected",
    [(-3, AgingStatus.NORMAL), (0, AgingStatus.NORMAL), (20, AgingStatus.NORMAL),
     (21, AgingStatus.WARNING), (23, AgingStatus.WARNING), (25, AgingStatus.WARNING),
     (26, AgingStatus.OVERDUE), (90, AgingStatus.OVERDUE), (400, AgingStatus.OVERDUE)],
)
def test_classify_age_days_boundaries(days, expected):
    assert classify_age_days(days) is expected


@pytest.mark.parametrize("days", [0, 20, 21, 25, 26, 60])
def test_invoice_aging_delegates_to_the_single_helper(days):
    today = date(2026, 10, 10)
    a = compute_invoice_aging(today - timedelta(days=days), Decimal("100"), Decimal("0"), today)
    assert a.aging_status is classify_age_days(days)


def test_paid_invoice_is_never_yellow_or_red():
    today = date(2026, 10, 10)
    a = compute_invoice_aging(today - timedelta(days=40), Decimal("100"), Decimal("100"), today)
    assert a.aging_status is AgingStatus.PAID
