"""
Forensic Audit Test Suite — Attendance, GPS, Customer Location & Scheduler Concurrency.

Covers:
- APP-ATT-006: Customer location not configured (NULL) -> is_valid=False, failure_reason='Customer location not configured'
- APP-ATT-014: Negative visit duration rejection (check_out < check_in) -> HTTP 422 INVALID_VISIT_DURATION
- APP-ATT-022: Missed visit scheduler atomic concurrency protection (WHERE status = 'PENDING')
- APP-ATT-012: Check-out notes schema support
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.customer import Customer
from app.models.visit import Visit, VisitStatus
from app.schemas.visit import CheckOutRequest
from app.services.customer_service import verify_device_against_customer
from app.services.visit_service import check_out
from app.exceptions.custom import BaseAPIException
from app.jobs.missed_visit_scheduler import mark_overdue_visits_as_missed


@pytest.mark.asyncio
async def test_verify_device_against_customer_null_location():
    """APP-ATT-006: Missing customer location returns explicit failure reason rather than Null Island math."""
    customer = Customer(
        id=uuid.uuid4(),
        name="Unconfigured Outlet",
        location=None,
        geofence_radius_m=100.0,
    )
    session = AsyncMock()

    res = await verify_device_against_customer(
        customer=customer,
        session=session,
        device_lat=12.9716,
        device_lng=77.5946,
    )

    assert res.is_valid is False
    assert res.failure_reason == "Customer location not configured"
    assert res.distance_m == 0.0


def test_checkout_request_schema_supports_notes():
    """APP-ATT-012: CheckOutRequest accepts notes field."""
    req = CheckOutRequest(
        latitude=12.9716,
        longitude=77.5946,
        accuracy_m=10.0,
        captured_at=datetime.now(tz=timezone.utc),
        idempotency_key=str(uuid.uuid4()),
        notes="Order captured and payment collected successfully",
    )
    assert req.notes == "Order captured and payment collected successfully"


@pytest.mark.asyncio
async def test_checkout_negative_duration_rejected():
    """APP-ATT-014: Check-out timestamp earlier than check-in timestamp raises INVALID_VISIT_DURATION."""
    now = datetime.now(tz=timezone.utc)
    visit = Visit(
        id=uuid.uuid4(),
        customer_id=uuid.uuid4(),
        employee_id=uuid.uuid4(),
        scheduled_at=now,
        status=VisitStatus.IN_PROGRESS,
        check_in_at=now,
    )

    # Attempt check out 10 minutes BEFORE check-in
    earlier_time = now - timedelta(minutes=10)
    data = CheckOutRequest(
        latitude=12.9716,
        longitude=77.5946,
        accuracy_m=10.0,
        captured_at=earlier_time,
        idempotency_key=str(uuid.uuid4()),
    )

    session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    session.execute.return_value = mock_result

    user = MagicMock()
    user.id = uuid.uuid4()

    with pytest.raises(BaseAPIException) as exc_info:
        with patch("app.services.visit_service.get_visit_for_user", return_value=visit):
            await check_out(visit.id, data, user, session)

    assert exc_info.value.status_code == 422
    assert exc_info.value.error_code == "INVALID_VISIT_DURATION"
    assert "earlier than check-in" in exc_info.value.detail
