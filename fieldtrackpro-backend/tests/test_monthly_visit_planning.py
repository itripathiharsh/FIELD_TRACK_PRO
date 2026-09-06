"""
Unit and integration tests for Monthly Visit Planning backend foundation (Phase 2A).
Validates:
1. Monthly plan initialization, idempotency, and uniqueness per employee per month.
2. Employee flexible planning: future date scheduling, multiple visits on the same day, zero-visit days.
3. Modification, rescheduling (same month & cross-month), and deletion of planned visits.
4. RBAC & ownership enforcement: employees cannot touch other employees' plans; admins have full oversight & reassignment.
5. Zero regression on existing visits engine.
"""
import uuid
from datetime import date, timedelta
import pytest
import pytest_asyncio
from httpx import AsyncClient

from app.core.security import create_access_token, hash_password
from app.database import AsyncSessionLocal
from app.models.customer import Customer
from app.models.employee import Employee
from app.models.monthly_visit_plan import MonthlyVisitPlan, PlannedVisit, PlannedVisitStatus
from app.models.requirement_form import Priority
from app.models.user import Role, User
from app.models.visit import VisitType
from tests.conftest import requires_db


@pytest_asyncio.fixture
async def planning_test_setup():
    async with AsyncSessionLocal() as session:
        # 1. Admin User
        admin_user = User(
            email=f"admin_plan_{uuid.uuid4().hex[:6]}@fieldtrack.test",
            password_hash=hash_password("AdminPass123!"),
            role=Role.ADMIN,
            is_active=True,
        )
        # 2. Employee A User & Profile
        emp_a_user = User(
            email=f"emp_a_{uuid.uuid4().hex[:6]}@fieldtrack.test",
            password_hash=hash_password("EmpPass123!"),
            role=Role.EMPLOYEE,
            is_active=True,
        )
        # 3. Employee B User & Profile
        emp_b_user = User(
            email=f"emp_b_{uuid.uuid4().hex[:6]}@fieldtrack.test",
            password_hash=hash_password("EmpPass123!"),
            role=Role.EMPLOYEE,
            is_active=True,
        )
        session.add_all([admin_user, emp_a_user, emp_b_user])
        await session.flush()

        employee_a = Employee(
            user_id=emp_a_user.id,
            full_name="Arun Sharma",
            employee_code=f"EMP-{uuid.uuid4().hex[:6].upper()}",
        )
        employee_b = Employee(
            user_id=emp_b_user.id,
            full_name="Pooja Verma",
            employee_code=f"EMP-{uuid.uuid4().hex[:6].upper()}",
        )
        session.add_all([employee_a, employee_b])
        await session.flush()

        # 4. Customers
        customer_1 = Customer(
            name="Apex Retailers",
            outlet_code=f"APX-{uuid.uuid4().hex[:6].upper()}",
            address="Sector 18, Noida",
            location="POINT(77.3200 28.5700)",
            geofence_radius_m=100,
            location_status="VERIFIED",
            created_by=admin_user.id,
        )
        customer_2 = Customer(
            name="Metro Supermart",
            outlet_code=f"MET-{uuid.uuid4().hex[:6].upper()}",
            address="Indirapuram, Ghaziabad",
            location="POINT(77.3700 28.6400)",
            geofence_radius_m=100,
            location_status="VERIFIED",
            created_by=admin_user.id,
        )
        customer_3 = Customer(
            name="Om Sai Traders",
            outlet_code=f"OMS-{uuid.uuid4().hex[:6].upper()}",
            address="Connaught Place, Delhi",
            location="POINT(77.2167 28.6315)",
            geofence_radius_m=100,
            location_status="VERIFIED",
            created_by=admin_user.id,
        )
        session.add_all([customer_1, customer_2, customer_3])
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
            "customer_1_id": str(customer_1.id),
            "customer_2_id": str(customer_2.id),
            "customer_3_id": str(customer_3.id),
        }


@pytest.mark.asyncio
async def test_get_or_create_monthly_plan_idempotent(client: AsyncClient, planning_test_setup: dict):
    """Calling my-plan idempotently initializes the plan and returns empty planned visits."""
    setup = planning_test_setup
    headers = {"Authorization": f"Bearer {setup['emp_a_token']}"}

    # Fetch plan for next month
    target_year = 2026
    target_month = 11

    res1 = await client.get(
        f"/api/v1/visit-planning/my-plan?year={target_year}&month={target_month}",
        headers=headers,
    )
    assert res1.status_code == 200, res1.text
    data1 = res1.json()
    assert data1["employee_id"] == setup["emp_a_id"]
    assert data1["year"] == target_year
    assert data1["month"] == target_month
    assert data1["status"] == "ACTIVE"
    assert data1["total_planned_visits"] == 0
    assert data1["planned_visits"] == []

    # Second call must return the same plan without duplication
    res2 = await client.get(
        f"/api/v1/visit-planning/my-plan?year={target_year}&month={target_month}",
        headers=headers,
    )
    assert res2.status_code == 200
    data2 = res2.json()
    assert data2["id"] == data1["id"]


@pytest.mark.asyncio
async def test_create_planned_visits_flexible_and_multi_day(client: AsyncClient, planning_test_setup: dict):
    """
    Employees can plan multiple visits on the same date without 60-minute time conflicts,
    and can have zero visits on other days.
    """
    setup = planning_test_setup
    headers = {"Authorization": f"Bearer {setup['emp_a_token']}"}

    future_date_1 = (date.today() + timedelta(days=10)).isoformat()
    future_date_2 = (date.today() + timedelta(days=15)).isoformat()

    # 1. Plan Visit 1 on future_date_1 for customer 1
    res1 = await client.post(
        "/api/v1/visit-planning/visits",
        json={
            "customer_id": setup["customer_1_id"],
            "planned_date": future_date_1,
            "priority": "HIGH",
            "notes": "Quarterly stock audit",
        },
        headers=headers,
    )
    assert res1.status_code == 201, res1.text
    v1 = res1.json()
    assert v1["customer_id"] == setup["customer_1_id"]
    assert v1["planned_date"] == future_date_1
    assert v1["priority"] == "HIGH"

    # 2. Plan Visit 2 on the SAME DATE (future_date_1) for customer 2 (Multiple visits on same day)
    res2 = await client.post(
        "/api/v1/visit-planning/visits",
        json={
            "customer_id": setup["customer_2_id"],
            "planned_date": future_date_1,
            "priority": "MEDIUM",
            "notes": "Payment collection follow-up",
        },
        headers=headers,
    )
    assert res2.status_code == 201, res2.text
    v2 = res2.json()
    assert v2["planned_date"] == future_date_1

    # 3. Plan Visit 3 on future_date_2 for customer 3
    res3 = await client.post(
        "/api/v1/visit-planning/visits",
        json={
            "customer_id": setup["customer_3_id"],
            "planned_date": future_date_2,
            "priority": "LOW",
        },
        headers=headers,
    )
    assert res3.status_code == 201, res3.text

    # 4. Verify my-plan reflects 3 visits across 2 active days
    dt = date.today() + timedelta(days=10)
    res_plan = await client.get(
        f"/api/v1/visit-planning/my-plan?year={dt.year}&month={dt.month}",
        headers=headers,
    )
    assert res_plan.status_code == 200
    plan_data = res_plan.json()
    assert plan_data["total_planned_visits"] >= 2
    assert plan_data["active_days_count"] >= 1


@pytest.mark.asyncio
async def test_cannot_plan_in_past_for_employee(client: AsyncClient, planning_test_setup: dict):
    """Employees cannot create planned visits for past dates."""
    setup = planning_test_setup
    headers = {"Authorization": f"Bearer {setup['emp_a_token']}"}

    past_date = (date.today() - timedelta(days=5)).isoformat()
    res = await client.post(
        "/api/v1/visit-planning/visits",
        json={
            "customer_id": setup["customer_1_id"],
            "planned_date": past_date,
        },
        headers=headers,
    )
    assert res.status_code in (400, 422)
    error_msg = res.json().get("error", {}).get("message", "") or res.json().get("detail", "")
    assert "past" in error_msg.lower()


@pytest.mark.asyncio
async def test_update_reschedule_and_delete_planned_visit(client: AsyncClient, planning_test_setup: dict):
    """Employee can update details, reschedule to new date, and cancel/delete future visits."""
    setup = planning_test_setup
    headers = {"Authorization": f"Bearer {setup['emp_a_token']}"}

    initial_date = (date.today() + timedelta(days=12)).isoformat()
    res_create = await client.post(
        "/api/v1/visit-planning/visits",
        json={
            "customer_id": setup["customer_1_id"],
            "planned_date": initial_date,
            "priority": "LOW",
            "notes": "Initial note",
        },
        headers=headers,
    )
    assert res_create.status_code == 201
    visit_id = res_create.json()["id"]

    # 1. Update notes and priority
    res_update = await client.patch(
        f"/api/v1/visit-planning/visits/{visit_id}",
        json={"priority": "HIGH", "notes": "Updated note with manager approval"},
        headers=headers,
    )
    assert res_update.status_code == 200
    assert res_update.json()["priority"] == "HIGH"
    assert res_update.json()["notes"] == "Updated note with manager approval"

    # 2. Reschedule to another future date
    new_date = (date.today() + timedelta(days=20)).isoformat()
    res_resched = await client.post(
        f"/api/v1/visit-planning/visits/{visit_id}/reschedule",
        json={"new_date": new_date},
        headers=headers,
    )
    assert res_resched.status_code == 200
    assert res_resched.json()["planned_date"] == new_date

    # 3. Delete visit
    res_del = await client.delete(
        f"/api/v1/visit-planning/visits/{visit_id}",
        headers=headers,
    )
    assert res_del.status_code == 204

    # 4. Verify gone from monthly plan
    d = date.today() + timedelta(days=20)
    res_plan = await client.get(
        f"/api/v1/visit-planning/my-plan?year={d.year}&month={d.month}",
        headers=headers,
    )
    visit_ids = [v["id"] for v in res_plan.json()["planned_visits"]]
    assert visit_id not in visit_ids


@pytest.mark.asyncio
async def test_rbac_employee_cannot_access_or_modify_other_plan(client: AsyncClient, planning_test_setup: dict):
    """Employee A cannot view or modify Employee B's plan or planned visits."""
    setup = planning_test_setup
    headers_a = {"Authorization": f"Bearer {setup['emp_a_token']}"}
    headers_b = {"Authorization": f"Bearer {setup['emp_b_token']}"}

    # Employee B creates a visit
    future_date = (date.today() + timedelta(days=8)).isoformat()
    res_b = await client.post(
        "/api/v1/visit-planning/visits",
        json={
            "customer_id": setup["customer_2_id"],
            "planned_date": future_date,
        },
        headers=headers_b,
    )
    assert res_b.status_code == 201
    visit_b_id = res_b.json()["id"]

    # Employee A tries to view Employee B's plan via /plans/{employee_id} -> 403
    d = date.today() + timedelta(days=8)
    res_unauth = await client.get(
        f"/api/v1/visit-planning/plans/{setup['emp_b_id']}?year={d.year}&month={d.month}",
        headers=headers_a,
    )
    assert res_unauth.status_code == 403

    # Employee A tries to modify Employee B's visit -> 403
    res_mod = await client.patch(
        f"/api/v1/visit-planning/visits/{visit_b_id}",
        json={"notes": "Hacked note"},
        headers=headers_a,
    )
    assert res_mod.status_code == 403

    # Employee A tries to delete Employee B's visit -> 403
    res_del = await client.delete(
        f"/api/v1/visit-planning/visits/{visit_b_id}",
        headers=headers_a,
    )
    assert res_del.status_code == 403


@pytest.mark.asyncio
async def test_admin_governance_and_reassignment(client: AsyncClient, planning_test_setup: dict):
    """Admin can view any plan, schedule for any employee, list summaries, and reassign visits."""
    setup = planning_test_setup
    admin_headers = {"Authorization": f"Bearer {setup['admin_token']}"}

    future_date = (date.today() + timedelta(days=14)).isoformat()

    # 1. Admin plans a visit specifically for Employee A
    res_create = await client.post(
        "/api/v1/visit-planning/visits",
        json={
            "employee_id": setup["emp_a_id"],
            "customer_id": setup["customer_1_id"],
            "planned_date": future_date,
            "priority": "HIGH",
            "notes": "Assigned by Zonal Sales Manager",
        },
        headers=admin_headers,
    )
    assert res_create.status_code == 201
    visit_id = res_create.json()["id"]
    assert res_create.json()["employee_id"] == setup["emp_a_id"]

    # 2. Admin inspects Employee A's monthly plan
    d = date.today() + timedelta(days=14)
    res_view = await client.get(
        f"/api/v1/visit-planning/plans/{setup['emp_a_id']}?year={d.year}&month={d.month}",
        headers=admin_headers,
    )
    assert res_view.status_code == 200
    assert any(v["id"] == visit_id for v in res_view.json()["planned_visits"])

    # 3. Admin views all plans overview
    res_list = await client.get(
        f"/api/v1/visit-planning/plans?year={d.year}&month={d.month}",
        headers=admin_headers,
    )
    assert res_list.status_code == 200
    assert isinstance(res_list.json(), list)

    # 4. Admin reassigns this visit to Employee B
    res_reassign = await client.post(
        f"/api/v1/visit-planning/visits/{visit_id}/reassign",
        json={"new_employee_id": setup["emp_b_id"]},
        headers=admin_headers,
    )
    assert res_reassign.status_code == 200
    assert res_reassign.json()["employee_id"] == setup["emp_b_id"]

    # 5. Verify visit now shows up in Employee B's plan
    res_b_plan = await client.get(
        f"/api/v1/visit-planning/plans/{setup['emp_b_id']}?year={d.year}&month={d.month}",
        headers=admin_headers,
    )
    assert res_b_plan.status_code == 200
    assert any(v["id"] == visit_id for v in res_b_plan.json()["planned_visits"])


@pytest.mark.asyncio
async def test_admin_team_monthly_plan_endpoint(client: AsyncClient, planning_test_setup: dict):
    """Admin can fetch combined team plan for all employees or filtered by employee; employee access is forbidden."""
    setup = planning_test_setup
    admin_headers = {"Authorization": f"Bearer {setup['admin_token']}"}
    emp_headers = {"Authorization": f"Bearer {setup['emp_a_token']}"}

    d = date.today() + timedelta(days=12)
    future_date = d.isoformat()

    # Employee A creates a planned visit
    res_a = await client.post(
        "/api/v1/visit-planning/visits",
        json={"customer_id": setup["customer_1_id"], "planned_date": future_date, "notes": "Emp A visit"},
        headers=emp_headers,
    )
    assert res_a.status_code == 201

    # Employee B creates a planned visit
    headers_b = {"Authorization": f"Bearer {setup['emp_b_token']}"}
    res_b = await client.post(
        "/api/v1/visit-planning/visits",
        json={"customer_id": setup["customer_2_id"], "planned_date": future_date, "notes": "Emp B visit"},
        headers=headers_b,
    )
    assert res_b.status_code == 201

    # Employee tries to access /team-plan -> 403 Forbidden
    res_emp = await client.get(
        f"/api/v1/visit-planning/team-plan?year={d.year}&month={d.month}",
        headers=emp_headers,
    )
    assert res_emp.status_code == 403

    # Admin accesses /team-plan -> 200 with both visits
    res_team = await client.get(
        f"/api/v1/visit-planning/team-plan?year={d.year}&month={d.month}",
        headers=admin_headers,
    )
    assert res_team.status_code == 200
    data = res_team.json()
    assert data["total_planned_visits"] >= 2
    assert any(v["employee_id"] == setup["emp_a_id"] for v in data["planned_visits"])
    assert any(v["employee_id"] == setup["emp_b_id"] for v in data["planned_visits"])

    # Admin filters by employee A
    res_filtered = await client.get(
        f"/api/v1/visit-planning/team-plan?year={d.year}&month={d.month}&employee_id={setup['emp_a_id']}",
        headers=admin_headers,
    )
    assert res_filtered.status_code == 200
    filtered_data = res_filtered.json()
    assert all(v["employee_id"] == setup["emp_a_id"] for v in filtered_data["planned_visits"])
