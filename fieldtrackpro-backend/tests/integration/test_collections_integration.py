"""
Integration tests for P1: Invoices, Aging, Payments/Collections, Accountant
review, and outlet Account summary.

Business-case coverage mirrors the client's own worked examples: an invoice
of 200,000 paid down by 50,000 then 100,000 must leave exactly 50,000
outstanding, with both payments remaining as separate historical rows.
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
import pytest_asyncio
from httpx import AsyncClient

from tests.integration.conftest import create_visit, requires_db

pytestmark = [requires_db, pytest.mark.integration, pytest.mark.asyncio]


def _iso_days_ago(days: int) -> str:
    return (date.today() - timedelta(days=days)).isoformat()


@pytest_asyncio.fixture
async def visit_id(client, admin_headers, seeded_world, created_visits) -> str:
    return await create_visit(
        client, admin_headers, seeded_world["customer_id"],
        seeded_world["employee_id"], created_visits,
    )


async def _create_invoice(
    client, admin_headers, customer_id, number, days_ago, amount, brand=None, created_invoices=None
):
    resp = await client.post(
        "/api/v1/invoices",
        json={
            "customer_id": customer_id,
            "invoice_number": number,
            "invoice_date": _iso_days_ago(days_ago),
            "amount": amount,
            "brand": brand,
        },
        headers=admin_headers,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    if created_invoices is not None:
        created_invoices.append(body["id"])
    return body


# -- Invoice creation + aging --------------------------------------------------

async def test_admin_can_create_invoice_with_correct_aging(
    client: AsyncClient, admin_headers, seeded_world, created_invoices
):
    inv = await _create_invoice(
        client, admin_headers, seeded_world["customer_id"], f"__itest__INV-{uuid.uuid4().hex[:8]}",
        days_ago=5, amount="10000.00", created_invoices=created_invoices,
    )
    assert inv["aging_status"] == "NORMAL"
    assert inv["days_outstanding"] == 5
    assert inv["remaining_amount"] == "10000.00"
    assert inv["mis_bucket"] == "0-15"


@pytest.mark.parametrize(
    "days_ago,expected_status",
    [(20, "NORMAL"), (21, "WARNING"), (25, "WARNING"), (26, "OVERDUE")],
)
async def test_invoice_aging_boundaries_via_api(
    client: AsyncClient, admin_headers, seeded_world, created_invoices, days_ago, expected_status
):
    inv = await _create_invoice(
        client, admin_headers, seeded_world["customer_id"], f"__itest__AGE-{uuid.uuid4().hex[:8]}",
        days_ago=days_ago, amount="1000.00", created_invoices=created_invoices,
    )
    assert inv["aging_status"] == expected_status


async def test_employee_cannot_create_invoice(client: AsyncClient, employee_headers, seeded_world):
    resp = await client.post(
        "/api/v1/invoices",
        json={
            "customer_id": seeded_world["customer_id"],
            "invoice_number": "__itest__SHOULD-FAIL",
            "invoice_date": _iso_days_ago(1),
            "amount": "100.00",
        },
        headers=employee_headers,
    )
    assert resp.status_code == 403


async def test_duplicate_invoice_number_for_same_outlet_rejected(
    client: AsyncClient, admin_headers, seeded_world, created_invoices
):
    number = f"__itest__DUP-{uuid.uuid4().hex[:8]}"
    first = await _create_invoice(
        client, admin_headers, seeded_world["customer_id"], number,
        days_ago=1, amount="500.00", created_invoices=created_invoices,
    )
    assert first
    resp = await client.post(
        "/api/v1/invoices",
        json={
            "customer_id": seeded_world["customer_id"], "invoice_number": number,
            "invoice_date": _iso_days_ago(1), "amount": "500.00",
        },
        headers=admin_headers,
    )
    assert resp.status_code == 409


async def test_unauthenticated_cannot_create_invoice(client: AsyncClient, seeded_world):
    resp = await client.post(
        "/api/v1/invoices",
        json={
            "customer_id": seeded_world["customer_id"], "invoice_number": "x",
            "invoice_date": _iso_days_ago(1), "amount": "1.00",
        },
    )
    assert resp.status_code == 401


# -- Outlet account visibility -------------------------------------------------

async def test_employee_without_a_visit_cannot_view_account(
    client: AsyncClient, other_employee_headers, seeded_world
):
    """other_employee has no visit to seeded_world's customer."""
    resp = await client.get(
        f"/api/v1/customers/{seeded_world['customer_id']}/account", headers=other_employee_headers
    )
    assert resp.status_code == 403, resp.text


async def test_employee_with_a_visit_can_view_account(
    client: AsyncClient, employee_headers, seeded_world, visit_id
):
    resp = await client.get(
        f"/api/v1/customers/{seeded_world['customer_id']}/account", headers=employee_headers
    )
    assert resp.status_code == 200, resp.text


async def test_admin_can_view_any_account_without_a_visit(
    client: AsyncClient, admin_headers, seeded_world
):
    resp = await client.get(
        f"/api/v1/customers/{seeded_world['customer_id']}/account", headers=admin_headers
    )
    assert resp.status_code == 200


async def test_unauthenticated_cannot_view_account(client: AsyncClient, seeded_world):
    resp = await client.get(f"/api/v1/customers/{seeded_world['customer_id']}/account")
    assert resp.status_code == 401


# -- Brand-wise aggregation -----------------------------------------------------

async def test_brand_summary_aggregates_correctly(
    client: AsyncClient, admin_headers, seeded_world, created_invoices
):
    cust_id = seeded_world["customer_id"]
    tag = uuid.uuid4().hex[:8]
    await _create_invoice(client, admin_headers, cust_id, f"__itest__B1-{tag}", 5, "10000.00", brand="Usha", created_invoices=created_invoices)
    await _create_invoice(client, admin_headers, cust_id, f"__itest__B2-{tag}", 5, "5000.00", brand="Usha", created_invoices=created_invoices)
    await _create_invoice(client, admin_headers, cust_id, f"__itest__B3-{tag}", 5, "2000.00", brand="Singer", created_invoices=created_invoices)

    resp = await client.get(f"/api/v1/customers/{cust_id}/account", headers=admin_headers)
    assert resp.status_code == 200
    brands = {b["brand"]: b for b in resp.json()["brand_summary"]}
    assert brands["Usha"]["total_invoiced"] == "15000.00"
    assert brands["Singer"]["total_invoiced"] == "2000.00"


# -- Payment / collection creation ---------------------------------------------

async def test_employee_can_collect_cash_payment_for_own_visit(
    client: AsyncClient, employee_headers, visit_id, created_payments
):
    resp = await client.post(
        "/api/v1/payments",
        json={
            "visit_id": visit_id, "amount": "500.00", "payment_method": "CASH",
            "payment_date": date.today().isoformat(),
        },
        headers=employee_headers,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    created_payments.append(body["id"])
    assert body["status"] == "PENDING_VERIFICATION"


async def test_same_idempotency_key_does_not_create_a_second_payment(
    client: AsyncClient, employee_headers, visit_id, created_payments
):
    """P0-2: a double-tapped/retried submit with the same key must not create
    two collection rows for the same visit."""
    key = f"__itest__idem-{uuid.uuid4().hex}"
    payload = {
        "visit_id": visit_id, "amount": "750.00", "payment_method": "CASH",
        "payment_date": date.today().isoformat(), "idempotency_key": key,
    }

    first = await client.post("/api/v1/payments", json=payload, headers=employee_headers)
    assert first.status_code == 201, first.text
    first_body = first.json()
    created_payments.append(first_body["id"])

    second = await client.post("/api/v1/payments", json=payload, headers=employee_headers)
    assert second.status_code == 201, second.text
    second_body = second.json()

    assert second_body["id"] == first_body["id"], "retried request must resolve to the same payment"


async def test_concurrent_duplicate_payment_requests_create_only_one_row(
    client: AsyncClient, employee_headers, visit_id, created_payments
):
    """P0-2: the DB constraint, not just the pre-check, must hold under a
    genuine race - two requests firing at once with the same key."""
    key = f"__itest__idem-race-{uuid.uuid4().hex}"
    payload = {
        "visit_id": visit_id, "amount": "900.00", "payment_method": "CASH",
        "payment_date": date.today().isoformat(), "idempotency_key": key,
    }

    responses = await asyncio.gather(
        client.post("/api/v1/payments", json=payload, headers=employee_headers),
        client.post("/api/v1/payments", json=payload, headers=employee_headers),
    )
    ids = set()
    for resp in responses:
        assert resp.status_code == 201, resp.text
        ids.add(resp.json()["id"])
    assert len(ids) == 1, "concurrent duplicate submissions must resolve to a single payment row"
    created_payments.append(ids.pop())


async def test_different_idempotency_keys_create_separate_payments(
    client: AsyncClient, employee_headers, visit_id, created_payments
):
    """Two genuinely separate collections against the same visit must both persist."""
    payload_a = {
        "visit_id": visit_id, "amount": "300.00", "payment_method": "CASH",
        "payment_date": date.today().isoformat(), "idempotency_key": f"__itest__A-{uuid.uuid4().hex}",
    }
    payload_b = {
        "visit_id": visit_id, "amount": "400.00", "payment_method": "CASH",
        "payment_date": date.today().isoformat(), "idempotency_key": f"__itest__B-{uuid.uuid4().hex}",
    }

    resp_a = await client.post("/api/v1/payments", json=payload_a, headers=employee_headers)
    resp_b = await client.post("/api/v1/payments", json=payload_b, headers=employee_headers)
    assert resp_a.status_code == 201, resp_a.text
    assert resp_b.status_code == 201, resp_b.text
    id_a, id_b = resp_a.json()["id"], resp_b.json()["id"]
    assert id_a != id_b
    created_payments.extend([id_a, id_b])


async def test_payment_without_idempotency_key_still_succeeds(
    client: AsyncClient, employee_headers, visit_id, created_payments
):
    """Backward compatibility: a caller that sends no key at all is unaffected."""
    resp = await client.post(
        "/api/v1/payments",
        json={
            "visit_id": visit_id, "amount": "250.00", "payment_method": "CASH",
            "payment_date": date.today().isoformat(),
        },
        headers=employee_headers,
    )
    assert resp.status_code == 201, resp.text
    created_payments.append(resp.json()["id"])


async def test_cheque_payment_requires_cheque_number(
    client: AsyncClient, employee_headers, visit_id
):
    resp = await client.post(
        "/api/v1/payments",
        json={
            "visit_id": visit_id, "amount": "500.00", "payment_method": "CHEQUE",
            "payment_date": date.today().isoformat(),
        },
        headers=employee_headers,
    )
    assert resp.status_code == 422


async def test_online_payment_requires_utr(client: AsyncClient, employee_headers, visit_id):
    resp = await client.post(
        "/api/v1/payments",
        json={
            "visit_id": visit_id, "amount": "500.00", "payment_method": "ONLINE",
            "payment_date": date.today().isoformat(),
        },
        headers=employee_headers,
    )
    assert resp.status_code == 422


async def test_employee_cannot_collect_against_another_employees_visit(
    client: AsyncClient, other_employee_headers, visit_id
):
    """visit_id belongs to seeded_world's primary employee, not other_employee."""
    resp = await client.post(
        "/api/v1/payments",
        json={
            "visit_id": visit_id, "amount": "500.00", "payment_method": "CASH",
            "payment_date": date.today().isoformat(),
        },
        headers=other_employee_headers,
    )
    assert resp.status_code == 403


async def test_payment_is_stamped_with_visits_customer_and_employee(
    client: AsyncClient, employee_headers, seeded_world, visit_id, created_payments
):
    """The client never supplies customer_id/employee_id - they come from the visit."""
    resp = await client.post(
        "/api/v1/payments",
        json={
            "visit_id": visit_id, "amount": "500.00", "payment_method": "CASH",
            "payment_date": date.today().isoformat(),
        },
        headers=employee_headers,
    )
    body = resp.json()
    created_payments.append(body["id"])
    assert body["customer_id"] == seeded_world["customer_id"]
    assert body["employee_id"] == seeded_world["employee_id"]


async def test_unauthenticated_cannot_create_payment(client: AsyncClient, visit_id):
    resp = await client.post(
        "/api/v1/payments",
        json={"visit_id": visit_id, "amount": "1.00", "payment_method": "CASH", "payment_date": date.today().isoformat()},
    )
    assert resp.status_code == 401


# -- Authorization on existing payments ----------------------------------------

async def test_employee_cannot_view_another_employees_payment(
    client: AsyncClient, employee_headers, other_employee_headers, visit_id, created_payments
):
    create_resp = await client.post(
        "/api/v1/payments",
        json={"visit_id": visit_id, "amount": "500.00", "payment_method": "CASH", "payment_date": date.today().isoformat()},
        headers=employee_headers,
    )
    payment_id = create_resp.json()["id"]
    created_payments.append(payment_id)

    resp = await client.get(f"/api/v1/payments/{payment_id}", headers=other_employee_headers)
    assert resp.status_code == 403


async def test_employee_cannot_verify_own_payment(
    client: AsyncClient, employee_headers, visit_id, created_payments
):
    create_resp = await client.post(
        "/api/v1/payments",
        json={"visit_id": visit_id, "amount": "500.00", "payment_method": "CASH", "payment_date": date.today().isoformat()},
        headers=employee_headers,
    )
    payment_id = create_resp.json()["id"]
    created_payments.append(payment_id)

    resp = await client.post(f"/api/v1/payments/{payment_id}/verify", headers=employee_headers)
    assert resp.status_code == 403


async def test_employee_cannot_see_review_queue(client: AsyncClient, employee_headers):
    resp = await client.get("/api/v1/payments/queue", headers=employee_headers)
    assert resp.status_code == 403


async def test_admin_sees_review_queue(client: AsyncClient, admin_headers, employee_headers, seeded_world, visit_id, created_payments):
    create_resp = await client.post(
        "/api/v1/payments",
        json={"visit_id": visit_id, "amount": "500.00", "payment_method": "CASH", "payment_date": date.today().isoformat()},
        headers=employee_headers,
    )
    payment_id = create_resp.json()["id"]
    created_payments.append(payment_id)

    resp = await client.get("/api/v1/payments/queue?status=PENDING_VERIFICATION", headers=admin_headers)
    assert resp.status_code == 200
    matches = [p for p in resp.json() if p["id"] == payment_id]
    assert matches, "the new payment should appear in the queue"

    # The queue table needs outlet/employee names, not just ids - these must
    # be enriched server-side rather than left null (see to_payment_read_for_queue).
    row = matches[0]
    assert row["customer_name"], "queue row must include the outlet name"
    assert row["employee_name"], "queue row must include the employee name"


# -- Verify / reject workflow + accounting math --------------------------------

async def test_reject_requires_a_reason(client: AsyncClient, admin_headers, employee_headers, visit_id, created_payments):
    create_resp = await client.post(
        "/api/v1/payments",
        json={"visit_id": visit_id, "amount": "500.00", "payment_method": "CASH", "payment_date": date.today().isoformat()},
        headers=employee_headers,
    )
    payment_id = create_resp.json()["id"]
    created_payments.append(payment_id)

    resp = await client.post(f"/api/v1/payments/{payment_id}/reject", json={}, headers=admin_headers)
    assert resp.status_code == 422

    resp = await client.post(
        f"/api/v1/payments/{payment_id}/reject",
        json={"rejection_reason": "Duplicate collection"},
        headers=admin_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "REJECTED"


async def test_cannot_review_an_already_reviewed_payment(
    client: AsyncClient, admin_headers, employee_headers, visit_id, created_payments
):
    create_resp = await client.post(
        "/api/v1/payments",
        json={"visit_id": visit_id, "amount": "500.00", "payment_method": "CASH", "payment_date": date.today().isoformat()},
        headers=employee_headers,
    )
    payment_id = create_resp.json()["id"]
    created_payments.append(payment_id)

    verify_resp = await client.post(f"/api/v1/payments/{payment_id}/verify", headers=admin_headers)
    assert verify_resp.status_code == 200

    resp = await client.post(f"/api/v1/payments/{payment_id}/verify", headers=admin_headers)
    assert resp.status_code == 409


async def test_rejected_payment_does_not_count_toward_outstanding(
    client: AsyncClient, admin_headers, employee_headers, seeded_world, visit_id, created_invoices, created_payments
):
    inv = await _create_invoice(
        client, admin_headers, seeded_world["customer_id"], f"__itest__REJ-{uuid.uuid4().hex[:8]}",
        days_ago=5, amount="1000.00", created_invoices=created_invoices,
    )
    create_resp = await client.post(
        "/api/v1/payments",
        json={
            "visit_id": visit_id, "invoice_id": inv["id"], "amount": "1000.00",
            "payment_method": "CASH", "payment_date": date.today().isoformat(),
        },
        headers=employee_headers,
    )
    payment_id = create_resp.json()["id"]
    created_payments.append(payment_id)

    await client.post(
        f"/api/v1/payments/{payment_id}/reject",
        json={"rejection_reason": "Could not confirm with retailer"},
        headers=admin_headers,
    )

    check = await client.get(f"/api/v1/invoices/{inv['id']}", headers=admin_headers)
    assert check.json()["remaining_amount"] == "1000.00"
    assert check.json()["payment_status"] == "UNPAID"


async def test_verified_payments_reduce_outstanding_and_preserve_history(
    client: AsyncClient, admin_headers, employee_headers, seeded_world, visit_id, created_invoices, created_payments
):
    """The client's own worked example: 200,000 invoice, 50,000 then 100,000
    paid down -> 50,000 remaining, with both payments still present as
    separate historical rows (never overwriting a single running balance)."""
    inv = await _create_invoice(
        client, admin_headers, seeded_world["customer_id"], f"__itest__HIST-{uuid.uuid4().hex[:8]}",
        days_ago=10, amount="200000.00", created_invoices=created_invoices,
    )

    async def collect_and_verify(amount: str):
        resp = await client.post(
            "/api/v1/payments",
            json={
                "visit_id": visit_id, "invoice_id": inv["id"], "amount": amount,
                "payment_method": "CASH", "payment_date": date.today().isoformat(),
            },
            headers=employee_headers,
        )
        payment_id = resp.json()["id"]
        created_payments.append(payment_id)
        verify = await client.post(f"/api/v1/payments/{payment_id}/verify", headers=admin_headers)
        assert verify.status_code == 200
        return payment_id

    p1 = await collect_and_verify("50000.00")

    check1 = await client.get(f"/api/v1/invoices/{inv['id']}", headers=admin_headers)
    assert check1.json()["remaining_amount"] == "150000.00"
    assert check1.json()["payment_status"] == "PARTIALLY_PAID"

    p2 = await collect_and_verify("100000.00")

    check2 = await client.get(f"/api/v1/invoices/{inv['id']}", headers=admin_headers)
    assert check2.json()["remaining_amount"] == "50000.00"
    assert check2.json()["verified_paid_amount"] == "150000.00"

    # History intact: both payments still exist as distinct rows.
    p1_check = await client.get(f"/api/v1/payments/{p1}", headers=admin_headers)
    p2_check = await client.get(f"/api/v1/payments/{p2}", headers=admin_headers)
    assert p1_check.status_code == 200 and p1_check.json()["amount"] == "50000.00"
    assert p2_check.status_code == 200 and p2_check.json()["amount"] == "100000.00"


# -- Account aggregation correctness ---------------------------------------------

async def test_unallocated_verified_payment_still_reduces_total_outstanding(
    client: AsyncClient, admin_headers, employee_headers, seeded_world, visit_id, created_invoices, created_payments
):
    """
    A payment the employee didn't tie to a specific invoice (left blank -
    the accountant can allocate it later) must still count against the
    outlet's aggregate outstanding once verified. Regression for a bug found
    via live browser testing: total_outstanding was computed as
    sum(invoice.remaining_amount), which never moves for unallocated
    payments even though total_paid does.
    """
    inv = await _create_invoice(
        client, admin_headers, seeded_world["customer_id"], f"__itest__UNALLOC-{uuid.uuid4().hex[:8]}",
        days_ago=5, amount="100000.00", created_invoices=created_invoices,
    )

    # After adding the invoice (before any payment): outstanding rose by
    # exactly the invoice amount relative to whatever baseline existed.
    after_invoice = await client.get(f"/api/v1/customers/{seeded_world['customer_id']}/account", headers=admin_headers)
    outstanding_with_invoice = float(after_invoice.json()["total_outstanding"])
    paid_before_payment = float(after_invoice.json()["total_paid"])

    create_resp = await client.post(
        "/api/v1/payments",
        # No invoice_id - deliberately unallocated.
        json={"visit_id": visit_id, "amount": "30000.00", "payment_method": "CASH", "payment_date": date.today().isoformat()},
        headers=employee_headers,
    )
    payment_id = create_resp.json()["id"]
    created_payments.append(payment_id)
    await client.post(f"/api/v1/payments/{payment_id}/verify", headers=admin_headers)

    after_payment = await client.get(f"/api/v1/customers/{seeded_world['customer_id']}/account", headers=admin_headers)
    after_json = after_payment.json()
    # The unallocated-but-verified 30,000 must reduce the aggregate
    # outstanding by exactly 30,000, even though no single invoice's own
    # remaining_amount changed.
    assert float(after_json["total_outstanding"]) == round(outstanding_with_invoice - 30000.00, 2)
    assert float(after_json["total_paid"]) == round(paid_before_payment + 30000.00, 2)


# -- Payment proof --------------------------------------------------------------

async def test_upload_and_download_payment_proof(
    client: AsyncClient, admin_headers, employee_headers, visit_id, created_payments
):
    create_resp = await client.post(
        "/api/v1/payments",
        json={
            "visit_id": visit_id, "amount": "500.00", "payment_method": "CHEQUE",
            "payment_date": date.today().isoformat(), "cheque_number": "CHQ001",
        },
        headers=employee_headers,
    )
    payment_id = create_resp.json()["id"]
    created_payments.append(payment_id)

    from tests.integration.conftest import VALID_JPEG

    upload = await client.post(
        f"/api/v1/payments/{payment_id}/proof",
        files={"file": ("cheque.jpg", VALID_JPEG, "image/jpeg")},
        headers=employee_headers,
    )
    assert upload.status_code == 201, upload.text
    proof_id = upload.json()["id"]

    dl = await client.get(f"/api/v1/payments/proofs/{proof_id}/download", headers=admin_headers)
    assert dl.status_code == 200
    download_url = dl.json()["download_url"]
    assert download_url.startswith("http://") or download_url.startswith("https://")

    relative = download_url.split("/api/v1", 1)[1]
    file_resp = await client.get(f"/api/v1{relative}")
    assert file_resp.status_code == 200
    assert file_resp.content == VALID_JPEG


async def test_employee_cannot_upload_proof_to_another_employees_payment(
    client: AsyncClient, employee_headers, other_employee_headers, visit_id, created_payments
):
    create_resp = await client.post(
        "/api/v1/payments",
        json={"visit_id": visit_id, "amount": "500.00", "payment_method": "CASH", "payment_date": date.today().isoformat()},
        headers=employee_headers,
    )
    payment_id = create_resp.json()["id"]
    created_payments.append(payment_id)

    from tests.integration.conftest import VALID_JPEG

    resp = await client.post(
        f"/api/v1/payments/{payment_id}/proof",
        files={"file": ("x.jpg", VALID_JPEG, "image/jpeg")},
        headers=other_employee_headers,
    )
    assert resp.status_code == 403


# -- Invoice history endpoint ---------------------------------------------------

async def test_invoice_history_endpoint_lists_all_invoices_with_aging(
    client: AsyncClient, admin_headers, employee_headers, seeded_world, visit_id, created_invoices
):
    tag = uuid.uuid4().hex[:8]
    await _create_invoice(client, admin_headers, seeded_world["customer_id"], f"__itest__LIST1-{tag}", 5, "100.00", created_invoices=created_invoices)
    await _create_invoice(client, admin_headers, seeded_world["customer_id"], f"__itest__LIST2-{tag}", 30, "200.00", created_invoices=created_invoices)

    resp = await client.get(f"/api/v1/customers/{seeded_world['customer_id']}/invoices", headers=employee_headers)
    assert resp.status_code == 200
    numbers = {inv["invoice_number"] for inv in resp.json()}
    assert f"__itest__LIST1-{tag}" in numbers
    assert f"__itest__LIST2-{tag}" in numbers


# -- Order capture (reuses visit_media) ------------------------------------------

async def test_order_capture_reuses_media_upload_with_note(
    client: AsyncClient, employee_headers, visit_id, created_media
):
    from tests.integration.conftest import VALID_JPEG

    resp = await client.post(
        f"/api/v1/visits/{visit_id}/media?is_order=true&note=5x+Usha+fans%2C+2x+Singer+mixers",
        files={"file": ("order.jpg", VALID_JPEG, "image/jpeg")},
        headers=employee_headers,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    created_media.append(body["id"])
    assert body["media_type"] == "ORDER"
    assert "Usha" in (body["note"] or "")
