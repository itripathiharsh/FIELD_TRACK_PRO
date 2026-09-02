from __future__ import annotations

import random
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.core.security import create_access_token
from app.database import AsyncSessionLocal
from app.main import app
from app.models.customer import Customer
from app.models.employee import Employee
from app.models.employee_work_session import EmployeeWorkSession, WorkSessionStatus
from app.models.payment import Payment, PaymentMethod, PaymentSource, PaymentStatus
from app.models.territory import Territory
from app.models.user import Role, User
from app.models.visit import Visit, VisitStatus, VisitType


@pytest_asyncio.fixture
async def workday_setup():
    async with AsyncSessionLocal() as session:
        # Create Territory
        territory = Territory(
            id=uuid.uuid4(),
            name=f"Workday Zone {random.randint(1000, 9999)}",
        )
        session.add(territory)

        # Create Admin User
        admin_user = User(
            id=uuid.uuid4(),
            email=f"admin_workday_{random.randint(1000, 9999)}@example.com",
            password_hash="hash",
            role=Role.ADMIN,
            is_active=True,
        )
        session.add(admin_user)

        # Create Employee User & Employee
        emp_user = User(
            id=uuid.uuid4(),
            email=f"emp_workday_{random.randint(1000, 9999)}@example.com",
            password_hash="hash",
            role=Role.EMPLOYEE,
            is_active=True,
        )
        session.add(emp_user)
        await session.flush()

        employee = Employee(
            id=uuid.uuid4(),
            user_id=emp_user.id,
            full_name="Rajesh Kumar",
            employee_code=f"EMP-WD-{random.randint(1000, 9999)}",
            territory_id=territory.id,
        )
        session.add(employee)

        # Create Customer
        from geoalchemy2.elements import WKTElement
        customer = Customer(
            id=uuid.uuid4(),
            name="Super Electronic Store",
            contact_number=f"+9198{random.randint(10000000, 99999999)}",
            contact_person="Sunil",
            location=WKTElement("SRID=4326;POINT(77.2090 28.6139)"),
            geofence_radius_m=100,
            location_status="VERIFIED",
            outlet_code=f"OUT-WD-{random.randint(1000, 9999)}",
            created_by=admin_user.id,
        )
        session.add(customer)

        # Create Planned Visit
        now = datetime.now(timezone.utc)
        visit_planned = Visit(
            id=uuid.uuid4(),
            customer_id=customer.id,
            employee_id=employee.id,
            scheduled_at=now,
            status=VisitStatus.COMPLETED,
            visit_type=VisitType.PLANNED,
            created_by=admin_user.id,
        )
        session.add(visit_planned)

        # Create Ad-Hoc Visit
        visit_adhoc = Visit(
            id=uuid.uuid4(),
            customer_id=customer.id,
            employee_id=employee.id,
            scheduled_at=now,
            status=VisitStatus.COMPLETED,
            visit_type=VisitType.AD_HOC,
            adhoc_reason="Payment Follow-up",
            created_by=emp_user.id,
        )
        session.add(visit_adhoc)

        # Create Verified Payment
        payment = Payment(
            id=uuid.uuid4(),
            customer_id=customer.id,
            employee_id=employee.id,
            amount=Decimal("45000.00"),
            payment_method=PaymentMethod.ONLINE,
            source=PaymentSource.MANUAL,
            payment_date=now.date(),
            status=PaymentStatus.VERIFIED,
            created_by=emp_user.id,
        )
        session.add(payment)

        await session.commit()

        emp_token = create_access_token(str(emp_user.id), Role.EMPLOYEE)
        admin_token = create_access_token(str(admin_user.id), Role.ADMIN)

        return {
            "admin_user": admin_user,
            "admin_token": admin_token,
            "emp_user": emp_user,
            "employee": employee,
            "emp_token": emp_token,
            "customer": customer,
            "payment": payment,
        }


@pytest.mark.asyncio
async def test_start_workday_success(workday_setup):
    emp_token = workday_setup["emp_token"]
    employee = workday_setup["employee"]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/workday/start",
            headers={"Authorization": f"Bearer {emp_token}"},
            json={
                "latitude": 28.6139,
                "longitude": 77.2090,
                "accuracy_meters": 8.0,
                "notes": "Starting from Central Office",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["employee_id"] == str(employee.id)
        assert data["employee_name"] == "Rajesh Kumar"
        assert data["session"]["status"] == "STARTED"
        assert data["session"]["start_latitude"] == 28.6139
        assert data["session"]["start_longitude"] == 77.2090
        assert data["session"]["start_accuracy_meters"] == 8.0
        assert data["session"]["start_notes"] == "Starting from Central Office"

        # Summary verification
        summary = data["summary"]
        assert summary["total_visits"] == 2
        assert summary["planned_visits"] == 1
        assert summary["adhoc_visits"] == 1
        assert summary["completed_visits"] == 2
        assert float(summary["collections_total_amount"]) == 45000.0


@pytest.mark.asyncio
async def test_duplicate_start_workday_rejected(workday_setup):
    emp_token = workday_setup["emp_token"]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # First start
        r1 = await client.post(
            "/api/v1/workday/start",
            headers={"Authorization": f"Bearer {emp_token}"},
            json={"latitude": 28.6139, "longitude": 77.2090, "accuracy_meters": 5.0},
        )
        assert r1.status_code == 201

        # Second start on same day
        r2 = await client.post(
            "/api/v1/workday/start",
            headers={"Authorization": f"Bearer {emp_token}"},
            json={"latitude": 28.6145, "longitude": 77.2095, "accuracy_meters": 6.0},
        )
        assert r2.status_code == 409
        err_msg = r2.json().get("error", {}).get("message", "") or r2.json().get("detail", "")
        assert "already been started" in err_msg.lower()


@pytest.mark.asyncio
async def test_end_workday_before_start_rejected(workday_setup):
    emp_token = workday_setup["emp_token"]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/workday/end",
            headers={"Authorization": f"Bearer {emp_token}"},
            json={"latitude": 28.6500, "longitude": 77.2300, "accuracy_meters": 10.0},
        )
        assert resp.status_code == 400
        err_msg = resp.json().get("error", {}).get("message", "") or resp.json().get("detail", "")
        assert "cannot end workday before starting" in err_msg.lower()


@pytest.mark.asyncio
async def test_end_workday_success(workday_setup):
    emp_token = workday_setup["emp_token"]
    employee = workday_setup["employee"]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Start day
        r_start = await client.post(
            "/api/v1/workday/start",
            headers={"Authorization": f"Bearer {emp_token}"},
            json={"latitude": 28.6139, "longitude": 77.2090, "accuracy_meters": 5.0},
        )
        assert r_start.status_code == 201

        # End day
        r_end = await client.post(
            "/api/v1/workday/end",
            headers={"Authorization": f"Bearer {emp_token}"},
            json={
                "latitude": 28.6800,
                "longitude": 77.2900,
                "accuracy_meters": 7.5,
                "notes": "Completed all planned and adhoc visits successfully",
            },
        )
        assert r_end.status_code == 200
        data = r_end.json()
        assert data["session"]["status"] == "COMPLETED"
        assert data["session"]["end_latitude"] == 28.6800
        assert data["session"]["end_longitude"] == 77.2900
        assert data["session"]["end_accuracy_meters"] == 7.5
        assert data["session"]["end_notes"] == "Completed all planned and adhoc visits successfully"


@pytest.mark.asyncio
async def test_duplicate_end_workday_rejected(workday_setup):
    emp_token = workday_setup["emp_token"]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post(
            "/api/v1/workday/start",
            headers={"Authorization": f"Bearer {emp_token}"},
            json={"latitude": 28.6139, "longitude": 77.2090},
        )
        r_end1 = await client.post(
            "/api/v1/workday/end",
            headers={"Authorization": f"Bearer {emp_token}"},
            json={"latitude": 28.6800, "longitude": 77.2900},
        )
        assert r_end1.status_code == 200

        # Attempt duplicate end
        r_end2 = await client.post(
            "/api/v1/workday/end",
            headers={"Authorization": f"Bearer {emp_token}"},
            json={"latitude": 28.6800, "longitude": 77.2900},
        )
        assert r_end2.status_code == 409


@pytest.mark.asyncio
async def test_get_today_workday_live_summary(workday_setup):
    emp_token = workday_setup["emp_token"]
    employee = workday_setup["employee"]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Check state before start
        r_pre = await client.get(
            "/api/v1/workday/today",
            headers={"Authorization": f"Bearer {emp_token}"},
        )
        assert r_pre.status_code == 200
        pre_data = r_pre.json()
        assert pre_data["session"] is None
        assert pre_data["summary"]["total_visits"] == 2

        # Start workday
        await client.post(
            "/api/v1/workday/start",
            headers={"Authorization": f"Bearer {emp_token}"},
            json={"latitude": 28.6139, "longitude": 77.2090, "accuracy_meters": 5.0},
        )

        # Check state after start
        r_post = await client.get(
            "/api/v1/workday/today",
            headers={"Authorization": f"Bearer {emp_token}"},
        )
        assert r_post.status_code == 200
        post_data = r_post.json()
        assert post_data["session"]["status"] == "STARTED"
        assert post_data["summary"]["planned_visits"] == 1
        assert post_data["summary"]["adhoc_visits"] == 1
        assert float(post_data["summary"]["collections_total_amount"]) == 45000.0


@pytest.mark.asyncio
async def test_admin_lookup_employee_workday_and_overview(workday_setup):
    emp_token = workday_setup["emp_token"]
    admin_token = workday_setup["admin_token"]
    employee = workday_setup["employee"]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Employee starts and ends day
        await client.post(
            "/api/v1/workday/start",
            headers={"Authorization": f"Bearer {emp_token}"},
            json={"latitude": 28.6139, "longitude": 77.2090, "accuracy_meters": 4.0},
        )
        await client.post(
            "/api/v1/workday/end",
            headers={"Authorization": f"Bearer {emp_token}"},
            json={"latitude": 28.6800, "longitude": 77.2900, "accuracy_meters": 6.0},
        )

        # 1. Admin looks up specific employee
        admin_emp_resp = await client.get(
            f"/api/v1/workday/employees/{employee.id}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert admin_emp_resp.status_code == 200
        emp_data = admin_emp_resp.json()
        assert emp_data["employee_id"] == str(employee.id)
        assert emp_data["session"]["status"] == "COMPLETED"
        assert emp_data["summary"]["total_visits"] == 2
        assert float(emp_data["summary"]["collections_total_amount"]) == 45000.0

        # 2. Admin queries organization-wide daily field overview
        admin_overview_resp = await client.get(
            "/api/v1/workday/overview/today",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert admin_overview_resp.status_code == 200
        ov_data = admin_overview_resp.json()
        assert ov_data["employees_completed"] >= 1
        assert ov_data["total_visits"] >= 2
        assert float(ov_data["total_collections_amount"]) >= 45000.0
        assert len(ov_data["sessions"]) >= 1
