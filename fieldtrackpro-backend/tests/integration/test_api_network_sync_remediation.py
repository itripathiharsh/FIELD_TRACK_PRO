"""
API, Network & Sync Remediation Tests.

Covers:
- APP-CONTRACT-002: Visit checkout notes persistence and retrieval
- APP-CONTRACT-003: Payment idempotency and double-submit protection
- APP-CONTRACT-001: GPS accuracy requirement validation
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_checkout_with_notes_persisted_and_returned_in_visit_read(
    client: AsyncClient, admin_headers, employee_headers, seeded_world, created_visits
):
    """APP-CONTRACT-002: Checkout with notes persists notes and returns them in VisitRead."""
    cust_id = seeded_world["customer_id"]
    emp_id = seeded_world["employee_id"]

    # 1. Create visit
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
    visit_id = create_resp.json()["id"]
    created_visits.append(visit_id)

    # 2. Check in
    now_iso = datetime.now(timezone.utc).isoformat()
    checkin_resp = await client.post(
        f"/api/v1/visits/{visit_id}/check-in",
        json={
            "latitude": 12.9716,
            "longitude": 77.5946,
            "accuracy_m": 8.0,
            "is_mock_location": False,
            "captured_at": now_iso,
        },
        headers=employee_headers,
    )
    assert checkin_resp.status_code == 200, checkin_resp.text

    # 3. Check out with notes
    notes_content = "Customer requested a product demo next Tuesday! Punctuation: & @ # $ %."
    checkout_resp = await client.post(
        f"/api/v1/visits/{visit_id}/check-out",
        json={
            "latitude": 12.9716,
            "longitude": 77.5946,
            "accuracy_m": 8.0,
            "is_mock_location": False,
            "captured_at": now_iso,
            "notes": notes_content,
        },
        headers=employee_headers,
    )
    assert checkout_resp.status_code == 200, checkout_resp.text
    completed_visit = checkout_resp.json()
    assert completed_visit["status"] == "COMPLETED"
    assert completed_visit["notes"] == notes_content

    # 4. Fetch visit by ID and verify notes
    get_resp = await client.get(
        f"/api/v1/visits/{visit_id}",
        headers=employee_headers,
    )
    assert get_resp.status_code == 200, get_resp.text
    assert get_resp.json()["notes"] == notes_content


@pytest.mark.asyncio
async def test_checkout_without_notes_has_null_notes(
    client: AsyncClient, admin_headers, employee_headers, seeded_world, created_visits
):
    """APP-CONTRACT-002: Checkout without notes leaves notes as None."""
    cust_id = seeded_world["customer_id"]
    emp_id = seeded_world["employee_id"]

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
    visit_id = create_resp.json()["id"]
    created_visits.append(visit_id)

    now_iso = datetime.now(timezone.utc).isoformat()
    await client.post(
        f"/api/v1/visits/{visit_id}/check-in",
        json={
            "latitude": 12.9716,
            "longitude": 77.5946,
            "accuracy_m": 5.0,
            "is_mock_location": False,
            "captured_at": now_iso,
        },
        headers=employee_headers,
    )

    checkout_resp = await client.post(
        f"/api/v1/visits/{visit_id}/check-out",
        json={
            "latitude": 12.9716,
            "longitude": 77.5946,
            "accuracy_m": 5.0,
            "is_mock_location": False,
            "captured_at": now_iso,
        },
        headers=employee_headers,
    )
    assert checkout_resp.status_code == 200, checkout_resp.text
    assert checkout_resp.json()["notes"] is None


@pytest.mark.asyncio
async def test_payment_idempotency_retry_returns_same_payment(
    client: AsyncClient, admin_headers, employee_headers, seeded_world
):
    """APP-CONTRACT-003: Retrying payment creation with the same idempotency_key returns the existing payment."""
    cust_id = seeded_world["customer_id"]
    emp_id = seeded_world["employee_id"]

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
    visit_id = create_resp.json()["id"]

    # In-progress visit
    now_iso = datetime.now(timezone.utc).isoformat()
    await client.post(
        f"/api/v1/visits/{visit_id}/check-in",
        json={
            "latitude": 12.9716,
            "longitude": 77.5946,
            "accuracy_m": 5.0,
            "is_mock_location": False,
            "captured_at": now_iso,
        },
        headers=employee_headers,
    )

    idempotency_key = f"pay-key-{uuid.uuid4()}"
    payment_payload = {
        "visit_id": visit_id,
        "amount": "1500.00",
        "payment_method": "CASH",
        "payment_date": date.today().isoformat(),
        "notes": "Collected cash on site",
        "idempotency_key": idempotency_key,
    }

    # First submit
    resp1 = await client.post(
        "/api/v1/payments",
        json=payment_payload,
        headers=employee_headers,
    )
    assert resp1.status_code == 201, resp1.text
    payment1 = resp1.json()

    # Retry submit with exact same idempotency_key
    resp2 = await client.post(
        "/api/v1/payments",
        json=payment_payload,
        headers=employee_headers,
    )
    assert resp2.status_code in (200, 201), resp2.text
    payment2 = resp2.json()

    assert payment1["id"] == payment2["id"]
    assert payment1["amount"] == payment2["amount"]
    assert payment1["visit_id"] == payment2["visit_id"]
