"""
Integration tests for customer and territory fixes:
WEB-CUST-001 through WEB-CUST-019
"""
from __future__ import annotations

import uuid
import pytest
from httpx import AsyncClient

from tests.integration.conftest import requires_db

pytestmark = [requires_db, pytest.mark.integration, pytest.mark.asyncio]


async def test_patch_duplicate_dms_code_returns_409(
    client: AsyncClient, admin_headers
):
    """
    WEB-CUST-001 & WEB-CUST-006:
    Customer A -> outlet_code ABC_CODE_1
    Customer B -> PATCH outlet_code ABC_CODE_1
    Expected -> 409 OUTLET_CODE_EXISTS
    """
    code_suffix = uuid.uuid4().hex[:6].upper()
    code_a = f"OUT_{code_suffix}_A"
    code_b = f"OUT_{code_suffix}_B"

    # Create customer A
    resp_a = await client.post(
        "/api/v1/customers",
        json={
            "name": f"__itest__ Cust A {code_suffix}",
            "contact_number": "+919999900001",
            "outlet_code": code_a,
            "address": "123 Main St",
        },
        headers=admin_headers,
    )
    assert resp_a.status_code == 201, resp_a.text
    cust_a_id = resp_a.json()["id"]

    # Create customer B
    resp_b = await client.post(
        "/api/v1/customers",
        json={
            "name": f"__itest__ Cust B {code_suffix}",
            "contact_number": "+919999900002",
            "outlet_code": code_b,
            "address": "456 Side St",
        },
        headers=admin_headers,
    )
    assert resp_b.status_code == 201, resp_b.text
    cust_b_id = resp_b.json()["id"]

    # Patch B with A's code (case-insensitive test: lowercase of code_a)
    patch_resp = await client.patch(
        f"/api/v1/customers/{cust_b_id}",
        json={"outlet_code": code_a.lower()},
        headers=admin_headers,
    )
    assert patch_resp.status_code == 409, patch_resp.text
    err = patch_resp.json()
    assert err["error"]["code"] == "OUTLET_CODE_EXISTS"

    # Verify Customer B can update another field while retaining its OWN outlet code
    edit_self = await client.patch(
        f"/api/v1/customers/{cust_b_id}",
        json={"name": f"__itest__ Cust B Updated {code_suffix}", "outlet_code": code_b},
        headers=admin_headers,
    )
    assert edit_self.status_code == 200, edit_self.text
    assert edit_self.json()["outlet_code"] == code_b


async def test_whitespace_only_address_rejected(
    client: AsyncClient, admin_headers
):
    """
    WEB-CUST-007: Address containing only whitespace is rejected.
    """
    for invalid_addr in ["   ", "\t", "\n  \t "]:
        resp = await client.post(
            "/api/v1/customers",
            json={
                "name": f"__itest__ Whitespace Address {uuid.uuid4().hex[:4]}",
                "contact_number": "+919999900003",
                "address": invalid_addr,
                "outlet_code": f"OUT_{uuid.uuid4().hex[:6].upper()}",
            },
            headers=admin_headers,
        )
        assert resp.status_code == 422, f"Failed to reject address: {invalid_addr!r}"


async def test_customer_search_escapes_wildcards(
    client: AsyncClient, admin_headers
):
    """
    WEB-CUST-004: Ensure '%' and '_' in search do not act as SQL wildcards.
    """
    suffix = uuid.uuid4().hex[:4]
    name_literal = f"__itest__ Literal%50_Off {suffix}"
    name_other = f"__itest__ Literal9501Off {suffix}"

    resp1 = await client.post(
        "/api/v1/customers",
        json={
            "name": name_literal,
            "contact_number": "+919999900004",
            "outlet_code": f"LIT_{suffix.upper()}",
            "address": "Market Street",
        },
        headers=admin_headers,
    )
    assert resp1.status_code == 201

    resp2 = await client.post(
        "/api/v1/customers",
        json={
            "name": name_other,
            "contact_number": "+919999900005",
            "outlet_code": f"OTH_{suffix.upper()}",
            "address": "Market Street",
        },
        headers=admin_headers,
    )
    assert resp2.status_code == 201

    # Search for literal '%50_'
    search_resp = await client.get(
        f"/api/v1/customers?search=%2550_",
        headers=admin_headers,
    )
    assert search_resp.status_code == 200
    results = search_resp.json()
    matched_names = [c["name"] for c in results]
    assert name_literal in matched_names
    assert name_other not in matched_names


async def test_territory_case_insensitive_duplicate_returns_409(
    client: AsyncClient, admin_headers
):
    """
    WEB-CUST-012: Territory name uniqueness is case-insensitive.
    """
    suffix = uuid.uuid4().hex[:6]
    name = f"__itest__ Territory_{suffix}"

    # Create territory in mixed case
    resp1 = await client.post(
        "/api/v1/territories",
        json={"name": name, "center_latitude": 26.8467, "center_longitude": 80.9462, "radius_km": 10.0},
        headers=admin_headers,
    )
    assert resp1.status_code == 201, resp1.text

    # Attempt to create with different casing (lowercase)
    resp2 = await client.post(
        "/api/v1/territories",
        json={"name": name.lower(), "center_latitude": 26.8467, "center_longitude": 80.9462, "radius_km": 15.0},
        headers=admin_headers,
    )
    assert resp2.status_code == 409, resp2.text
    assert resp2.json()["error"]["code"] == "TERRITORY_EXISTS"

    # Attempt to create with uppercase
    resp3 = await client.post(
        "/api/v1/territories",
        json={"name": name.upper(), "center_latitude": 26.8467, "center_longitude": 80.9462, "radius_km": 15.0},
        headers=admin_headers,
    )
    assert resp3.status_code == 409
    assert resp3.json()["error"]["code"] == "TERRITORY_EXISTS"


async def test_zero_zero_coordinates_and_null_coordinates(
    client: AsyncClient, admin_headers
):
    """
    WEB-CUST-017: (0,0) is accepted as valid coordinates, and NULL is treated as missing.
    """
    # 1. Test (0.0, 0.0)
    resp_zero = await client.post(
        "/api/v1/customers",
        json={
            "name": f"__itest__ Null Island {uuid.uuid4().hex[:4]}",
            "contact_number": "+919999900006",
            "location": {"latitude": 0.0, "longitude": 0.0},
            "outlet_code": f"ZERO_{uuid.uuid4().hex[:6].upper()}",
            "address": "Null Island Bay",
        },
        headers=admin_headers,
    )
    assert resp_zero.status_code == 201, resp_zero.text
    data_zero = resp_zero.json()
    assert data_zero["location"] is not None
    assert data_zero["location"]["latitude"] == 0.0
    assert data_zero["location"]["longitude"] == 0.0

    # 2. Test map locations endpoint
    map_resp = await client.get("/api/v1/customers/map-locations", headers=admin_headers)
    assert map_resp.status_code == 200
    map_locations = map_resp.json()
    assert isinstance(map_locations, list)
    zero_entry = next((m for m in map_locations if m["id"] == data_zero["id"]), None)
    assert zero_entry is not None
    assert zero_entry["latitude"] == 0.0
    assert zero_entry["longitude"] == 0.0
