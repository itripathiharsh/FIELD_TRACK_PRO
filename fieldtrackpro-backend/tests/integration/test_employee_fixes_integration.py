"""
Integration tests for consolidated employee fixes:
WEB-EMP-001 through WEB-EMP-035
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone, timedelta
import pytest
from httpx import AsyncClient

from tests.integration.conftest import requires_db

pytestmark = [requires_db, pytest.mark.integration, pytest.mark.asyncio]


async def test_employee_server_side_pagination_and_search(
    client: AsyncClient, admin_headers
):
    """
    WEB-EMP-001, 002, 003:
    Pagination with X-Total-Count and server-side search across all records.
    """
    # 1. Fetch paginated employees
    resp = await client.get("/api/v1/employees?skip=0&limit=5", headers=admin_headers)
    assert resp.status_code == 200, resp.text
    assert "X-Total-Count" in resp.headers
    total_count = int(resp.headers["X-Total-Count"])
    assert total_count >= 1
    employees = resp.json()
    assert len(employees) <= 5

    # 2. Create a uniquely identifiable employee
    suffix = uuid.uuid4().hex[:6].upper()
    name = f"__itest__ Searchable Emp {suffix}"
    code = f"EMP_{suffix}"
    email = f"emp_{suffix.lower()}@fieldtrack.test"

    reg_resp = await client.post(
        "/api/v1/employees/register",
        json={
            "user": {
                "email": email,
                "password": "Password123!",
                "role": "EMPLOYEE",
            },
            "full_name": name,
            "employee_code": code,
        },
        headers=admin_headers,
    )
    assert reg_resp.status_code == 201, reg_resp.text

    # 3. Search for this specific employee across the entire database
    search_resp = await client.get(f"/api/v1/employees?search={suffix}", headers=admin_headers)
    assert search_resp.status_code == 200
    search_results = search_resp.json()
    matched_names = [e["full_name"] for e in search_results]
    assert name in matched_names


async def test_employee_code_case_insensitive_and_patch_duplicate_returns_409(
    client: AsyncClient, admin_headers
):
    """
    WEB-EMP-009, 010, 030:
    Employee code normalized uppercase and patch duplicate code returns 409.
    """
    suffix = uuid.uuid4().hex[:6].upper()
    code_a = f"CODE_{suffix}_A"
    code_b = f"CODE_{suffix}_B"

    # Create Emp A
    resp_a = await client.post(
        "/api/v1/employees/register",
        json={
            "user": {"email": f"a_{suffix.lower()}@fieldtrack.test", "password": "Password123!", "role": "EMPLOYEE"},
            "full_name": f"Emp A {suffix}",
            "employee_code": code_a.lower(),  # will normalize to uppercase
        },
        headers=admin_headers,
    )
    assert resp_a.status_code == 201, resp_a.text
    emp_a_data = resp_a.json()
    assert emp_a_data["employee_code"] == code_a

    # Create Emp B
    resp_b = await client.post(
        "/api/v1/employees/register",
        json={
            "user": {"email": f"b_{suffix.lower()}@fieldtrack.test", "password": "Password123!", "role": "EMPLOYEE"},
            "full_name": f"Emp B {suffix}",
            "employee_code": code_b,
        },
        headers=admin_headers,
    )
    assert resp_b.status_code == 201, resp_b.text
    emp_b_id = resp_b.json()["id"]

    # Patch B with A's code -> 409
    patch_resp = await client.patch(
        f"/api/v1/employees/{emp_b_id}",
        json={"employee_code": code_a.lower()},
        headers=admin_headers,
    )
    assert patch_resp.status_code == 409, patch_resp.text
    assert patch_resp.json()["error"]["code"] == "EMPLOYEE_CODE_EXISTS"

    # Emp B keeps its own code -> 200
    own_resp = await client.patch(
        f"/api/v1/employees/{emp_b_id}",
        json={"full_name": f"Emp B Renamed {suffix}", "employee_code": code_b},
        headers=admin_headers,
    )
    assert own_resp.status_code == 200


async def test_blank_and_whitespace_employee_name_rejected(
    client: AsyncClient, admin_headers
):
    """
    WEB-EMP-007: Reject whitespace and blank names with min length 2.
    """
    for invalid_name in ["", " ", "   ", "\t", "a"]:
        resp = await client.post(
            "/api/v1/employees/register",
            json={
                "user": {"email": f"invalid_{uuid.uuid4().hex[:6]}@test.com", "password": "Password123!", "role": "EMPLOYEE"},
                "full_name": invalid_name,
            },
            headers=admin_headers,
        )
        assert resp.status_code == 422, f"Failed to reject name: {invalid_name!r}"


async def test_nullable_employee_fields_cleared_with_explicit_null(
    client: AsyncClient, admin_headers
):
    """
    WEB-EMP-011: Nullable employee fields (cug, working_profile, address) can be cleared with explicit null.
    """
    suffix = uuid.uuid4().hex[:6].upper()
    reg_resp = await client.post(
        "/api/v1/employees/register",
        json={
            "user": {"email": f"nulltest_{suffix.lower()}@fieldtrack.test", "password": "Password123!", "role": "EMPLOYEE"},
            "full_name": f"Emp NullTest {suffix}",
            "cug": "+919876543210",
            "working_profile": "SENIOR_SALES",
            "address": "123 Test Lane",
        },
        headers=admin_headers,
    )
    assert reg_resp.status_code == 201, reg_resp.text
    emp_id = reg_resp.json()["id"]

    # Patch with explicit nulls
    patch_resp = await client.patch(
        f"/api/v1/employees/{emp_id}",
        json={
            "cug": None,
            "working_profile": None,
            "address": None,
        },
        headers=admin_headers,
    )
    assert patch_resp.status_code == 200, patch_resp.text
    updated = patch_resp.json()
    assert updated["cug"] is None
    assert updated["working_profile"] is None
    assert updated["address"] is None


async def test_duplicate_permanent_assignment_same_date_returns_409(
    client: AsyncClient, admin_headers, seeded_world
):
    """
    WEB-EMP-017: Prevent two PERMANENT assignments for the same employee on the same start date.
    """
    emp_id = seeded_world["employee_id"]
    terr_id = seeded_world["territory_id"]
    today_str = date.today().isoformat()

    # Create first assignment
    resp1 = await client.post(
        f"/api/v1/employees/{emp_id}/territory-assignments",
        json={
            "territory_id": terr_id,
            "assignment_type": "PERMANENT",
            "start_date": today_str,
        },
        headers=admin_headers,
    )
    if resp1.status_code == 201:
        resp2 = await client.post(
            f"/api/v1/employees/{emp_id}/territory-assignments",
            json={
                "territory_id": terr_id,
                "assignment_type": "PERMANENT",
                "start_date": today_str,
            },
            headers=admin_headers,
        )
        assert resp2.status_code == 409, resp2.text
        assert resp2.json()["error"]["code"] == "ASSIGNMENT_DUPLICATE_PERMANENT"


async def test_outlet_with_null_gps_and_checkout_before_checkin(
    client: AsyncClient, admin_headers, seeded_world
):
    """
    WEB-EMP-024 & WEB-EMP-023:
    - Outlet with NULL GPS cannot check in (returns OUTLET_LOCATION_NOT_CONFIGURED).
    - Checkout before check-in returns CHECKIN_REQUIRED.
    """
    emp_id = seeded_world["employee_id"]
    suffix = uuid.uuid4().hex[:6].upper()

    # 1. Create a customer without GPS location (NULL location)
    cust_resp = await client.post(
        "/api/v1/customers",
        json={
            "name": f"__itest__ No GPS Cust {suffix}",
            "contact_number": "+919999911111",
            "outlet_code": f"NOGPS_{suffix}",
            "address": "Remote Outpost",
        },
        headers=admin_headers,
    )
    assert cust_resp.status_code == 201
    cust_id = cust_resp.json()["id"]

    # 2. Schedule a visit to this customer
    visit_resp = await client.post(
        "/api/v1/visits",
        json={
            "customer_id": cust_id,
            "employee_id": emp_id,
            "scheduled_at": datetime.now(tz=timezone.utc).isoformat(),
        },
        headers=admin_headers,
    )
    assert visit_resp.status_code == 201, visit_resp.text
    visit_id = visit_resp.json()["id"]

    # 3. Attempt check-in on customer with NULL GPS -> 422 OUTLET_LOCATION_NOT_CONFIGURED
    checkin_resp = await client.post(
        f"/api/v1/visits/{visit_id}/check-in",
        json={
            "latitude": 12.9716,
            "longitude": 77.5946,
            "accuracy_m": 10.0,
            "captured_at": datetime.now(tz=timezone.utc).isoformat(),
        },
        headers=admin_headers,
    )
    assert checkin_resp.status_code == 422, checkin_resp.text
    assert checkin_resp.json()["error"]["code"] == "OUTLET_LOCATION_NOT_CONFIGURED"

    # 4. Attempt checkout before check-in -> 400 CHECKIN_REQUIRED
    checkout_resp = await client.post(
        f"/api/v1/visits/{visit_id}/check-out",
        json={
            "latitude": 12.9716,
            "longitude": 77.5946,
            "accuracy_m": 10.0,
            "captured_at": datetime.now(tz=timezone.utc).isoformat(),
        },
        headers=admin_headers,
    )
    assert checkout_resp.status_code == 400, checkout_resp.text
    assert checkout_resp.json()["error"]["code"] == "CHECKIN_REQUIRED"
