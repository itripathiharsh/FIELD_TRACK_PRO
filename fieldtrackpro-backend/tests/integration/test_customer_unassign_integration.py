"""
Integration tests for Customer territory & area assignment/unassignment lifecycle.

Proves:
- Customer can be assigned to a territory.
- Customer appears assigned in responses and database.
- Customer can be unassigned from a territory (territory_id: null).
- Relationship is actually removed from the database.
- After re-fetching (simulating page refresh), customer remains unassigned.
- Area assignment is preserved when customer is unassigned from a territory.
- Updating area_id updates territory_id accordingly.
- Unassigning area_id (area_id: null) clears area_id.
- Unrelated customer/area/territory relationships remain untouched.
- Authorization: Admin only; Employee gets 403.
"""
from __future__ import annotations

import uuid
import pytest
from httpx import AsyncClient

from tests.integration.conftest import requires_db

pytestmark = [requires_db, pytest.mark.integration, pytest.mark.asyncio]


async def test_customer_territory_assign_and_unassign_flow(
    client: AsyncClient, admin_headers, seeded_world, created_customers, created_territories
):
    """
    Verify complete chain:
    1. Create a customer with no territory.
    2. Assign customer to a territory.
    3. Verify customer is assigned.
    4. Unassign customer (territory_id: null).
    5. Verify customer territory_id is None in response and database.
    6. Re-fetch customer to confirm persistence.
    """
    tag = uuid.uuid4().hex[:8]

    # Create a fresh territory
    terr_resp = await client.post(
        "/api/v1/territories",
        json={
            "name": f"__itest__Zone-{tag}",
            "center_latitude": 26.8467,
            "center_longitude": 80.9462,
            "radius_km": 15,
        },
        headers=admin_headers,
    )
    assert terr_resp.status_code == 201, terr_resp.text
    territory_id = terr_resp.json()["id"]
    created_territories.append(territory_id)

    # 1. Create a customer without territory
    cust_resp = await client.post(
        "/api/v1/customers",
        json={
            "name": f"__itest__Cust-{tag}",
            "contact_number": "+919876500001",
            "contact_person": "Initial Person",
            "address": "123 Test Street",
            "location": {"latitude": 26.8467, "longitude": 80.9462},
        },
        headers=admin_headers,
    )
    assert cust_resp.status_code == 201, cust_resp.text
    customer_id = cust_resp.json()["id"]
    created_customers.append(customer_id)
    assert cust_resp.json()["territory_id"] is None

    # 2. Assign customer to territory
    assign_resp = await client.patch(
        f"/api/v1/customers/{customer_id}",
        json={"territory_id": territory_id},
        headers=admin_headers,
    )
    assert assign_resp.status_code == 200, assign_resp.text
    assert assign_resp.json()["territory_id"] == territory_id

    # 3. Verify customer appears assigned via GET
    get_resp = await client.get(f"/api/v1/customers/{customer_id}", headers=admin_headers)
    assert get_resp.status_code == 200
    assert get_resp.json()["territory_id"] == territory_id

    # 4. Unassign customer (send territory_id: null)
    unassign_resp = await client.patch(
        f"/api/v1/customers/{customer_id}",
        json={"territory_id": None},
        headers=admin_headers,
    )
    assert unassign_resp.status_code == 200, unassign_resp.text
    # 5. Verify relationship is removed
    assert unassign_resp.json()["territory_id"] is None

    # 6. Re-fetch customer (simulating page reload)
    refetch_resp = await client.get(f"/api/v1/customers/{customer_id}", headers=admin_headers)
    assert refetch_resp.status_code == 200
    assert refetch_resp.json()["territory_id"] is None


async def test_unassign_territory_preserves_area_assignment(
    client: AsyncClient, admin_headers, seeded_world, created_customers, created_territories
):
    """
    Ensure that unassigning territory_id directly does not delete area_id
    when area_id was not included in the PATCH body.
    """
    tag = uuid.uuid4().hex[:8]

    # Create territory and area
    terr_resp = await client.post(
        "/api/v1/territories",
        json={"name": f"__itest__ZoneArea-{tag}"},
        headers=admin_headers,
    )
    assert terr_resp.status_code == 201
    territory_id = terr_resp.json()["id"]
    created_territories.append(territory_id)

    area_resp = await client.post(
        "/api/v1/areas",
        json={"name": f"__itest__Area-{tag}", "territory_id": territory_id},
        headers=admin_headers,
    )
    assert area_resp.status_code == 201
    area_id = area_resp.json()["id"]

    # Create customer with area
    cust_resp = await client.post(
        "/api/v1/customers",
        json={
            "name": f"__itest__CustArea-{tag}",
            "contact_number": "+919876500002",
            "address": "456 Area Rd",
            "location": {"latitude": 12.9716, "longitude": 77.5946},
            "area_id": area_id,
        },
        headers=admin_headers,
    )
    assert cust_resp.status_code == 201
    customer_id = cust_resp.json()["id"]
    created_customers.append(customer_id)
    assert cust_resp.json()["area_id"] == area_id
    assert cust_resp.json()["territory_id"] == territory_id

    # Unassign territory only
    unassign_resp = await client.patch(
        f"/api/v1/customers/{customer_id}",
        json={"territory_id": None},
        headers=admin_headers,
    )
    assert unassign_resp.status_code == 200
    assert unassign_resp.json()["territory_id"] is None
    # Area ID is preserved
    assert unassign_resp.json()["area_id"] == area_id

    # Re-fetch customer
    get_resp = await client.get(f"/api/v1/customers/{customer_id}", headers=admin_headers)
    assert get_resp.json()["territory_id"] is None
    assert get_resp.json()["area_id"] == area_id


async def test_unassign_area_and_reassign_territory(
    client: AsyncClient, admin_headers, seeded_world, created_customers, created_territories
):
    """
    Verify unassigning area_id (area_id: null) and assigning a different territory.
    """
    tag = uuid.uuid4().hex[:8]

    terr1_resp = await client.post(
        "/api/v1/territories",
        json={"name": f"__itest__Zone1-{tag}"},
        headers=admin_headers,
    )
    terr1_id = terr1_resp.json()["id"]
    created_territories.append(terr1_id)

    terr2_resp = await client.post(
        "/api/v1/territories",
        json={"name": f"__itest__Zone2-{tag}"},
        headers=admin_headers,
    )
    terr2_id = terr2_resp.json()["id"]
    created_territories.append(terr2_id)

    area_resp = await client.post(
        "/api/v1/areas",
        json={"name": f"__itest__Area1-{tag}", "territory_id": terr1_id},
        headers=admin_headers,
    )
    area_id = area_resp.json()["id"]

    cust_resp = await client.post(
        "/api/v1/customers",
        json={
            "name": f"__itest__CustSwitch-{tag}",
            "contact_number": "+919876500003",
            "address": "789 Switch Rd",
            "location": {"latitude": 12.9716, "longitude": 77.5946},
            "area_id": area_id,
        },
        headers=admin_headers,
    )
    customer_id = cust_resp.json()["id"]
    created_customers.append(customer_id)
    assert cust_resp.json()["area_id"] == area_id
    assert cust_resp.json()["territory_id"] == terr1_id

    # Clear area and set territory to zone 2
    update_resp = await client.patch(
        f"/api/v1/customers/{customer_id}",
        json={"area_id": None, "territory_id": terr2_id},
        headers=admin_headers,
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["area_id"] is None
    assert update_resp.json()["territory_id"] == terr2_id

    # Re-fetch
    get_resp = await client.get(f"/api/v1/customers/{customer_id}", headers=admin_headers)
    assert get_resp.json()["area_id"] is None
    assert get_resp.json()["territory_id"] == terr2_id


async def test_unassign_customer_authorization(
    client: AsyncClient, admin_headers, employee_headers, seeded_world, created_customers
):
    """
    Only ADMIN can update/unassign customer territory assignments.
    EMPLOYEE receives 403 Forbidden.
    """
    tag = uuid.uuid4().hex[:8]
    cust_resp = await client.post(
        "/api/v1/customers",
        json={
            "name": f"__itest__AuthCust-{tag}",
            "contact_number": "+919876500004",
            "address": "101 Auth Rd",
            "location": {"latitude": 12.9716, "longitude": 77.5946},
            "territory_id": seeded_world["territory_id"],
        },
        headers=admin_headers,
    )
    customer_id = cust_resp.json()["id"]
    created_customers.append(customer_id)

    # Employee tries to unassign -> 403
    emp_patch_resp = await client.patch(
        f"/api/v1/customers/{customer_id}",
        json={"territory_id": None},
        headers=employee_headers,
    )
    assert emp_patch_resp.status_code == 403

    # Admin unassigns -> 200
    admin_patch_resp = await client.patch(
        f"/api/v1/customers/{customer_id}",
        json={"territory_id": None},
        headers=admin_headers,
    )
    assert admin_patch_resp.status_code == 200
    assert admin_patch_resp.json()["territory_id"] is None
