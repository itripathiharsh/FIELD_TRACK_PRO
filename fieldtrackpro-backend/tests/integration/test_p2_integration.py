"""
Integration tests for P2: Brand-wise history enrichment, Order-capture
history views, Employee Activity, and Territory Reassignment.

Order-capture upload itself (is_order=true reusing visit_media) is already
covered by test_collections_integration.py::test_order_capture_reuses_media_upload_with_note -
this file covers the NEW P2 surfaces built on top of it.
"""
from __future__ import annotations

import uuid
from datetime import date, timedelta

import pytest
import pytest_asyncio
from httpx import AsyncClient

from tests.integration.conftest import VALID_JPEG, create_visit, db_cursor, requires_db

pytestmark = [requires_db, pytest.mark.integration, pytest.mark.asyncio]


def _iso_days_ago(days: int) -> str:
    return (date.today() - timedelta(days=days)).isoformat()


@pytest.fixture(autouse=True)
def _restore_employee_territory(seeded_world):
    """
    P2-D's create_assignment eagerly syncs Employee.territory_id when a
    PERMANENT assignment is immediately effective (see
    territory_assignment_service.py) - a deliberate convenience-cache
    update, never a loss of history. But seeded_world's employee is
    session-scoped and shared across every test in this file, so without
    this, one test's sync would leak into every test that runs after it and
    assumes the original territory_id. Snapshot and restore it around each
    test so P2-D tests stay order-independent.
    """
    with db_cursor(privileged=True) as cur:
        cur.execute("SELECT territory_id FROM employees WHERE id = %s", (seeded_world["employee_id"],))
        original = cur.fetchone()["territory_id"]
    yield
    with db_cursor(privileged=True) as cur:
        cur.execute("UPDATE employees SET territory_id = %s WHERE id = %s", (original, seeded_world["employee_id"]))


@pytest_asyncio.fixture
async def visit_id(client, admin_headers, seeded_world, created_visits) -> str:
    return await create_visit(
        client, admin_headers, seeded_world["customer_id"], seeded_world["employee_id"], created_visits,
    )


async def _create_invoice(client, admin_headers, customer_id, number, days_ago, amount, brand, created_invoices):
    resp = await client.post(
        "/api/v1/invoices",
        json={
            "customer_id": customer_id, "invoice_number": number,
            "invoice_date": _iso_days_ago(days_ago), "amount": amount, "brand": brand,
        },
        headers=admin_headers,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    created_invoices.append(body["id"])
    return body


# -- P2-A: Brand-wise history enrichment ---------------------------------------

async def test_brand_summary_includes_counts_overdue_and_latest_dates(
    client: AsyncClient, admin_headers, employee_headers, seeded_world, visit_id, created_invoices, created_payments
):
    cust_id = seeded_world["customer_id"]
    tag = uuid.uuid4().hex[:8]
    old_invoice = await _create_invoice(
        client, admin_headers, cust_id, f"__itest__PBA1-{tag}", days_ago=40, amount="10000.00",
        brand="Usha", created_invoices=created_invoices,
    )
    recent_invoice = await _create_invoice(
        client, admin_headers, cust_id, f"__itest__PBA2-{tag}", days_ago=2, amount="5000.00",
        brand="Usha", created_invoices=created_invoices,
    )

    pay_resp = await client.post(
        "/api/v1/payments",
        json={
            "visit_id": visit_id, "invoice_id": recent_invoice["id"], "amount": "5000.00",
            "payment_method": "CASH", "payment_date": _iso_days_ago(1),
        },
        headers=employee_headers,
    )
    assert pay_resp.status_code == 201, pay_resp.text
    payment_id = pay_resp.json()["id"]
    created_payments.append(payment_id)
    verify_resp = await client.post(f"/api/v1/payments/{payment_id}/verify", headers=admin_headers)
    assert verify_resp.status_code == 200, verify_resp.text

    resp = await client.get(f"/api/v1/customers/{cust_id}/account", headers=admin_headers)
    assert resp.status_code == 200
    usha = next(b for b in resp.json()["brand_summary"] if b["brand"] == "Usha")
    assert usha["invoice_count"] == 2
    assert usha["payment_count"] == 1
    assert usha["total_invoiced"] == "15000.00"
    assert usha["total_paid"] == "5000.00"
    assert usha["total_outstanding"] == "10000.00"
    assert usha["overdue_amount"] == "10000.00"  # only the 40-day-old invoice is overdue
    assert usha["latest_invoice_date"] == _iso_days_ago(2)
    assert usha["latest_payment_date"] == _iso_days_ago(1)
    assert old_invoice["id"] != recent_invoice["id"]


async def test_brand_summary_unallocated_payment_not_attributed_to_any_brand(
    client: AsyncClient, admin_headers, employee_headers, seeded_world, visit_id, created_invoices, created_payments
):
    """An unallocated (invoice_id=None) verified payment has no brand to attribute it to."""
    cust_id = seeded_world["customer_id"]
    tag = uuid.uuid4().hex[:8]
    await _create_invoice(
        client, admin_headers, cust_id, f"__itest__PBB1-{tag}", days_ago=1, amount="1000.00",
        brand="Zebronics", created_invoices=created_invoices,
    )
    pay_resp = await client.post(
        "/api/v1/payments",
        json={"visit_id": visit_id, "amount": "300.00", "payment_method": "CASH", "payment_date": _iso_days_ago(0)},
        headers=employee_headers,
    )
    assert pay_resp.status_code == 201, pay_resp.text
    payment_id = pay_resp.json()["id"]
    created_payments.append(payment_id)
    assert pay_resp.json()["invoice_id"] is None
    verify_resp = await client.post(f"/api/v1/payments/{payment_id}/verify", headers=admin_headers)
    assert verify_resp.status_code == 200

    resp = await client.get(f"/api/v1/customers/{cust_id}/account", headers=admin_headers)
    zeb = next(b for b in resp.json()["brand_summary"] if b["brand"] == "Zebronics")
    assert zeb["payment_count"] == 0
    assert zeb["latest_payment_date"] is None


async def test_brand_summary_unbranded_invoice_bucketed_separately(
    client: AsyncClient, admin_headers, seeded_world, created_invoices
):
    cust_id = seeded_world["customer_id"]
    tag = uuid.uuid4().hex[:8]
    await _create_invoice(
        client, admin_headers, cust_id, f"__itest__PBC1-{tag}", days_ago=1, amount="750.00",
        brand=None, created_invoices=created_invoices,
    )
    resp = await client.get(f"/api/v1/customers/{cust_id}/account", headers=admin_headers)
    unbranded = next(b for b in resp.json()["brand_summary"] if b["brand"] == "Unbranded")
    assert unbranded["invoice_count"] >= 1


# -- P2-B: Order history views --------------------------------------------------

async def test_admin_can_view_customer_order_history_across_visits(
    client: AsyncClient, admin_headers, employee_headers, seeded_world, visit_id, created_media
):
    upload = await client.post(
        f"/api/v1/visits/{visit_id}/media?is_order=true&note=__itest__+3x+Usha+fans",
        files={"file": ("order.jpg", VALID_JPEG, "image/jpeg")},
        headers=employee_headers,
    )
    assert upload.status_code == 201, upload.text
    created_media.append(upload.json()["id"])

    resp = await client.get(f"/api/v1/customers/{seeded_world['customer_id']}/orders", headers=admin_headers)
    assert resp.status_code == 200, resp.text
    orders = resp.json()
    assert any("Usha" in (o["note"] or "") for o in orders)
    order = next(o for o in orders if "Usha" in (o["note"] or ""))
    assert order["visit_scheduled_at"] is not None
    assert order["employee_name"] == "__itest__ Primary Rep"


async def test_employee_without_visit_cannot_view_customer_order_history(
    client: AsyncClient, other_employee_headers, seeded_world
):
    resp = await client.get(f"/api/v1/customers/{seeded_world['customer_id']}/orders", headers=other_employee_headers)
    assert resp.status_code == 403


async def test_regular_photo_media_excluded_from_order_history(
    client: AsyncClient, admin_headers, employee_headers, seeded_world, visit_id, created_media
):
    upload = await client.post(
        f"/api/v1/visits/{visit_id}/media",
        files={"file": ("plain.jpg", VALID_JPEG, "image/jpeg")},
        headers=employee_headers,
    )
    assert upload.status_code == 201
    created_media.append(upload.json()["id"])
    assert upload.json()["media_type"] == "PHOTO"

    resp = await client.get(f"/api/v1/customers/{seeded_world['customer_id']}/orders", headers=admin_headers)
    assert all(o["id"] != upload.json()["id"] for o in resp.json())


# -- P2-C: Employee Activity ------------------------------------------------------

async def test_admin_can_view_employee_activity_aggregation(
    client: AsyncClient, admin_headers, employee_headers, seeded_world, visit_id, created_payments, created_media
):
    pay_resp = await client.post(
        "/api/v1/payments",
        json={"visit_id": visit_id, "amount": "400.00", "payment_method": "CASH", "payment_date": _iso_days_ago(0)},
        headers=employee_headers,
    )
    assert pay_resp.status_code == 201
    created_payments.append(pay_resp.json()["id"])

    order_resp = await client.post(
        f"/api/v1/visits/{visit_id}/media?is_order=true&note=__itest__activity+order",
        files={"file": ("o.jpg", VALID_JPEG, "image/jpeg")},
        headers=employee_headers,
    )
    assert order_resp.status_code == 201
    created_media.append(order_resp.json()["id"])

    resp = await client.get(f"/api/v1/employees/{seeded_world['employee_id']}/activity", headers=admin_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["employee_id"] == seeded_world["employee_id"]
    assert body["visits_total"] >= 1
    assert any(v["id"] == visit_id for v in body["visits"])
    assert body["collections_total"] >= 1
    assert body["collections_pending"] >= 1
    assert body["orders_total"] >= 1
    assert any("activity order" in (o["note"] or "") for o in body["orders"])


async def test_employee_cannot_view_employee_activity(client: AsyncClient, employee_headers, seeded_world):
    resp = await client.get(f"/api/v1/employees/{seeded_world['employee_id']}/activity", headers=employee_headers)
    assert resp.status_code == 403


async def test_employee_activity_404_for_unknown_employee(client: AsyncClient, admin_headers):
    resp = await client.get(f"/api/v1/employees/{uuid.uuid4()}/activity", headers=admin_headers)
    assert resp.status_code == 404


# -- P2-D: Territory Reassignment --------------------------------------------------

@pytest_asyncio.fixture
async def second_territory_id(client: AsyncClient, admin_headers, created_territories) -> str:
    resp = await client.post(
        "/api/v1/territories", json={"name": f"__itest__Reassign-{uuid.uuid4().hex[:8]}"}, headers=admin_headers,
    )
    assert resp.status_code == 201, resp.text
    tid = resp.json()["id"]
    created_territories.append(tid)
    return tid


async def test_permanent_reassignment_effective_today_becomes_current(
    client: AsyncClient, admin_headers, seeded_world, second_territory_id
):
    emp_id = seeded_world["employee_id"]
    resp = await client.post(
        f"/api/v1/employees/{emp_id}/territory-assignments",
        json={"territory_id": second_territory_id, "assignment_type": "PERMANENT", "start_date": date.today().isoformat()},
        headers=admin_headers,
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["is_current"] is True

    history = await client.get(f"/api/v1/employees/{emp_id}/territory-assignments", headers=admin_headers)
    assert history.status_code == 200
    assert history.json()["effective_territory_id"] == second_territory_id


async def test_future_permanent_reassignment_does_not_apply_yet(
    client: AsyncClient, admin_headers, seeded_world, second_territory_id
):
    emp_id = seeded_world["employee_id"]
    future_date = (date.today() + timedelta(days=30)).isoformat()
    resp = await client.post(
        f"/api/v1/employees/{emp_id}/territory-assignments",
        json={"territory_id": second_territory_id, "assignment_type": "PERMANENT", "start_date": future_date},
        headers=admin_headers,
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["is_current"] is False

    history = await client.get(f"/api/v1/employees/{emp_id}/territory-assignments", headers=admin_headers)
    # Still the employee's original (legacy) territory - the future
    # assignment has not taken effect yet.
    assert history.json()["effective_territory_id"] == seeded_world["territory_id"]


async def test_temporary_reassignment_active_window_wins_over_base(
    client: AsyncClient, admin_headers, seeded_world, second_territory_id
):
    emp_id = seeded_world["employee_id"]
    resp = await client.post(
        f"/api/v1/employees/{emp_id}/territory-assignments",
        json={
            "territory_id": second_territory_id, "assignment_type": "TEMPORARY",
            "start_date": _iso_days_ago(1), "end_date": (date.today() + timedelta(days=5)).isoformat(),
        },
        headers=admin_headers,
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["is_current"] is True

    history = await client.get(f"/api/v1/employees/{emp_id}/territory-assignments", headers=admin_headers)
    assert history.json()["effective_territory_id"] == second_territory_id


async def test_expired_temporary_reassignment_reverts_to_base(
    client: AsyncClient, admin_headers, seeded_world, second_territory_id
):
    emp_id = seeded_world["employee_id"]
    resp = await client.post(
        f"/api/v1/employees/{emp_id}/territory-assignments",
        json={
            "territory_id": second_territory_id, "assignment_type": "TEMPORARY",
            "start_date": _iso_days_ago(10), "end_date": _iso_days_ago(2),
        },
        headers=admin_headers,
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["is_current"] is False  # already expired

    history = await client.get(f"/api/v1/employees/{emp_id}/territory-assignments", headers=admin_headers)
    assert history.json()["effective_territory_id"] == seeded_world["territory_id"]


async def test_temporary_assignment_requires_end_date(
    client: AsyncClient, admin_headers, seeded_world, second_territory_id
):
    resp = await client.post(
        f"/api/v1/employees/{seeded_world['employee_id']}/territory-assignments",
        json={"territory_id": second_territory_id, "assignment_type": "TEMPORARY", "start_date": date.today().isoformat()},
        headers=admin_headers,
    )
    assert resp.status_code == 400


async def test_temporary_assignment_end_before_start_rejected(
    client: AsyncClient, admin_headers, seeded_world, second_territory_id
):
    resp = await client.post(
        f"/api/v1/employees/{seeded_world['employee_id']}/territory-assignments",
        json={
            "territory_id": second_territory_id, "assignment_type": "TEMPORARY",
            "start_date": date.today().isoformat(), "end_date": _iso_days_ago(1),
        },
        headers=admin_headers,
    )
    assert resp.status_code == 400


async def test_permanent_assignment_with_end_date_rejected(
    client: AsyncClient, admin_headers, seeded_world, second_territory_id
):
    resp = await client.post(
        f"/api/v1/employees/{seeded_world['employee_id']}/territory-assignments",
        json={
            "territory_id": second_territory_id, "assignment_type": "PERMANENT",
            "start_date": date.today().isoformat(), "end_date": (date.today() + timedelta(days=1)).isoformat(),
        },
        headers=admin_headers,
    )
    assert resp.status_code == 400


async def test_overlapping_temporary_assignments_rejected(
    client: AsyncClient, admin_headers, seeded_world, second_territory_id
):
    emp_id = seeded_world["employee_id"]
    first = await client.post(
        f"/api/v1/employees/{emp_id}/territory-assignments",
        json={
            "territory_id": second_territory_id, "assignment_type": "TEMPORARY",
            "start_date": (date.today() + timedelta(days=10)).isoformat(),
            "end_date": (date.today() + timedelta(days=20)).isoformat(),
        },
        headers=admin_headers,
    )
    assert first.status_code == 201, first.text

    overlapping = await client.post(
        f"/api/v1/employees/{emp_id}/territory-assignments",
        json={
            "territory_id": second_territory_id, "assignment_type": "TEMPORARY",
            "start_date": (date.today() + timedelta(days=15)).isoformat(),
            "end_date": (date.today() + timedelta(days=25)).isoformat(),
        },
        headers=admin_headers,
    )
    assert overlapping.status_code == 409


async def test_immediate_permanent_reassignment_syncs_legacy_column(
    client: AsyncClient, admin_headers, seeded_world, second_territory_id
):
    """The legacy Employee.territory_id pointer is kept in sync when a
    PERMANENT assignment is immediately effective - every pre-existing
    admin view that reads that raw column directly (e.g. TerritoryDetailPage's
    "employees assigned to this territory" list) must keep working without
    a full audit of every such call site. This never loses history: the
    assignment row above is the permanent record regardless of what the
    cache column says."""
    emp_id = seeded_world["employee_id"]
    resp = await client.post(
        f"/api/v1/employees/{emp_id}/territory-assignments",
        json={"territory_id": second_territory_id, "assignment_type": "PERMANENT", "start_date": date.today().isoformat()},
        headers=admin_headers,
    )
    assert resp.status_code == 201

    with db_cursor() as cur:
        cur.execute("SELECT territory_id FROM employees WHERE id = %s", (emp_id,))
        row = cur.fetchone()
        assert str(row["territory_id"]) == second_territory_id


async def test_future_permanent_reassignment_does_not_sync_legacy_column_yet(
    client: AsyncClient, admin_headers, seeded_world, second_territory_id
):
    """The inverse of the immediate case: a not-yet-effective permanent
    reassignment must not touch the legacy column early."""
    emp_id = seeded_world["employee_id"]
    resp = await client.post(
        f"/api/v1/employees/{emp_id}/territory-assignments",
        json={
            "territory_id": second_territory_id, "assignment_type": "PERMANENT",
            "start_date": (date.today() + timedelta(days=30)).isoformat(),
        },
        headers=admin_headers,
    )
    assert resp.status_code == 201

    with db_cursor() as cur:
        cur.execute("SELECT territory_id FROM employees WHERE id = %s", (emp_id,))
        row = cur.fetchone()
        assert str(row["territory_id"]) == seeded_world["territory_id"]


async def test_temporary_reassignment_never_syncs_legacy_column(
    client: AsyncClient, admin_headers, seeded_world, second_territory_id
):
    """A temporary override must revert on its own once it expires - it must
    never touch the legacy column even while active, or reverting would
    require a scheduled job that doesn't exist."""
    emp_id = seeded_world["employee_id"]
    resp = await client.post(
        f"/api/v1/employees/{emp_id}/territory-assignments",
        json={
            "territory_id": second_territory_id, "assignment_type": "TEMPORARY",
            "start_date": _iso_days_ago(1), "end_date": (date.today() + timedelta(days=5)).isoformat(),
        },
        headers=admin_headers,
    )
    assert resp.status_code == 201

    with db_cursor() as cur:
        cur.execute("SELECT territory_id FROM employees WHERE id = %s", (emp_id,))
        row = cur.fetchone()
        assert str(row["territory_id"]) == seeded_world["territory_id"]


async def test_reassignment_does_not_alter_historical_visit_or_customer_territory(
    client: AsyncClient, admin_headers, seeded_world, visit_id, second_territory_id
):
    """A visit recorded while the employee was in the old territory must
    never appear to have happened in the new one - visits don't even store a
    territory, and the customer's own territory_id is entirely unrelated to
    the employee's, so reassigning the employee must never touch either."""
    resp = await client.post(
        f"/api/v1/employees/{seeded_world['employee_id']}/territory-assignments",
        json={"territory_id": second_territory_id, "assignment_type": "PERMANENT", "start_date": date.today().isoformat()},
        headers=admin_headers,
    )
    assert resp.status_code == 201

    visit_resp = await client.get(f"/api/v1/visits/{visit_id}", headers=admin_headers)
    assert visit_resp.status_code == 200
    assert visit_resp.json()["customer_id"] == seeded_world["customer_id"]

    with db_cursor() as cur:
        cur.execute("SELECT territory_id FROM customers WHERE id = %s", (seeded_world["customer_id"],))
        assert str(cur.fetchone()["territory_id"]) == seeded_world["territory_id"]


async def test_employee_cannot_create_or_view_territory_assignments(
    client: AsyncClient, employee_headers, seeded_world, second_territory_id
):
    emp_id = seeded_world["employee_id"]
    get_resp = await client.get(f"/api/v1/employees/{emp_id}/territory-assignments", headers=employee_headers)
    assert get_resp.status_code == 403

    post_resp = await client.post(
        f"/api/v1/employees/{emp_id}/territory-assignments",
        json={"territory_id": second_territory_id, "assignment_type": "PERMANENT", "start_date": date.today().isoformat()},
        headers=employee_headers,
    )
    assert post_resp.status_code == 403


async def test_employee_login_reflects_active_temporary_reassignment(
    client: AsyncClient, admin_headers, seeded_world, second_territory_id
):
    """P2-D employee-behavior requirement: /auth/me (fed by the login flow)
    must reflect the currently effective territory, not the raw column."""
    emp_id = seeded_world["employee_id"]
    resp = await client.post(
        f"/api/v1/employees/{emp_id}/territory-assignments",
        json={
            "territory_id": second_territory_id, "assignment_type": "TEMPORARY",
            "start_date": _iso_days_ago(1), "end_date": (date.today() + timedelta(days=5)).isoformat(),
        },
        headers=admin_headers,
    )
    assert resp.status_code == 201

    login_resp = await client.post(
        "/api/v1/auth/login", json={"email": seeded_world["employee_email"], "password": seeded_world["password"]},
    )
    token = login_resp.json()["access_token"]
    me = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["territory_id"] == second_territory_id
