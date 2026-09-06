"""
Unit and integration tests for Visit Planning Analytics & Planned vs Actual integration (Phase 2D).
Validates:
1. Zero planned visits handling (completion_rate is None, no division by zero).
2. Deterministic planned -> actual matching (same employee + customer + calendar date).
3. Completed vs Missed vs Extra/Unplanned vs Cancelled distinctions.
4. Future planned visits are not marked as missed.
5. Soft-cancelled visits are tracked as cancelled and excluded from active planned/missed counts.
6. Averages calculation with explicit denominators (active planned days, active execution days).
7. Behind schedule deterministic indicator.
8. Daily analytics breakdown.
9. Team analytics aggregation and employee filter.
10. Strict RBAC enforcement across all analytics endpoints.
"""
import uuid
from datetime import date, datetime, timedelta, timezone
import pytest
import pytest_asyncio
from httpx import AsyncClient

from app.core.datetime_utils import get_ist_now
from app.core.security import create_access_token, hash_password
from app.database import AsyncSessionLocal
from app.models.customer import Customer
from app.models.employee import Employee
from app.models.monthly_visit_plan import MonthlyVisitPlan, PlannedVisit, PlannedVisitStatus
from app.models.requirement_form import Priority
from app.models.user import Role, User
from app.models.visit import Visit, VisitStatus, VisitType
from tests.conftest import requires_db


@pytest_asyncio.fixture
async def analytics_test_setup():
    async with AsyncSessionLocal() as session:
        # Admin User
        admin_user = User(
            email=f"admin_an_{uuid.uuid4().hex[:6]}@fieldtrack.test",
            password_hash=hash_password("AdminPass123!"),
            role=Role.ADMIN,
            is_active=True,
        )
        # Employee A
        emp_a_user = User(
            email=f"emp_a_an_{uuid.uuid4().hex[:6]}@fieldtrack.test",
            password_hash=hash_password("EmpPass123!"),
            role=Role.EMPLOYEE,
            is_active=True,
        )
        # Employee B
        emp_b_user = User(
            email=f"emp_b_an_{uuid.uuid4().hex[:6]}@fieldtrack.test",
            password_hash=hash_password("EmpPass123!"),
            role=Role.EMPLOYEE,
            is_active=True,
        )
        session.add_all([admin_user, emp_a_user, emp_b_user])
        await session.flush()

        employee_a = Employee(
            user_id=emp_a_user.id,
            full_name="Rajesh Kumar",
            employee_code=f"EMP-{uuid.uuid4().hex[:6].upper()}",
        )
        employee_b = Employee(
            user_id=emp_b_user.id,
            full_name="Sunita Rao",
            employee_code=f"EMP-{uuid.uuid4().hex[:6].upper()}",
        )
        session.add_all([employee_a, employee_b])
        await session.flush()

        # Customers
        cust_1 = Customer(
            name="Super Store A",
            outlet_code=f"OUT-{uuid.uuid4().hex[:6].upper()}",
            address="Delhi Road",
            location="POINT(77.2090 28.6139)",
            geofence_radius_m=100,
            location_status="VERIFIED",
            created_by=admin_user.id,
        )
        cust_2 = Customer(
            name="Kirana Mart B",
            outlet_code=f"OUT-{uuid.uuid4().hex[:6].upper()}",
            address="Noida Road",
            location="POINT(77.3200 28.5700)",
            geofence_radius_m=100,
            location_status="VERIFIED",
            created_by=admin_user.id,
        )
        cust_3 = Customer(
            name="Mega Mart C",
            outlet_code=f"OUT-{uuid.uuid4().hex[:6].upper()}",
            address="Gurgaon Road",
            location="POINT(77.0266 28.4595)",
            geofence_radius_m=100,
            location_status="VERIFIED",
            created_by=admin_user.id,
        )
        session.add_all([cust_1, cust_2, cust_3])
        await session.commit()

        admin_token = create_access_token(str(admin_user.id), Role.ADMIN.value)
        emp_a_token = create_access_token(str(emp_a_user.id), Role.EMPLOYEE.value)
        emp_b_token = create_access_token(str(emp_b_user.id), Role.EMPLOYEE.value)

        return {
            "admin_user_id": str(admin_user.id),
            "admin_token": admin_token,
            "emp_a_user_id": str(emp_a_user.id),
            "emp_a_id": str(employee_a.id),
            "emp_a_token": emp_a_token,
            "emp_b_user_id": str(emp_b_user.id),
            "emp_b_id": str(employee_b.id),
            "emp_b_token": emp_b_token,
            "cust_1_id": str(cust_1.id),
            "cust_2_id": str(cust_2.id),
            "cust_3_id": str(cust_3.id),
        }


@pytest.mark.asyncio
async def test_zero_planned_visits_analytics(client: AsyncClient, analytics_test_setup: dict):
    """When an employee has no planned visits, completion_rate must be None (not 0 or 100)."""
    setup = analytics_test_setup
    headers = {"Authorization": f"Bearer {setup['emp_a_token']}"}

    res = await client.get("/api/v1/visit-planning/analytics/my-month?year=2026&month=9", headers=headers)
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["employee_id"] == setup["emp_a_id"]
    assert data["total_planned"] == 0
    assert data["completed"] == 0
    assert data["missed"] == 0
    assert data["cancelled"] == 0
    assert data["extra_unplanned"] == 0
    assert data["completion_rate"] is None
    assert data["active_planned_days"] == 0
    assert data["active_execution_days"] == 0
    assert data["avg_planned_per_active_day"] is None
    assert data["avg_completed_per_execution_day"] is None
    assert data["behind_schedule"] is False


@pytest.mark.asyncio
async def test_planned_vs_actual_matching_and_metrics(client: AsyncClient, analytics_test_setup: dict):
    """
    Test scenario with:
    - 1 planned visit in past completed by matching actual visit -> completed=1
    - 1 planned visit in past NOT completed -> missed=1
    - 1 planned visit in future -> total_planned=3, NOT missed
    - 1 planned visit cancelled -> cancelled=1, not in total_planned
    - 1 extra/unplanned actual visit -> extra_unplanned=1
    """
    setup = analytics_test_setup
    admin_headers = {"Authorization": f"Bearer {setup['admin_token']}"}
    emp_headers = {"Authorization": f"Bearer {setup['emp_a_token']}"}

    today = get_ist_now().date()
    # Past date in current month (or adjust if today is 1st of month)
    if today.day > 2:
        past_date_1 = today - timedelta(days=2)
        past_date_2 = today - timedelta(days=1)
    else:
        past_date_1 = date(today.year, today.month, 1)
        past_date_2 = date(today.year, today.month, 1)
    
    # Future date in current month (or next month if near end)
    future_date = today + timedelta(days=5)

    year = today.year
    month = today.month

    # 1. Create planned visit 1 (past) via admin
    res1 = await client.post(
        "/api/v1/visit-planning/visits",
        headers=admin_headers,
        json={
            "customer_id": setup["cust_1_id"],
            "planned_date": past_date_1.isoformat(),
            "employee_id": setup["emp_a_id"],
            "priority": "HIGH",
        },
    )
    assert res1.status_code == 201, res1.text
    pv1_id = res1.json()["id"]

    # 2. Create planned visit 2 (past, to be missed) via admin
    res2 = await client.post(
        "/api/v1/visit-planning/visits",
        headers=admin_headers,
        json={
            "customer_id": setup["cust_2_id"],
            "planned_date": past_date_1.isoformat(),
            "employee_id": setup["emp_a_id"],
            "priority": "MEDIUM",
        },
    )
    assert res2.status_code == 201, res2.text

    # 3. Create planned visit 3 (future date)
    res3 = await client.post(
        "/api/v1/visit-planning/visits",
        headers=emp_headers,
        json={
            "customer_id": setup["cust_3_id"],
            "planned_date": future_date.isoformat(),
            "priority": "LOW",
        },
    )
    assert res3.status_code == 201, res3.text

    # 4. Create planned visit 4 to be cancelled
    res4 = await client.post(
        "/api/v1/visit-planning/visits",
        headers=emp_headers,
        json={
            "customer_id": setup["cust_1_id"],
            "planned_date": future_date.isoformat(),
            "priority": "LOW",
        },
    )
    assert res4.status_code == 201, res4.text
    pv4_id = res4.json()["id"]

    # Cancel planned visit 4
    del_res = await client.delete(f"/api/v1/visit-planning/visits/{pv4_id}", headers=emp_headers)
    assert del_res.status_code == 204

    # 5. Create actual visits directly in DB
    async with AsyncSessionLocal() as session:
        # Actual visit A: matches pv1 (same emp, same cust_1, same past_date_1) and is COMPLETED
        visit_completed = Visit(
            customer_id=uuid.UUID(setup["cust_1_id"]),
            employee_id=uuid.UUID(setup["emp_a_id"]),
            scheduled_at=datetime(past_date_1.year, past_date_1.month, past_date_1.day, 10, 0, tzinfo=timezone(timedelta(hours=5, minutes=30))).astimezone(timezone.utc),
            status=VisitStatus.COMPLETED,
            visit_type=VisitType.PLANNED,
            created_by=uuid.UUID(setup["admin_user_id"]),
        )
        # Actual visit B: extra visit to cust_3 on past_date_1 (not planned on that day)
        visit_extra = Visit(
            customer_id=uuid.UUID(setup["cust_3_id"]),
            employee_id=uuid.UUID(setup["emp_a_id"]),
            scheduled_at=datetime(past_date_1.year, past_date_1.month, past_date_1.day, 14, 0, tzinfo=timezone(timedelta(hours=5, minutes=30))).astimezone(timezone.utc),
            status=VisitStatus.COMPLETED,
            visit_type=VisitType.AD_HOC,
            created_by=uuid.UUID(setup["admin_user_id"]),
        )
        session.add_all([visit_completed, visit_extra])
        await session.commit()

    # Query Employee A analytics
    res_an = await client.get(
        f"/api/v1/visit-planning/analytics/my-month?year={year}&month={month}",
        headers=emp_headers,
    )
    assert res_an.status_code == 200, res_an.text
    an = res_an.json()

    assert an["total_planned"] == 3  # pv1, pv2, pv3 (pv4 is cancelled)
    assert an["completed"] == 1       # pv1 matched with visit_completed
    assert an["cancelled"] == 1       # pv4
    assert an["extra_unplanned"] == 1 # visit_extra
    if past_date_1 < today:
        assert an["missed"] >= 1      # pv2 was not completed on past date
    assert an["completion_rate"] == round((1 / 3) * 100, 1)
    assert an["active_planned_days"] >= 1
    assert an["active_execution_days"] >= 1


@pytest.mark.asyncio
async def test_daily_analytics_breakdown(client: AsyncClient, analytics_test_setup: dict):
    """Daily analytics returns correct metrics for employee on specific date."""
    setup = analytics_test_setup
    emp_headers = {"Authorization": f"Bearer {setup['emp_a_token']}"}
    today = get_ist_now().date()
    target_date = today + timedelta(days=3)

    # Create 2 planned visits on target_date
    await client.post(
        "/api/v1/visit-planning/visits",
        headers=emp_headers,
        json={"customer_id": setup["cust_1_id"], "planned_date": target_date.isoformat()},
    )
    await client.post(
        "/api/v1/visit-planning/visits",
        headers=emp_headers,
        json={"customer_id": setup["cust_2_id"], "planned_date": target_date.isoformat()},
    )

    res = await client.get(
        f"/api/v1/visit-planning/analytics/daily?employee_id={setup['emp_a_id']}&date={target_date.isoformat()}",
        headers=emp_headers,
    )
    assert res.status_code == 200, res.text
    daily = res.json()
    assert daily["planned"] == 2
    assert daily["completed"] == 0
    assert daily["missed"] == 0  # future date -> not missed
    assert daily["extra_unplanned"] == 0


@pytest.mark.asyncio
async def test_team_monthly_analytics_and_filter(client: AsyncClient, analytics_test_setup: dict):
    """Admin team analytics aggregates all employees and supports employee filtering."""
    setup = analytics_test_setup
    admin_headers = {"Authorization": f"Bearer {setup['admin_token']}"}
    today = get_ist_now().date()
    year = today.year
    month = today.month

    # Admin calls team analytics without filter
    res = await client.get(
        f"/api/v1/visit-planning/analytics/team?year={year}&month={month}",
        headers=admin_headers,
    )
    assert res.status_code == 200, res.text
    team_data = res.json()
    assert "employees" in team_data
    assert "team_total_planned" in team_data
    assert "team_completed" in team_data
    assert "team_missed" in team_data

    # Admin calls team analytics with employee filter
    res_filtered = await client.get(
        f"/api/v1/visit-planning/analytics/team?year={year}&month={month}&employee_id={setup['emp_a_id']}",
        headers=admin_headers,
    )
    assert res_filtered.status_code == 200, res_filtered.text
    filtered_data = res_filtered.json()
    assert len(filtered_data["employees"]) == 1
    assert filtered_data["employees"][0]["employee_id"] == setup["emp_a_id"]


@pytest.mark.asyncio
async def test_rbac_analytics_endpoints(client: AsyncClient, analytics_test_setup: dict):
    """Employees cannot access other employees' analytics or admin team analytics."""
    setup = analytics_test_setup
    emp_a_headers = {"Authorization": f"Bearer {setup['emp_a_token']}"}
    admin_headers = {"Authorization": f"Bearer {setup['admin_token']}"}
    today = get_ist_now().date()

    # 1. Employee calling /analytics/team -> 403
    res1 = await client.get("/api/v1/visit-planning/analytics/team?year=2026&month=9", headers=emp_a_headers)
    assert res1.status_code == 403

    # 2. Employee calling /analytics/employee/{other_emp_id} -> 403
    res2 = await client.get(
        f"/api/v1/visit-planning/analytics/employee/{setup['emp_b_id']}?year=2026&month=9",
        headers=emp_a_headers,
    )
    assert res2.status_code == 403

    # 3. Employee calling /analytics/daily for another employee -> 403
    res3 = await client.get(
        f"/api/v1/visit-planning/analytics/daily?employee_id={setup['emp_b_id']}&date={today.isoformat()}",
        headers=emp_a_headers,
    )
    assert res3.status_code == 403

    # 4. Admin calling /analytics/employee/{emp_a_id} -> 200
    res4 = await client.get(
        f"/api/v1/visit-planning/analytics/employee/{setup['emp_a_id']}?year=2026&month=9",
        headers=admin_headers,
    )
    assert res4.status_code == 200

    # 5. Admin calling /analytics/daily for any employee -> 200
    res5 = await client.get(
        f"/api/v1/visit-planning/analytics/daily?employee_id={setup['emp_a_id']}&date={today.isoformat()}",
        headers=admin_headers,
    )
    assert res5.status_code == 200
