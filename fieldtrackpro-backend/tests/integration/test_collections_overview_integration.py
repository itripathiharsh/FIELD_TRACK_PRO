"""
Integration tests for the Collections Overview aggregate endpoint
(Meeting 2's "Excel screenshot" replacement) - GET /api/v1/collections/overview.

Every ageing assertion here checks the endpoint agrees with the same
aging_service thresholds already covered by test_collections_integration.py's
per-invoice tests - this suite is about the BULK aggregation (totals,
pagination, filters, per-outlet rollups) being correct, not re-proving the
aging math itself.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
import pytest_asyncio
from httpx import AsyncClient

from tests.integration.conftest import (
    TEST_MARKER,
    TEST_PASSWORD,
    create_visit,
    db_cursor,
    hash_password,
    requires_db,
)

pytestmark = [requires_db, pytest.mark.integration, pytest.mark.asyncio]


def _iso_days_ago(days: int) -> str:
    return (date.today() - timedelta(days=days)).isoformat()


async def _create_customer(client, admin_headers, created_customers, *, name=None, outlet_code=None, territory_id=None):
    tag = uuid.uuid4().hex[:8]
    payload = {
        "name": name or f"{TEST_MARKER}Outlet-{tag}",
        "contact_number": "+919999900002",
        "address": f"{TEST_MARKER} Overview Test Road",
        "location": {"latitude": 12.9716, "longitude": 77.5946},
        "geofence_radius_m": 75,
        "outlet_code": outlet_code or f"{TEST_MARKER}OC-{tag}",
    }
    if territory_id:
        payload["territory_id"] = territory_id
    resp = await client.post("/api/v1/customers", json=payload, headers=admin_headers)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    created_customers.append(body["id"])
    return body


async def _create_invoice(client, admin_headers, customer_id, days_ago, amount, created_invoices):
    resp = await client.post(
        "/api/v1/invoices",
        json={
            "customer_id": customer_id,
            "invoice_number": f"__itest__OV-{uuid.uuid4().hex[:8]}",
            "invoice_date": _iso_days_ago(days_ago),
            "amount": amount,
        },
        headers=admin_headers,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    created_invoices.append(body["id"])
    return body


@pytest_asyncio.fixture
async def dedicated_employee(created_territories):
    """
    A territory with EXACTLY one employee assigned - unlike seeded_world's
    own territory, which deliberately has TWO employees sharing it (a real
    product ambiguity this suite documents rather than papers over). Gives
    the employee-filter and assigned-employee-name tests a deterministic
    outlet to check against.
    """
    tag = uuid.uuid4().hex[:8]
    territory_id = str(uuid.uuid4())
    user_id = str(uuid.uuid4())
    employee_id = str(uuid.uuid4())
    code = f"{TEST_MARKER}SOLO-{tag}"
    with db_cursor(privileged=True) as cur:
        cur.execute(
            "INSERT INTO territories (id, name, created_at) VALUES (%s, %s, now())",
            (territory_id, f"{TEST_MARKER}Solo Zone {tag}"),
        )
        cur.execute(
            "INSERT INTO users (id, email, password_hash, role, is_active, created_at, updated_at) "
            "VALUES (%s, %s, %s, 'EMPLOYEE', true, now(), now())",
            (user_id, f"{TEST_MARKER}solo-{tag}@fieldtrack.test", hash_password(TEST_PASSWORD)),
        )
        cur.execute(
            "INSERT INTO employees (id, user_id, full_name, territory_id, employee_code, created_at) "
            "VALUES (%s, %s, %s, %s, %s, now())",
            (employee_id, user_id, f"{TEST_MARKER} Solo Rep {tag}", territory_id, code),
        )
    created_territories.append(territory_id)
    return {"territory_id": territory_id, "employee_id": employee_id}


# -- Permissions ----------------------------------------------------------------

async def test_employee_cannot_view_collections_overview(client: AsyncClient, employee_headers):
    resp = await client.get("/api/v1/collections/overview", headers=employee_headers)
    assert resp.status_code == 403


async def test_unauthenticated_cannot_view_collections_overview(client: AsyncClient):
    resp = await client.get("/api/v1/collections/overview")
    assert resp.status_code == 401


async def test_admin_can_view_collections_overview(client: AsyncClient, admin_headers):
    resp = await client.get("/api/v1/collections/overview", headers=admin_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert "totals" in body and "outlets" in body


# -- Ageing correctness (bulk aggregation reuses aging_service exactly) --------

async def test_bucket_amounts_and_status_match_aging_service(
    client: AsyncClient, admin_headers, created_customers, created_invoices
):
    outlet = await _create_customer(client, admin_headers, created_customers)
    await _create_invoice(client, admin_headers, outlet["id"], days_ago=5, amount="1000.00", created_invoices=created_invoices)
    await _create_invoice(client, admin_headers, outlet["id"], days_ago=26, amount="2000.00", created_invoices=created_invoices)

    resp = await client.get(
        "/api/v1/collections/overview", params={"search": outlet["outlet_code"]}, headers=admin_headers
    )
    assert resp.status_code == 200
    rows = resp.json()["outlets"]
    row = next(r for r in rows if r["customer_id"] == outlet["id"])

    assert row["total_invoiced"] == "3000.00"
    assert row["total_outstanding"] == "3000.00"
    assert row["overdue_amount"] == "2000.00"
    assert row["collection_status"] == "OVERDUE"  # worst status across its invoices
    assert row["max_days_outstanding"] == 26
    assert row["relevant_mis_bucket"] == "16-30"
    assert row["relevant_bucket_amount"] == "2000.00"


async def test_fully_paid_outlet_has_paid_status_and_zero_outstanding(
    client: AsyncClient, admin_headers, employee_headers, created_customers, created_invoices,
    created_visits, created_payments, seeded_world,
):
    outlet = await _create_customer(client, admin_headers, created_customers)
    inv = await _create_invoice(client, admin_headers, outlet["id"], days_ago=10, amount="500.00", created_invoices=created_invoices)

    visit_id = await create_visit(client, admin_headers, outlet["id"], seeded_world["employee_id"], created_visits)
    pay_resp = await client.post(
        "/api/v1/payments",
        json={
            "visit_id": visit_id, "invoice_id": inv["id"], "amount": "500.00",
            "payment_method": "CASH", "payment_date": date.today().isoformat(),
        },
        headers=employee_headers,
    )
    payment_id = pay_resp.json()["id"]
    created_payments.append(payment_id)
    verify = await client.post(f"/api/v1/payments/{payment_id}/verify", headers=admin_headers)
    assert verify.status_code == 200

    resp = await client.get(
        "/api/v1/collections/overview", params={"search": outlet["outlet_code"]}, headers=admin_headers
    )
    row = next(r for r in resp.json()["outlets"] if r["customer_id"] == outlet["id"])
    assert row["total_outstanding"] == "0.00"
    assert row["collection_status"] == "PAID"
    assert row["most_recent_payment_amount"] == "500.00"


async def test_outlet_with_no_invoices_is_paid_and_does_not_crash(
    client: AsyncClient, admin_headers, created_customers
):
    outlet = await _create_customer(client, admin_headers, created_customers)
    resp = await client.get(
        "/api/v1/collections/overview", params={"search": outlet["outlet_code"]}, headers=admin_headers
    )
    assert resp.status_code == 200
    row = next(r for r in resp.json()["outlets"] if r["customer_id"] == outlet["id"])
    # An outlet with zero invoices sums to a plain Decimal("0"), which
    # serializes as "0" rather than "0.00" - mathematically identical to the
    # padded form other tests see once a real invoice is involved.
    assert float(row["total_invoiced"]) == 0
    assert float(row["total_outstanding"]) == 0
    assert row["collection_status"] == "PAID"
    assert row["relevant_mis_bucket"] is None
    assert row["most_recent_payment_date"] is None
    assert row["most_recent_visit_date"] is None


# -- Outlet identity --------------------------------------------------------------

async def test_outlet_code_and_territory_visible_in_overview_row(
    client: AsyncClient, admin_headers, created_customers, seeded_world
):
    outlet = await _create_customer(
        client, admin_headers, created_customers, territory_id=seeded_world["territory_id"]
    )
    resp = await client.get(
        "/api/v1/collections/overview", params={"search": outlet["outlet_code"]}, headers=admin_headers
    )
    row = next(r for r in resp.json()["outlets"] if r["customer_id"] == outlet["id"])
    assert row["outlet_code"] == outlet["outlet_code"]
    assert row["territory_id"] == seeded_world["territory_id"]
    assert row["territory_name"]


# -- Filters ------------------------------------------------------------------

async def test_search_filters_by_outlet_code(client: AsyncClient, admin_headers, created_customers):
    outlet_a = await _create_customer(client, admin_headers, created_customers)
    outlet_b = await _create_customer(client, admin_headers, created_customers)

    resp = await client.get(
        "/api/v1/collections/overview", params={"search": outlet_a["outlet_code"]}, headers=admin_headers
    )
    ids = {r["customer_id"] for r in resp.json()["outlets"]}
    assert outlet_a["id"] in ids
    assert outlet_b["id"] not in ids


async def test_territory_filter_scopes_to_that_territory_only(
    client: AsyncClient, admin_headers, created_customers, dedicated_employee
):
    in_zone = await _create_customer(
        client, admin_headers, created_customers, territory_id=dedicated_employee["territory_id"]
    )
    outside_zone = await _create_customer(client, admin_headers, created_customers)

    resp = await client.get(
        "/api/v1/collections/overview",
        params={"territory_id": dedicated_employee["territory_id"]},
        headers=admin_headers,
    )
    ids = {r["customer_id"] for r in resp.json()["outlets"]}
    assert in_zone["id"] in ids
    assert outside_zone["id"] not in ids


async def test_employee_filter_resolves_via_legacy_territory_for_outlets_with_no_area(
    client: AsyncClient, admin_headers, created_customers, dedicated_employee
):
    """An outlet with no Area assigned yet falls back to the pre-migration
    single-Zone Employee.territory_id derivation, so it doesn't regress to
    "unassigned" just because Area hasn't been set up for it yet."""
    outlet = await _create_customer(
        client, admin_headers, created_customers, territory_id=dedicated_employee["territory_id"]
    )
    resp = await client.get(
        "/api/v1/collections/overview",
        params={"employee_id": dedicated_employee["employee_id"]},
        headers=admin_headers,
    )
    rows = resp.json()["outlets"]
    matched = next((r for r in rows if r["customer_id"] == outlet["id"]), None)
    assert matched is not None, "outlet in the dedicated employee's territory must appear"
    assert matched["area_id"] is None
    assigned_ids = {e["id"] for e in matched["assigned_employees"]}
    assert dedicated_employee["employee_id"] in assigned_ids


async def test_employee_covering_an_area_is_assigned_employee_for_its_outlets(
    client: AsyncClient, admin_headers, created_customers, dedicated_employee
):
    """Once an outlet has a real Area, coverage comes from
    EmployeeAreaAssignment, not the legacy territory shortcut."""
    area_resp = await client.post(
        "/api/v1/areas",
        json={"name": f"{TEST_MARKER}Area-{uuid.uuid4().hex[:6]}", "territory_id": dedicated_employee["territory_id"]},
        headers=admin_headers,
    )
    assert area_resp.status_code == 201, area_resp.text
    area_id = area_resp.json()["id"]

    assign_resp = await client.post(
        f"/api/v1/employees/{dedicated_employee['employee_id']}/areas",
        json={"area_id": area_id},
        headers=admin_headers,
    )
    assert assign_resp.status_code == 201, assign_resp.text

    outlet = await _create_customer(client, admin_headers, created_customers)
    patch_resp = await client.patch(
        f"/api/v1/customers/{outlet['id']}", json={"area_id": area_id}, headers=admin_headers
    )
    assert patch_resp.status_code == 200, patch_resp.text
    # Area is the source of truth: patching area_id must also update
    # territory_id to match, never leaving them disagreeing.
    assert patch_resp.json()["territory_id"] == dedicated_employee["territory_id"]

    resp = await client.get(
        "/api/v1/collections/overview",
        params={"employee_id": dedicated_employee["employee_id"]},
        headers=admin_headers,
    )
    rows = resp.json()["outlets"]
    matched = next((r for r in rows if r["customer_id"] == outlet["id"]), None)
    assert matched is not None
    assert matched["area_id"] == area_id
    assigned_ids = {e["id"] for e in matched["assigned_employees"]}
    assert dedicated_employee["employee_id"] in assigned_ids


async def test_employee_can_cover_multiple_areas_across_multiple_zones(
    client: AsyncClient, admin_headers, created_customers, created_territories, dedicated_employee
):
    """Directly exercises the client's stated business rule: one employee
    can cover multiple Areas across multiple Zones, not just one."""
    zone_b_resp = await client.post(
        "/api/v1/territories", json={"name": f"{TEST_MARKER}Zone-B-{uuid.uuid4().hex[:6]}"}, headers=admin_headers
    )
    assert zone_b_resp.status_code == 201, zone_b_resp.text
    zone_b_id = zone_b_resp.json()["id"]
    created_territories.append(zone_b_id)

    area_a_resp = await client.post(
        "/api/v1/areas",
        json={"name": f"{TEST_MARKER}Area-A-{uuid.uuid4().hex[:6]}", "territory_id": dedicated_employee["territory_id"]},
        headers=admin_headers,
    )
    area_b_resp = await client.post(
        "/api/v1/areas",
        json={"name": f"{TEST_MARKER}Area-B-{uuid.uuid4().hex[:6]}", "territory_id": zone_b_id},
        headers=admin_headers,
    )
    assert area_a_resp.status_code == 201 and area_b_resp.status_code == 201
    area_a_id, area_b_id = area_a_resp.json()["id"], area_b_resp.json()["id"]

    for aid in (area_a_id, area_b_id):
        r = await client.post(
            f"/api/v1/employees/{dedicated_employee['employee_id']}/areas",
            json={"area_id": aid}, headers=admin_headers,
        )
        assert r.status_code == 201, r.text

    coverage = await client.get(
        f"/api/v1/employees/{dedicated_employee['employee_id']}/areas", headers=admin_headers
    )
    assert coverage.status_code == 200
    covered_area_ids = {a["area_id"] for a in coverage.json()}
    covered_zone_ids = {a["territory_id"] for a in coverage.json()}
    assert {area_a_id, area_b_id} <= covered_area_ids
    assert {dedicated_employee["territory_id"], zone_b_id} <= covered_zone_ids

    outlet_a = await _create_customer(client, admin_headers, created_customers)
    outlet_b = await _create_customer(client, admin_headers, created_customers)
    await client.patch(f"/api/v1/customers/{outlet_a['id']}", json={"area_id": area_a_id}, headers=admin_headers)
    await client.patch(f"/api/v1/customers/{outlet_b['id']}", json={"area_id": area_b_id}, headers=admin_headers)

    resp = await client.get(
        "/api/v1/collections/overview",
        params={"employee_id": dedicated_employee["employee_id"]},
        headers=admin_headers,
    )
    ids = {r["customer_id"] for r in resp.json()["outlets"]}
    assert outlet_a["id"] in ids and outlet_b["id"] in ids, "employee covering both areas must see both outlets"


async def test_area_filter_scopes_to_that_area_only(
    client: AsyncClient, admin_headers, created_customers, dedicated_employee
):
    area_resp = await client.post(
        "/api/v1/areas",
        json={"name": f"{TEST_MARKER}Area-{uuid.uuid4().hex[:6]}", "territory_id": dedicated_employee["territory_id"]},
        headers=admin_headers,
    )
    area_id = area_resp.json()["id"]

    in_area = await _create_customer(client, admin_headers, created_customers)
    await client.patch(f"/api/v1/customers/{in_area['id']}", json={"area_id": area_id}, headers=admin_headers)
    outside_area = await _create_customer(client, admin_headers, created_customers)

    resp = await client.get(
        "/api/v1/collections/overview", params={"area_id": area_id}, headers=admin_headers
    )
    ids = {r["customer_id"] for r in resp.json()["outlets"]}
    assert in_area["id"] in ids
    assert outside_area["id"] not in ids


async def test_collection_status_filter_returns_only_matching_status(
    client: AsyncClient, admin_headers, created_customers, created_invoices
):
    overdue_outlet = await _create_customer(client, admin_headers, created_customers)
    await _create_invoice(client, admin_headers, overdue_outlet["id"], days_ago=30, amount="1000.00", created_invoices=created_invoices)

    normal_outlet = await _create_customer(client, admin_headers, created_customers)
    await _create_invoice(client, admin_headers, normal_outlet["id"], days_ago=1, amount="1000.00", created_invoices=created_invoices)

    resp = await client.get(
        "/api/v1/collections/overview",
        params={"collection_status": "OVERDUE"},
        headers=admin_headers,
    )
    body = resp.json()
    ids = {r["customer_id"] for r in body["outlets"]}
    assert overdue_outlet["id"] in ids
    assert normal_outlet["id"] not in ids
    assert all(r["collection_status"] == "OVERDUE" for r in body["outlets"])


# -- Pagination + totals-vs-page consistency ------------------------------------

async def test_totals_reflect_the_full_filtered_set_not_just_the_current_page(
    client: AsyncClient, admin_headers, created_customers, created_invoices, dedicated_employee
):
    tid = dedicated_employee["territory_id"]
    outlet_a = await _create_customer(client, admin_headers, created_customers, territory_id=tid)
    outlet_b = await _create_customer(client, admin_headers, created_customers, territory_id=tid)
    await _create_invoice(client, admin_headers, outlet_a["id"], days_ago=1, amount="1000.00", created_invoices=created_invoices)
    await _create_invoice(client, admin_headers, outlet_b["id"], days_ago=1, amount="2000.00", created_invoices=created_invoices)

    resp = await client.get(
        "/api/v1/collections/overview",
        params={"territory_id": tid, "limit": 1},
        headers=admin_headers,
    )
    body = resp.json()
    assert len(body["outlets"]) == 1, "page must be limited to 1 row"
    assert body["total_count"] == 2, "total_count must reflect both matching outlets"
    assert body["totals"]["total_outlets"] == 2
    assert body["totals"]["total_invoiced"] == "3000.00"


async def test_skip_moves_to_the_next_page(
    client: AsyncClient, admin_headers, created_customers, dedicated_employee
):
    tid = dedicated_employee["territory_id"]
    outlet_a = await _create_customer(client, admin_headers, created_customers, territory_id=tid)
    outlet_b = await _create_customer(client, admin_headers, created_customers, territory_id=tid)

    page1 = await client.get(
        "/api/v1/collections/overview", params={"territory_id": tid, "limit": 1, "skip": 0}, headers=admin_headers
    )
    page2 = await client.get(
        "/api/v1/collections/overview", params={"territory_id": tid, "limit": 1, "skip": 1}, headers=admin_headers
    )
    id1 = page1.json()["outlets"][0]["customer_id"]
    id2 = page2.json()["outlets"][0]["customer_id"]
    assert id1 != id2
    assert {id1, id2} == {outlet_a["id"], outlet_b["id"]}


# -- Last payment / last visit ---------------------------------------------------

async def test_last_visit_reflects_checked_in_visit_not_a_future_scheduled_one(
    client: AsyncClient, admin_headers, employee_headers, created_customers, created_visits, seeded_world
):
    outlet = await _create_customer(client, admin_headers, created_customers)
    visit_id = await create_visit(client, admin_headers, outlet["id"], seeded_world["employee_id"], created_visits)

    check_in = await client.post(
        f"/api/v1/visits/{visit_id}/check-in",
        json={
            "latitude": seeded_world["customer_lat"], "longitude": seeded_world["customer_lng"],
            "accuracy_m": 5.0, "captured_at": datetime.now(timezone.utc).isoformat(),
        },
        headers=employee_headers,
    )
    assert check_in.status_code == 200, check_in.text

    resp = await client.get(
        "/api/v1/collections/overview", params={"search": outlet["outlet_code"]}, headers=admin_headers
    )
    row = next(r for r in resp.json()["outlets"] if r["customer_id"] == outlet["id"])
    assert row["most_recent_visit_date"] is not None
    assert row["most_recent_visit_employee_name"]


async def test_rejected_payment_is_not_the_most_recent_payment(
    client: AsyncClient, admin_headers, employee_headers, created_customers, created_visits,
    created_payments, seeded_world,
):
    outlet = await _create_customer(client, admin_headers, created_customers)
    visit_id = await create_visit(client, admin_headers, outlet["id"], seeded_world["employee_id"], created_visits)

    pay_resp = await client.post(
        "/api/v1/payments",
        json={"visit_id": visit_id, "amount": "999.00", "payment_method": "CASH", "payment_date": date.today().isoformat()},
        headers=employee_headers,
    )
    payment_id = pay_resp.json()["id"]
    created_payments.append(payment_id)
    await client.post(
        f"/api/v1/payments/{payment_id}/reject", json={"rejection_reason": "test"}, headers=admin_headers
    )

    resp = await client.get(
        "/api/v1/collections/overview", params={"search": outlet["outlet_code"]}, headers=admin_headers
    )
    row = next(r for r in resp.json()["outlets"] if r["customer_id"] == outlet["id"])
    assert row["most_recent_payment_date"] is None, "a rejected payment must never surface as the most recent one"


# -- Outlet detail extension (most_recent_visit on AccountSummary) -------------

async def test_account_summary_includes_most_recent_visit(
    client: AsyncClient, admin_headers, employee_headers, created_customers, created_visits, seeded_world
):
    outlet = await _create_customer(client, admin_headers, created_customers)
    visit_id = await create_visit(client, admin_headers, outlet["id"], seeded_world["employee_id"], created_visits)
    check_in = await client.post(
        f"/api/v1/visits/{visit_id}/check-in",
        json={
            "latitude": seeded_world["customer_lat"], "longitude": seeded_world["customer_lng"],
            "accuracy_m": 5.0, "captured_at": datetime.now(timezone.utc).isoformat(),
        },
        headers=employee_headers,
    )
    assert check_in.status_code == 200, check_in.text

    resp = await client.get(f"/api/v1/customers/{outlet['id']}/account", headers=admin_headers)
    body = resp.json()
    assert body["most_recent_visit_date"] is not None
    assert body["most_recent_visit_employee_name"]


async def test_account_summary_has_no_visit_yet_returns_none(
    client: AsyncClient, admin_headers, created_customers
):
    outlet = await _create_customer(client, admin_headers, created_customers)
    resp = await client.get(f"/api/v1/customers/{outlet['id']}/account", headers=admin_headers)
    body = resp.json()
    assert body["most_recent_visit_date"] is None
    assert body["most_recent_visit_employee_name"] is None
