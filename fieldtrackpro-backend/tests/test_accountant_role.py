"""ACCOUNTANT role (19-Nov-2026): web-only, READ-ONLY access to the financial reports and collections.

* Only endpoints that name ACCOUNTANT in their role check admit it, and every one of them is a GET.
* It fails CLOSED: endpoints that only require "a signed-in user" (visits, media, signatures, form
  submissions, ...) answer 403 to an accountant, so code that treats "not an EMPLOYEE" as "an admin"
  can never be reached by it. A short self-service list (own profile, own password, own notifications)
  stays open.
* Only a Super Admin may create an ACCOUNTANT.
"""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from fastapi.routing import APIRoute
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from app.config import settings
from app.core.security import create_access_token, hash_password
from app.database import AsyncSessionLocal
from app.main import app
from app.models.employee import Employee
from app.models.security_audit import SecurityAuditLog
from app.models.user import Role, User
from tests.conftest import admin_headers, employee_headers, requires_db

P = settings.api_v1_prefix.rstrip("/")

#: The complete, reviewed list of what an accountant can call by role (all read-only).
EXPECTED_ACCOUNTANT_ROUTES = {
    "/areas", "/brands", "/territories",
    "/collections/overview", "/collections/overview/export",
    "/dashboard/history-periods",
    "/reports/business-summary", "/reports/business-summary/export",
    "/reports/collections", "/reports/collections/export",
    "/reports/monthly-periods", "/reports/monthly-periods/export",
    "/reports/monthly-periods/{period_id}/review",
    "/reports/outlets", "/reports/outlets/export",
    "/reports/outstanding", "/reports/outstanding/export",
    "/reports/overview", "/reports/overview/export",
}


def _flat(routes):
    for r in routes:
        if type(r).__name__ == "_IncludedRouter":
            yield from _flat(r.original_router.routes)
        elif isinstance(r, APIRoute):
            yield r
        elif hasattr(r, "routes"):
            yield from _flat(r.routes)


def _role_checks(dep, out):
    for d in dep.dependencies:
        allowed = getattr(d.call, "allowed_roles", None)
        if allowed is not None:
            out.append(allowed)
        _role_checks(d, out)
    return out


def test_only_reviewed_read_only_routes_admit_the_accountant():
    admitted = {}
    for r in _flat(app.routes):
        checks = _role_checks(r.dependant, [])
        if checks and all(Role.ACCOUNTANT in c for c in checks):
            admitted[r.path.removeprefix(P)] = r.methods
    assert set(admitted) == EXPECTED_ACCOUNTANT_ROUTES
    assert all(m == {"GET"} for m in admitted.values()), admitted


# ---------------------------------------------------------------------------------------------------------
# HTTP behaviour with a real accountant account
# ---------------------------------------------------------------------------------------------------------

@pytest_asyncio.fixture
async def accountant():
    uid = uuid.uuid4()
    async with AsyncSessionLocal() as s:
        s.add(User(id=uid, email=f"acct_{uid.hex[:10]}@fieldtrack.test", password_hash=hash_password("x" * 16),
                   role=Role.ACCOUNTANT, is_active=True))
        await s.flush()
        s.add(Employee(id=uuid.uuid4(), user_id=uid, full_name="Acct Test", must_change_password=False))
        await s.commit()
    token = create_access_token(str(uid), Role.ACCOUNTANT.value, token_version=0)
    yield {"id": uid, "h": {"Authorization": f"Bearer {token}"}}
    async with AsyncSessionLocal() as s:
        await s.execute(delete(Employee).where(Employee.user_id == uid))
        await s.execute(delete(User).where(User.id == uid))
        await s.commit()


@pytest_asyncio.fixture
async def http():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@requires_db
@pytest.mark.asyncio
async def test_accountant_reads_financial_reports(http, accountant):
    h = accountant["h"]
    for path, params in [
        ("/reports/business-summary", {"month": "FY2025-26"}),
        ("/reports/overview", {}),
        ("/reports/outstanding", {}),
        ("/reports/outlets", {"limit": "5"}),
        ("/reports/collections", {}),
        ("/reports/monthly-periods", {}),
        ("/collections/overview", {"limit": "5"}),
        ("/dashboard/history-periods", {}),
        ("/territories", {}), ("/areas", {}), ("/brands", {}),
        ("/auth/me", {}), ("/employees/me", {}),
        ("/notifications/unread-count", {}),
    ]:
        r = await http.get(P + path, params=params, headers=h)
        assert r.status_code == 200, (path, r.status_code, r.text[:200])
    r = await http.get(P + "/reports/business-summary/export", params={"month": "FY2025-26", "format": "xlsx"},
                       headers=h)
    assert r.status_code == 200
    me = (await http.get(P + "/auth/me", headers=h)).json()
    assert me["role"] == "ACCOUNTANT"


@requires_db
@pytest.mark.asyncio
async def test_accountant_is_refused_everything_else(http, accountant):
    h = accountant["h"]
    rid = str(uuid.uuid4())
    refused = [
        # admin areas: staff, user management, operations
        ("GET", "/employees"), ("GET", f"/employees/{rid}"), ("GET", "/customers"),
        ("GET", f"/invoices/{rid}"), ("GET", "/payments/queue"), ("GET", f"/payments/{rid}"), ("GET", "/reports/employees"), ("GET", "/reports/employees-master"),
        ("GET", "/reports/visits-detailed"), ("GET", "/reports/geo-verification"), ("GET", "/reports/productivity"),
        ("GET", f"/reports/customers/{rid}/history"),
        # closing / reopening a month is an admin write
        ("POST", f"/reports/monthly-periods/{rid}/finalize"), ("POST", f"/reports/monthly-periods/{rid}/reopen"),
        # "any signed-in user" endpoints fail closed for the accountant
        ("GET", "/dashboard/summary"), ("GET", "/visits/me/today"), ("GET", "/form-submissions"),
        ("GET", f"/media/{rid}"), ("DELETE", f"/media/{rid}"), ("GET", f"/visits/{rid}/signatures"),
        ("GET", f"/visits/{rid}/geo-logs"), ("POST", "/devices/register"),
        # writes on the lists it can read
        ("POST", "/territories"), ("POST", "/areas"), ("POST", "/brands"),
    ]
    for method, path in refused:
        r = await http.request(method, P + path, headers=h, json={})
        assert r.status_code == 403, (method, path, r.status_code, r.text[:200])


@requires_db
@pytest.mark.asyncio
async def test_admin_and_employee_access_unchanged(http):
    assert (await http.get(P + "/reports/employees", headers=admin_headers())).status_code == 200
    assert (await http.get(P + "/reports/business-summary", headers=admin_headers())).status_code == 200
    assert (await http.get(P + "/reports/business-summary", headers=employee_headers())).status_code == 403
    assert (await http.get(P + "/territories", headers=employee_headers())).status_code == 200


@requires_db
@pytest.mark.asyncio
async def test_only_a_super_admin_may_create_an_accountant():
    from app.exceptions.custom import BaseAPIException
    from app.services import admin_security_service

    async with AsyncSessionLocal() as s:
        admin = (await s.execute(select(User).where(User.role == Role.ADMIN, User.is_active.is_(True)))).scalars().first()
        if admin is None:
            pytest.skip("no active ADMIN in the test database")
        admin_id = admin.id
        with pytest.raises(BaseAPIException) as ei:
            await admin_security_service.assert_may_assign_role_on_create(admin, Role.ACCOUNTANT, s, "127.0.0.1")
        assert ei.value.status_code == 403 and ei.value.error_code == "ROLE_ASSIGNMENT_FORBIDDEN"
        sup = User(id=uuid.uuid4(), role=Role.SUPER_ADMIN, password_hash="-", is_active=True)
        await admin_security_service.assert_may_assign_role_on_create(sup, Role.ACCOUNTANT, s, "127.0.0.1")  # no raise
    async with AsyncSessionLocal() as s:  # the refusal is audited; tidy it (the audit table may be append-only)
        try:
            await s.execute(delete(SecurityAuditLog).where(SecurityAuditLog.actor_user_id == admin_id,
                                                           SecurityAuditLog.new_role == "ACCOUNTANT"))
            await s.commit()
        except Exception:
            pass
