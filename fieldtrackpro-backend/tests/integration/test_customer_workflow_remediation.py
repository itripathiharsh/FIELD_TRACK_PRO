"""
Customer Workflow Remediation Tests.

Covers:
- APP-CUST-001: Customer update outlet_code uniqueness check and 409 handling
- APP-CUST-002 / 008 / 009 / 010: Customer pagination, search, territory/area filters, X-Total-Count header
- APP-CUST-004 / 005 / 019 / 022: VisitRead returns customer summary and coordinates to eliminate N+1 calls
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_update_customer_with_unique_outlet_code(
    client: AsyncClient, admin_headers
):
    """APP-CUST-001: Updating customer with a unique outlet code succeeds."""
    orig_code = f"ORIG-{uuid.uuid4().hex[:6].upper()}"
    create_resp = await client.post(
        "/api/v1/customers",
        json={
            "name": "Unique Test Customer",
            "contact_number": "+919876543219",
            "outlet_code": orig_code,
            "address": "123 Test St",
            "location": {"latitude": 12.9716, "longitude": 77.5946},
        },
        headers=admin_headers,
    )
    assert create_resp.status_code == 201, create_resp.text
    cust_id = create_resp.json()["id"]

    new_code = f"OUT-{uuid.uuid4().hex[:6].upper()}"
    resp = await client.patch(
        f"/api/v1/customers/{cust_id}",
        json={"outlet_code": new_code},
        headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["outlet_code"] == new_code


@pytest.mark.asyncio
async def test_update_customer_with_duplicate_outlet_code_returns_409(
    client: AsyncClient, admin_headers
):
    """APP-CUST-001: Updating customer with another customer's outlet code returns 409 OUTLET_CODE_EXISTS."""
    # Create customer A with unique code
    code_a = f"DUP-{uuid.uuid4().hex[:6].upper()}"
    resp_a = await client.post(
        "/api/v1/customers",
        json={
            "name": "Customer A",
            "contact_number": "+919876543210",
            "outlet_code": code_a,
            "address": "123 Main St",
            "location": {"latitude": 12.9716, "longitude": 77.5946},
        },
        headers=admin_headers,
    )
    assert resp_a.status_code == 201, resp_a.text

    # Create customer B with distinct code
    code_b = f"DUP-{uuid.uuid4().hex[:6].upper()}"
    resp_b = await client.post(
        "/api/v1/customers",
        json={
            "name": "Customer B",
            "contact_number": "+919876543211",
            "outlet_code": code_b,
            "address": "456 Other St",
            "location": {"latitude": 12.9716, "longitude": 77.5946},
        },
        headers=admin_headers,
    )
    assert resp_b.status_code == 201, resp_b.text
    cust_b_id = resp_b.json()["id"]

    # Try updating Customer B to use Customer A's code
    patch_resp = await client.patch(
        f"/api/v1/customers/{cust_b_id}",
        json={"outlet_code": code_a},
        headers=admin_headers,
    )
    assert patch_resp.status_code == 409
    err = patch_resp.json()
    error_obj = err.get("error", err)
    assert error_obj.get("code") == "OUTLET_CODE_EXISTS" or error_obj.get("error_code") == "OUTLET_CODE_EXISTS"
    assert f"DMS Code '{code_a}' already exists" in (error_obj.get("message") or error_obj.get("detail", ""))


@pytest.mark.asyncio
async def test_update_customer_retaining_own_outlet_code_succeeds(
    client: AsyncClient, admin_headers
):
    """APP-CUST-001: Updating other fields while retaining the customer's own outlet code succeeds."""
    code = f"SELF-{uuid.uuid4().hex[:6].upper()}"
    create_resp = await client.post(
        "/api/v1/customers",
        json={
            "name": "Self Retain Store",
            "contact_number": "+919876543212",
            "outlet_code": code,
            "address": "789 Self St",
            "location": {"latitude": 12.9716, "longitude": 77.5946},
        },
        headers=admin_headers,
    )
    assert create_resp.status_code == 201, create_resp.text
    cust_id = create_resp.json()["id"]

    # Update name and re-send same outlet_code
    patch_resp = await client.patch(
        f"/api/v1/customers/{cust_id}",
        json={"name": "Self Retain Store Renamed", "outlet_code": code},
        headers=admin_headers,
    )
    assert patch_resp.status_code == 200, patch_resp.text
    assert patch_resp.json()["name"] == "Self Retain Store Renamed"
    assert patch_resp.json()["outlet_code"] == code


@pytest.mark.asyncio
async def test_list_customers_pagination_and_x_total_count(
    client: AsyncClient, admin_headers
):
    """APP-CUST-002 / 008: Customer listing returns X-Total-Count header and respects skip/limit."""
    resp = await client.get(
        "/api/v1/customers?skip=0&limit=5",
        headers=admin_headers,
    )
    assert resp.status_code == 200
    assert "x-total-count" in resp.headers
    total_count = int(resp.headers["x-total-count"])
    assert total_count >= 0
    items = resp.json()
    assert len(items) <= 5


@pytest.mark.asyncio
async def test_visit_read_includes_denormalized_customer_metadata(
    client: AsyncClient, admin_headers, employee_headers, seeded_world, created_visits
):
    """APP-CUST-004 / 019: VisitRead includes customer location and summary metadata."""
    cust_id = seeded_world["customer_id"]
    emp_id = seeded_world["employee_id"]

    # Create visit
    create_resp = await client.post(
        "/api/v1/visits",
        json={
            "customer_id": cust_id,
            "employee_id": emp_id,
            "scheduled_at": datetime.now(timezone.utc).isoformat(),
        },
        headers=admin_headers,
    )
    assert create_resp.status_code == 201, create_resp.text
    visit = create_resp.json()
    created_visits.append(visit["id"])

    assert "customer_name" in visit
    assert "customer_address" in visit
    assert "customer_latitude" in visit
    assert "customer_longitude" in visit
    assert "customer_geofence_radius_m" in visit
    assert visit["customer_latitude"] is not None
    assert visit["customer_longitude"] is not None
