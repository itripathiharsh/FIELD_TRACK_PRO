"""
Tests for Off-Beat / Ad-Hoc Visits (P2: Ad-Hoc Visit Flow).
Validates:
- Creation of ad-hoc visits with lightweight business reasons & notes
- Classification: PLANNED vs AD_HOC
- GPS / Geofence security enforcement (geofence rules are NEVER weakened for ad-hoc visits)
- Admin filtering by visit_type (PLANNED vs AD_HOC)
- Employee Activity planned vs ad-hoc daily telemetry aggregation
"""
import uuid
from datetime import datetime, timezone
import pytest
import pytest_asyncio
from httpx import AsyncClient

from app.core.security import create_access_token, hash_password
from app.database import AsyncSessionLocal
from app.models.customer import Customer
from app.models.employee import Employee
from app.models.user import Role, User
from app.models.visit import Visit, VisitStatus, VisitType
from tests.conftest import requires_db


@pytest_asyncio.fixture
async def adhoc_test_setup():
    async with AsyncSessionLocal() as session:
        # 1. Admin User
        admin_user = User(
            email=f"admin_adhoc_{uuid.uuid4().hex[:6]}@fieldtrack.test",
            password_hash=hash_password("AdminPass123!"),
            role=Role.ADMIN,
            is_active=True,
        )
        # 2. Employee User & Employee Profile
        emp_user = User(
            email=f"emp_adhoc_{uuid.uuid4().hex[:6]}@fieldtrack.test",
            password_hash=hash_password("EmpPass123!"),
            role=Role.EMPLOYEE,
            is_active=True,
        )
        session.add_all([admin_user, emp_user])
        await session.flush()

        employee = Employee(
            user_id=emp_user.id,
            full_name="Rajesh Kumar",
            employee_code=f"EMP-{uuid.uuid4().hex[:6].upper()}",
        )
        session.add(employee)
        await session.flush()

        # 3. Customer 1 (Planned beat customer) - located in Connaught Place, Delhi (28.6315, 77.2167)
        planned_customer = Customer(
            name="Delhi Electricals",
            outlet_code=f"DEL-{uuid.uuid4().hex[:6].upper()}",
            address="Connaught Place, New Delhi",
            location="POINT(77.2167 28.6315)",
            geofence_radius_m=100,
            location_status="VERIFIED",
            created_by=admin_user.id,
        )
        # 4. Customer 2 (Off-beat / outside beat customer) - located in Nehru Place, Delhi (28.5494, 77.2528)
        offbeat_customer = Customer(
            name="Nehru Tech Hub",
            outlet_code=f"NEH-{uuid.uuid4().hex[:6].upper()}",
            address="Nehru Place, New Delhi",
            location="POINT(77.2528 28.5494)",
            geofence_radius_m=100,
            location_status="VERIFIED",
            created_by=admin_user.id,
        )
        session.add_all([planned_customer, offbeat_customer])
        await session.flush()

        # 5. Create a planned visit for Customer 1 for today
        planned_visit = Visit(
            customer_id=planned_customer.id,
            employee_id=employee.id,
            scheduled_at=datetime.now(timezone.utc),
            status=VisitStatus.PENDING,
            visit_type=VisitType.PLANNED,
            created_by=admin_user.id,
        )
        session.add(planned_visit)
        await session.commit()

        admin_token = create_access_token(str(admin_user.id), Role.ADMIN.value)
        emp_token = create_access_token(str(emp_user.id), Role.EMPLOYEE.value)

        return {
            "admin_user_id": str(admin_user.id),
            "emp_user_id": str(emp_user.id),
            "employee_id": str(employee.id),
            "planned_customer_id": str(planned_customer.id),
            "offbeat_customer_id": str(offbeat_customer.id),
            "planned_visit_id": str(planned_visit.id),
            "admin_token": admin_token,
            "emp_token": emp_token,
        }


@requires_db
@pytest.mark.asyncio
async def test_create_adhoc_visit_outside_beat(client: AsyncClient, adhoc_test_setup):
    data = adhoc_test_setup
    payload = {
        "customer_id": data["offbeat_customer_id"],
        "adhoc_reason": "Payment Follow-up",
        "adhoc_notes": "Customer requested urgent cheque collection",
    }

    resp = await client.post(
        "/api/v1/visits/ad-hoc",
        json=payload,
        headers={"Authorization": f"Bearer {data['emp_token']}"},
    )
    assert resp.status_code == 201, resp.text
    res_data = resp.json()
    assert res_data["visit_type"] == "AD_HOC"
    assert res_data["adhoc_reason"] == "Payment Follow-up"
    assert res_data["adhoc_notes"] == "Customer requested urgent cheque collection"
    assert res_data["customer_id"] == data["offbeat_customer_id"]
    assert res_data["employee_id"] == data["employee_id"]
    assert res_data["status"] == "PENDING"


@requires_db
@pytest.mark.asyncio
async def test_adhoc_visit_matches_existing_planned_visit_without_duplication(client: AsyncClient, adhoc_test_setup):
    data = adhoc_test_setup
    # Requesting ad-hoc for a customer who already has today's planned visit returns the existing planned visit
    payload = {
        "customer_id": data["planned_customer_id"],
        "adhoc_reason": "Urgent Collection",
    }

    resp = await client.post(
        "/api/v1/visits/ad-hoc",
        json=payload,
        headers={"Authorization": f"Bearer {data['emp_token']}"},
    )
    assert resp.status_code == 201, resp.text
    res_data = resp.json()
    assert res_data["id"] == data["planned_visit_id"]
    assert res_data["visit_type"] == "PLANNED"


@requires_db
@pytest.mark.asyncio
async def test_adhoc_visit_gps_geofence_verification_enforced(client: AsyncClient, adhoc_test_setup):
    data = adhoc_test_setup
    # 1. Create ad-hoc visit to Nehru Tech Hub (28.5494, 77.2528)
    create_resp = await client.post(
        "/api/v1/visits/ad-hoc",
        json={"customer_id": data["offbeat_customer_id"], "adhoc_reason": "Cheque Bounce"},
        headers={"Authorization": f"Bearer {data['emp_token']}"},
    )
    assert create_resp.status_code == 201
    visit_id = create_resp.json()["id"]

    # 2. Check-in within geofence (< 20 meters away at 28.54941, 77.25281)
    checkin_resp = await client.post(
        f"/api/v1/visits/{visit_id}/check-in",
        json={
            "latitude": 28.54941,
            "longitude": 77.25281,
            "accuracy_m": 8.0,
            "is_mock_location": False,
            "captured_at": datetime.now(timezone.utc).isoformat(),
        },
        headers={"Authorization": f"Bearer {data['emp_token']}"},
    )
    assert checkin_resp.status_code == 200, checkin_resp.text
    updated = checkin_resp.json()
    assert updated["status"] == "IN_PROGRESS"
    assert updated["visit_type"] == "AD_HOC"
    assert updated["check_in_at"] is not None


@requires_db
@pytest.mark.asyncio
async def test_adhoc_visit_outside_geofence_rejected(client: AsyncClient, adhoc_test_setup):
    data = adhoc_test_setup
    # 1. Create ad-hoc visit to Nehru Tech Hub (28.5494, 77.2528)
    create_resp = await client.post(
        "/api/v1/visits/ad-hoc",
        json={"customer_id": data["offbeat_customer_id"], "adhoc_reason": "New Business Opportunity"},
        headers={"Authorization": f"Bearer {data['emp_token']}"},
    )
    visit_id = create_resp.json()["id"]

    # 2. Attempt check-in from 10+ km away (e.g. Connaught Place 28.6315, 77.2167)
    checkin_resp = await client.post(
        f"/api/v1/visits/{visit_id}/check-in",
        json={
            "latitude": 28.6315,
            "longitude": 77.2167,
            "accuracy_m": 10.0,
            "is_mock_location": False,
            "captured_at": datetime.now(timezone.utc).isoformat(),
        },
        headers={"Authorization": f"Bearer {data['emp_token']}"},
    )
    # Geofence verification MUST reject the check-in!
    assert checkin_resp.status_code == 422
    assert "GEO_VERIFICATION_FAILED" in checkin_resp.text or "distance" in checkin_resp.text.lower()


@requires_db
@pytest.mark.asyncio
async def test_admin_filter_visits_by_visit_type(client: AsyncClient, adhoc_test_setup):
    data = adhoc_test_setup
    # Create an ad-hoc visit
    await client.post(
        "/api/v1/visits/ad-hoc",
        json={"customer_id": data["offbeat_customer_id"], "adhoc_reason": "Other", "adhoc_notes": "Sample note"},
        headers={"Authorization": f"Bearer {data['emp_token']}"},
    )

    # Filter by PLANNED
    resp_planned = await client.get(
        "/api/v1/visits?visit_type=PLANNED",
        headers={"Authorization": f"Bearer {data['admin_token']}"},
    )
    assert resp_planned.status_code == 200
    planned_list = resp_planned.json()
    assert all(v["visit_type"] == "PLANNED" for v in planned_list)

    # Filter by AD_HOC
    resp_adhoc = await client.get(
        "/api/v1/visits?visit_type=AD_HOC",
        headers={"Authorization": f"Bearer {data['admin_token']}"},
    )
    assert resp_adhoc.status_code == 200
    adhoc_list = resp_adhoc.json()
    assert len(adhoc_list) >= 1
    assert all(v["visit_type"] == "AD_HOC" for v in adhoc_list)


@requires_db
@pytest.mark.asyncio
async def test_employee_activity_planned_vs_adhoc_counts(client: AsyncClient, adhoc_test_setup):
    data = adhoc_test_setup
    # Create an ad-hoc visit
    await client.post(
        "/api/v1/visits/ad-hoc",
        json={"customer_id": data["offbeat_customer_id"], "adhoc_reason": "Payment Follow-up"},
        headers={"Authorization": f"Bearer {data['emp_token']}"},
    )

    # Check employee activity summary
    resp = await client.get(
        f"/api/v1/employees/{data['employee_id']}/activity",
        headers={"Authorization": f"Bearer {data['admin_token']}"},
    )
    assert resp.status_code == 200
    act = resp.json()
    assert act["visits_planned"] >= 1
    assert act["visits_adhoc"] >= 1
    assert act["visits_total"] == act["visits_planned"] + act["visits_adhoc"]
