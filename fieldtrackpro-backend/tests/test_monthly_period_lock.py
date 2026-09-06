"""
Comprehensive test suite for Monthly Close / Accounting Period Lifecycle Lock.
Verifies:
1. Automatic IST month rollover & PENDING_CLOSE state transition.
2. Financial lock: Blocking backdated payments and invoices for FINALIZED periods (409 PERIOD_LOCKED).
3. Legitimate cross-period payment: September payment on August invoice succeeds.
4. Period review summary endpoint.
5. Controlled Admin reopen with mandatory reason.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import delete, select

from app.core.security import hash_password
from app.database import AsyncSessionLocal
from app.exceptions.custom import BaseAPIException
from app.models.monthly_reporting_period import MonthlyPeriodStatus, MonthlyReportingPeriod
from app.models.user import Role, User
from app.services.period_service import (
    assert_period_open_for_date,
    ensure_monthly_periods_synced,
    finalize_monthly_period,
    get_monthly_period_review,
    reopen_monthly_period,
)
from tests.conftest import admin_headers, requires_db


@requires_db
@pytest.mark.asyncio
async def test_auto_rollover_sync_marks_previous_month_pending_close():
    """
    Ensures that ensure_monthly_periods_synced creates the current month as OPEN
    and flags past OPEN months as PENDING_CLOSE.
    """
    test_year = 2022
    test_month = 4

    try:
        async with AsyncSessionLocal() as session:
            # Clean up any leftover test year/month
            await session.execute(
                delete(MonthlyReportingPeriod).where(
                    MonthlyReportingPeriod.period_year == test_year,
                    MonthlyReportingPeriod.period_month == test_month,
                )
            )
            await session.commit()

            # Insert a past open month
            past_period = MonthlyReportingPeriod(
                period_year=test_year,
                period_month=test_month,
                period_name=f"April {test_year}",
                status=MonthlyPeriodStatus.OPEN,
            )
            session.add(past_period)
            await session.commit()
            period_id = past_period.id

            periods = await ensure_monthly_periods_synced(session)
            await session.commit()

            # Past period must now be PENDING_CLOSE
            refreshed_past = await session.get(MonthlyReportingPeriod, period_id)
            assert refreshed_past is not None
            assert refreshed_past.status in (MonthlyPeriodStatus.PENDING_CLOSE, MonthlyPeriodStatus.PENDING_CLOSE.value, "PENDING_CLOSE")

            # Current month must exist in periods
            today = date.today()
            current_period = next((p for p in periods if p.period_year == today.year and p.period_month == today.month), None)
            assert current_period is not None
            assert current_period.period_name is not None
    finally:
        async with AsyncSessionLocal() as session:
            await session.execute(
                delete(MonthlyReportingPeriod).where(
                    MonthlyReportingPeriod.period_year == test_year,
                )
            )
            await session.commit()


@requires_db
@pytest.mark.asyncio
async def test_assert_period_open_blocks_finalized_period():
    """
    Ensures that assert_period_open_for_date raises 409 PERIOD_LOCKED for a date in a finalized period.
    """
    test_year = 2032
    test_month = 2

    try:
        async with AsyncSessionLocal() as session:
            await session.execute(
                delete(MonthlyReportingPeriod).where(
                    MonthlyReportingPeriod.period_year == test_year,
                    MonthlyReportingPeriod.period_month == test_month,
                )
            )
            await session.commit()

            finalized_period = MonthlyReportingPeriod(
                period_year=test_year,
                period_month=test_month,
                period_name=f"February {test_year}",
                status=MonthlyPeriodStatus.FINALIZED,
            )
            session.add(finalized_period)
            await session.commit()

            # A date in February 2032 must raise 409
            with pytest.raises(BaseAPIException) as exc_info:
                await assert_period_open_for_date(date(test_year, test_month, 15), session)
            assert exc_info.value.status_code == 409
            assert exc_info.value.error_code == "PERIOD_LOCKED"

            # A date in an unfinalized period (e.g. March 2032) must succeed
            await assert_period_open_for_date(date(test_year, 3, 15), session)
    finally:
        async with AsyncSessionLocal() as session:
            await session.execute(
                delete(MonthlyReportingPeriod).where(
                    MonthlyReportingPeriod.period_year == test_year,
                )
            )
            await session.commit()


@requires_db
@pytest.mark.asyncio
async def test_cross_period_payment_on_closed_invoice_allowed():
    """
    Ensures that a payment created with an open period date referencing an invoice from a
    closed period passes period check, while backdating into the closed period is blocked.
    """
    test_year = 2033
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(
                delete(MonthlyReportingPeriod).where(
                    MonthlyReportingPeriod.period_year == test_year,
                )
            )
            await session.commit()

            aug_period = MonthlyReportingPeriod(
                period_year=test_year,
                period_month=8,
                period_name=f"August {test_year}",
                status=MonthlyPeriodStatus.FINALIZED,
            )
            sep_period = MonthlyReportingPeriod(
                period_year=test_year,
                period_month=9,
                period_name=f"September {test_year}",
                status=MonthlyPeriodStatus.OPEN,
            )
            session.add_all([aug_period, sep_period])
            await session.commit()

            # September payment passes period check
            await assert_period_open_for_date(date(test_year, 9, 5), session)

            # August payment fails period check
            with pytest.raises(BaseAPIException) as exc_info:
                await assert_period_open_for_date(date(test_year, 8, 20), session)
            assert exc_info.value.status_code == 409
    finally:
        async with AsyncSessionLocal() as session:
            await session.execute(
                delete(MonthlyReportingPeriod).where(
                    MonthlyReportingPeriod.period_year == test_year,
                )
            )
            await session.commit()


@requires_db
@pytest.mark.asyncio
async def test_reopen_requires_valid_reason():
    """
    Ensures reopen_monthly_period rejects empty reasons and successfully records the reason and user.
    """
    test_year = 2034
    test_month = 5

    try:
        async with AsyncSessionLocal() as session:
            # Get or create admin user
            admin_res = await session.execute(
                select(User).where(User.role == Role.ADMIN, User.is_active == True)
            )
            admin_user = admin_res.scalars().first()
            if not admin_user:
                admin_user = User(
                    email=f"admin_reopen_{uuid.uuid4().hex[:6]}@test.com",
                    password_hash=hash_password("AdminPass123!"),
                    role=Role.ADMIN,
                    is_active=True,
                )
                session.add(admin_user)
                await session.flush()

            await session.execute(
                delete(MonthlyReportingPeriod).where(
                    MonthlyReportingPeriod.period_year == test_year,
                    MonthlyReportingPeriod.period_month == test_month,
                )
            )
            await session.commit()

            period = MonthlyReportingPeriod(
                period_year=test_year,
                period_month=test_month,
                period_name=f"May {test_year}",
                status=MonthlyPeriodStatus.FINALIZED,
            )
            session.add(period)
            await session.commit()

            # Empty reason raises 422
            with pytest.raises(BaseAPIException) as exc_info:
                await reopen_monthly_period(period.id, admin_user.id, "   ", session)
            assert exc_info.value.status_code == 422
            assert exc_info.value.error_code == "REOPEN_REASON_REQUIRED"

            # Valid reason succeeds and records tracking metadata
            updated = await reopen_monthly_period(period.id, admin_user.id, "Dispute resolution on invoice #1024", session)
            assert updated.status == MonthlyPeriodStatus.PENDING_CLOSE.value
            assert updated.reopen_reason == "Dispute resolution on invoice #1024"
            assert updated.reopened_by == admin_user.id
            assert updated.finalized_at is None
    finally:
        async with AsyncSessionLocal() as session:
            await session.execute(
                delete(MonthlyReportingPeriod).where(
                    MonthlyReportingPeriod.period_year == test_year,
                )
            )
            await session.commit()


@requires_db
@pytest.mark.asyncio
async def test_monthly_period_review_endpoint(client: AsyncClient):
    """
    Ensures GET /api/v1/reports/monthly-periods/{id}/review returns accurate review metrics.
    """
    test_year = 2035
    test_month = 10

    try:
        async with AsyncSessionLocal() as session:
            await session.execute(
                delete(MonthlyReportingPeriod).where(
                    MonthlyReportingPeriod.period_year == test_year,
                    MonthlyReportingPeriod.period_month == test_month,
                )
            )
            await session.commit()

            period = MonthlyReportingPeriod(
                period_year=test_year,
                period_month=test_month,
                period_name=f"October {test_year}",
                status=MonthlyPeriodStatus.PENDING_CLOSE,
                total_market_os=Decimal("45000.00"),
            )
            session.add(period)
            await session.commit()
            p_id = period.id

        resp = await client.get(
            f"/api/v1/reports/monthly-periods/{p_id}/review",
            headers=admin_headers(),
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["period_name"] == f"October {test_year}"
        assert data["status"] == "PENDING_CLOSE"
        assert "visits_completed" in data
        assert "collections_submitted_amount" in data
        assert "total_outstanding" in data
        assert data["can_finalize"] is True
    finally:
        async with AsyncSessionLocal() as session:
            await session.execute(
                delete(MonthlyReportingPeriod).where(
                    MonthlyReportingPeriod.period_year == test_year,
                )
            )
            await session.commit()
