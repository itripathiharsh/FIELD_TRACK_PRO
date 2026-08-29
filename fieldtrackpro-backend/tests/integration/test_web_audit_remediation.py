import uuid
import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.employee import Employee
from app.models.fos_mapping import FOSEmployeeMapping
from app.models.monthly_reporting_period import MonthlyReportingPeriod, MonthlyPeriodStatus
from app.models.notification import Notification, NotificationType
from app.models.user import Role, User
from app.services.report_service import report_service
from tests.conftest import admin_headers, employee_headers, requires_db


@requires_db
@pytest.mark.asyncio
async def test_fos_mapping_create_and_update(
    client: AsyncClient,
):
    """WEB-GLOBAL-036: Verify FOS mapping create and update without NameError."""
    async with AsyncSessionLocal() as session:
        emp_res = await session.execute(select(Employee).limit(1))
        emp = emp_res.scalar_one_or_none()
        if not emp:
            pytest.skip("No employees in test DB")
        emp_id = emp.id

    # 1. Create mapping
    payload = {
        "raw_fos_name": "ROHIT SHARMA",
        "employee_id": str(emp_id),
    }
    resp = await client.post("/api/v1/imports/fos-mappings", json=payload, headers=admin_headers())
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["raw_fos_name"] == "ROHIT SHARMA"
    assert data["employee_id"] == str(emp_id)

    # 2. Update mapping
    payload_update = {
        "raw_fos_name": "rohit sharma",
        "employee_id": str(emp_id),
    }
    resp2 = await client.post("/api/v1/imports/fos-mappings", json=payload_update, headers=admin_headers())
    assert resp2.status_code == 200, resp2.text
    data2 = resp2.json()
    assert data2["id"] == data["id"]


@requires_db
@pytest.mark.asyncio
async def test_monthly_period_finalization_status():
    """WEB-GLOBAL-005: Finalized period returns is_finalized=True in BusinessBIDashboard."""
    async with AsyncSessionLocal() as session:
        period_res = await session.execute(
            select(MonthlyReportingPeriod).where(
                MonthlyReportingPeriod.period_year == 2026,
                MonthlyReportingPeriod.period_month == 1,
            )
        )
        period = period_res.scalar_one_or_none()
        if not period:
            period = MonthlyReportingPeriod(
                period_year=2026,
                period_month=1,
                period_name="January 2026",
                status=MonthlyPeriodStatus.FINALIZED,
                snapshot_count=10,
                total_outlets=5,
            )
            session.add(period)
        else:
            period.status = MonthlyPeriodStatus.FINALIZED
        await session.commit()

        dash = await report_service.get_business_bi_dashboard(
            session=session,
            month="2026-01",
        )
        assert dash.is_finalized is True

        dash_open = await report_service.get_business_bi_dashboard(
            session=session,
            month="2026-02",
        )
        assert dash_open.is_finalized is False


@pytest.mark.asyncio
async def test_auth_error_envelope_standardization(
    client: AsyncClient,
):
    """WEB-GLOBAL-027 / 028 / 029: Authentication errors return standardized string codes and envelope."""
    resp = await client.get("/api/v1/auth/me", headers={"Authorization": "Bearer invalid.token.here"})
    assert resp.status_code == 401
    body = resp.json()
    assert "error" in body
    assert body["error"]["code"] == "UNAUTHORIZED"
    assert isinstance(body["error"]["message"], str)


@requires_db
@pytest.mark.asyncio
async def test_notification_ownership_validation(
    client: AsyncClient,
):
    """WEB-GLOBAL-034: User cannot mark another user's notification as read."""
    async with AsyncSessionLocal() as session:
        admin_u = (await session.execute(select(User).where(User.role == Role.ADMIN).limit(1))).scalar_one_or_none()
        emp_u = (await session.execute(select(User).where(User.role == Role.EMPLOYEE).limit(1))).scalar_one_or_none()
        if not admin_u or not emp_u:
            pytest.skip("Users not populated in DB")

        notif = Notification(
            user_id=admin_u.id,
            type=NotificationType.NEW_VISIT,
            message="Admin alert",
        )
        session.add(notif)
        await session.commit()
        await session.refresh(notif)
        notif_id = notif.id

    # Employee tries to mark admin's notification as read
    resp = await client.patch(
        f"/api/v1/notifications/{notif_id}/read",
        headers=employee_headers(str(emp_u.id)),
    )
    assert resp.status_code == 403, resp.text
    body = resp.json()
    assert body["error"]["code"] == "FORBIDDEN"

    # Non-existent notification returns 404
    fake_id = uuid.uuid4()
    resp_missing = await client.patch(
        f"/api/v1/notifications/{fake_id}/read",
        headers=employee_headers(str(emp_u.id)),
    )
    assert resp_missing.status_code == 404
    assert resp_missing.json()["error"]["code"] == "RESOURCE_NOT_FOUND"


@pytest.mark.asyncio
async def test_requirement_form_missing_visit_validation(
    client: AsyncClient,
):
    """WEB-GLOBAL-035: Missing visit for requirement form returns 404."""
    fake_visit_id = uuid.uuid4()
    resp = await client.get(
        f"/api/v1/visits/{fake_visit_id}/requirement-form",
        headers=admin_headers(),
    )
    assert resp.status_code == 404
    body = resp.json()
    assert body["error"]["code"] == "RESOURCE_NOT_FOUND"


@requires_db
@pytest.mark.asyncio
async def test_report_routes_alignment(
    client: AsyncClient,
):
    """WEB-GLOBAL-001/002 & 003/004: Report routes and exports work correctly."""
    # Employee Master Report
    resp_emp = await client.get("/api/v1/reports/employees-master", headers=admin_headers())
    assert resp_emp.status_code == 200

    resp_emp_exp = await client.get("/api/v1/reports/employees-master/export", headers=admin_headers())
    assert resp_emp_exp.status_code == 200

    # Visits Detailed Report
    resp_vis = await client.get("/api/v1/reports/visits-detailed", headers=admin_headers())
    assert resp_vis.status_code == 200

    resp_vis_exp = await client.get("/api/v1/reports/visits-detailed/export", headers=admin_headers())
    assert resp_vis_exp.status_code == 200


@requires_db
@pytest.mark.asyncio
async def test_form_submission_http_201_created(
    client: AsyncClient,
):
    """WEB-GLOBAL-037: Form submission creation returns HTTP 201 Created."""
    # First create a template, publish it, create visit, then submit
    async with AsyncSessionLocal() as session:
        emp_res = await session.execute(select(Employee).limit(1))
        emp = emp_res.scalar_one_or_none()
        if not emp:
            pytest.skip("No employee in DB")

    t_resp = await client.post(
        "/api/v1/form-templates",
        json={"name": "WEB-GLOBAL-037 Template", "description": "Testing 201 status"},
        headers=admin_headers(),
    )
    if t_resp.status_code != 201:
        pytest.skip("Form template creation failed")
    t_id = t_resp.json()["id"]

    await client.post(f"/api/v1/form-templates/{t_id}/publish", headers=admin_headers())

    # Create submission
    sub_resp = await client.post(
        "/api/v1/form-submissions",
        json={"form_id": t_id, "visit_id": None, "answers": []},
        headers=admin_headers(),
    )
    assert sub_resp.status_code == 201, f"Expected 201 Created, got {sub_resp.status_code}: {sub_resp.text}"
    assert sub_resp.json()["id"] is not None

