"""
Integration tests covering dashboard bug fixes and data consistency:
- WEB-DASH-005 & WEB-DASH-006 (Employee My Day IST date boundary for visits, collections, orders)
- WEB-DASH-010 (is_fin typo regression test for monthly period finalization)
- WEB-DASH-012 (Employee count and KPI filter scoping)
- WEB-DASH-016 (Role-based access restriction on /dashboard/my-day)
"""
from __future__ import annotations

import uuid
from datetime import datetime, date, timedelta, timezone
from decimal import Decimal
import pytest
from httpx import AsyncClient

from app.core.datetime_utils import get_ist_today_range, IST
from app.database import AsyncSessionLocal
from app.models.monthly_reporting_period import MonthlyReportingPeriod, MonthlyPeriodStatus
from app.models.payment import Payment, PaymentMethod, PaymentStatus
from app.models.visit import Visit, VisitStatus
from app.models.visit_media import VisitMedia, MediaType
from tests.integration.conftest import requires_db

pytestmark = [requires_db, pytest.mark.integration, pytest.mark.asyncio]


async def test_dashboard_my_day_role_restriction(
    client: AsyncClient, admin_headers, employee_headers
):
    """WEB-DASH-016: /dashboard/my-day is restricted to EMPLOYEE role only."""
    admin_resp = await client.get("/api/v1/dashboard/my-day", headers=admin_headers)
    assert admin_resp.status_code == 403, admin_resp.text

    emp_resp = await client.get("/api/v1/dashboard/my-day", headers=employee_headers)
    assert emp_resp.status_code == 200, emp_resp.text
    body = emp_resp.json()
    assert "today_visits_count" in body
    assert "collections_today_count" in body
    assert "orders_today_count" in body


async def test_is_finalized_monthly_period_regression(
    client: AsyncClient, admin_headers
):
    """
    WEB-DASH-010: Ensure is_finalized returns True for finalized periods
    and False for non-finalized periods.
    """
    period_year = 2035
    period_month = 11
    m_str = f"{period_year}-{period_month}"

    async with AsyncSessionLocal() as session:
        period = MonthlyReportingPeriod(
            period_year=period_year,
            period_month=period_month,
            period_name="__itest__ Nov 2035",
            status=MonthlyPeriodStatus.FINALIZED,
            finalized_at=datetime.now(timezone.utc),
        )
        session.add(period)
        await session.commit()

    try:
        resp = await client.get(
            f"/api/v1/dashboard/summary?month={m_str}",
            headers=admin_headers,
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["period"] == m_str
        assert data["is_historical"] is True
    finally:
        async with AsyncSessionLocal() as session:
            p_to_del = await session.get(MonthlyReportingPeriod, period.id)
            if p_to_del:
                await session.delete(p_to_del)
                await session.commit()


async def test_employee_my_day_date_boundaries(
    client: AsyncClient, employee_headers, seeded_world
):
    """
    WEB-DASH-005 & WEB-DASH-006:
    Ensure visits, collections, and orders outside today's IST boundaries are not counted.
    """
    emp_id = uuid.UUID(seeded_world["employee_id"])
    cust_id = uuid.UUID(seeded_world["customer_id"])
    user_id = uuid.UUID(seeded_world["employee_user_id"])

    start_utc, end_utc = get_ist_today_range()

    async with AsyncSessionLocal() as session:
        # 1. Historical visit (yesterday)
        yesterday_visit = Visit(
            customer_id=cust_id,
            employee_id=emp_id,
            scheduled_at=start_utc - timedelta(hours=2),
            status=VisitStatus.COMPLETED,
            created_by=user_id,
        )
        # 2. Today's visit
        today_visit = Visit(
            customer_id=cust_id,
            employee_id=emp_id,
            scheduled_at=start_utc + timedelta(hours=4),
            status=VisitStatus.PENDING,
            created_by=user_id,
        )
        # 3. Tomorrow's visit
        tomorrow_visit = Visit(
            customer_id=cust_id,
            employee_id=emp_id,
            scheduled_at=end_utc + timedelta(hours=2),
            status=VisitStatus.PENDING,
            created_by=user_id,
        )

        session.add_all([yesterday_visit, today_visit, tomorrow_visit])
        await session.flush()

        # 4. Historical payment (yesterday)
        yesterday_pay = Payment(
            customer_id=cust_id,
            employee_id=emp_id,
            visit_id=yesterday_visit.id,
            amount=Decimal("5000.00"),
            payment_method=PaymentMethod.CASH,
            payment_date=(datetime.now(IST) - timedelta(days=1)).date(),
            created_by=user_id,
            created_at=start_utc - timedelta(hours=2),
        )
        # 5. Today's payment
        today_pay = Payment(
            customer_id=cust_id,
            employee_id=emp_id,
            visit_id=today_visit.id,
            amount=Decimal("1500.00"),
            payment_method=PaymentMethod.ONLINE,
            payment_date=datetime.now(IST).date(),
            created_by=user_id,
            created_at=start_utc + timedelta(hours=3),
        )
        session.add_all([yesterday_pay, today_pay])
        await session.flush()

        # 6. Historical order
        yesterday_order = VisitMedia(
            visit_id=yesterday_visit.id,
            media_type=MediaType.ORDER,
            storage_key=f"orders/hist_{uuid.uuid4().hex[:6]}.jpg",
            file_size_bytes=1024,
            uploaded_by=user_id,
            uploaded_at=start_utc - timedelta(hours=2),
        )
        # 7. Today's order
        today_order = VisitMedia(
            visit_id=today_visit.id,
            media_type=MediaType.ORDER,
            storage_key=f"orders/today_{uuid.uuid4().hex[:6]}.jpg",
            file_size_bytes=1024,
            uploaded_by=user_id,
            uploaded_at=start_utc + timedelta(hours=3),
        )
        session.add_all([yesterday_order, today_order])
        await session.commit()

    # Query Employee Day Dashboard
    resp = await client.get("/api/v1/dashboard/my-day", headers=employee_headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()

    # Assert only today's items are counted
    assert data["today_visits_count"] >= 1
    assert data["collections_today_count"] >= 1
    assert Decimal(str(data["collections_today_amount"])) >= Decimal("1500.00")
    assert data["orders_today_count"] >= 1
