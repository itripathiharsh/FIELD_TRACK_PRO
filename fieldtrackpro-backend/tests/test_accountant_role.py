"""ACCOUNTANT role (policy approved 19-Nov-2026).

* READ: every GET an Admin may make, except the import credentials download and the security audit log.
* WRITE: ONLY the explicit allow-list (field-staff profile edit and territory / area assignment, territories
  and areas create/edit, customers, outlet mapping, outlet verification). Everything else - user / role /
  password management, deletes, payments, visits, forms, imports, month close - is refused.
* Field-staff only: an accountant can never edit an Admin / Super Admin / Accountant profile.
* Super-Admin-only and employee-only (field app) routes never admit an accountant.
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
from app.core.deps.auth import _ACCOUNTANT_READ_DENY, _ACCOUNTANT_WRITE_ALLOW, accountant_may
from app.core.security import create_access_token, hash_password
from app.database import AsyncSessionLocal
from app.main import app
from app.models.employee import Employee
from app.models.security_audit import SecurityAuditLog
from app.models.user import Role, User
from tests.conftest import admin_headers, employee_headers, requires_db

P = settings.api_v1_prefix.rstrip("/")


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


def _admitted():
    """(method, path) -> admitted for an accountant, from the real route table and the real policy."""
    res = {}
    for r in _flat(app.routes):
        path = r.path.removeprefix(P)
        checks = _role_checks(r.dependant, [])
        for m in r.methods:
            if checks:
                res[(m, path)] = all(accountant_may(m, path, c) for c in checks)
            else:
                res[(m, path)] = accountant_may(m, path, None)
    return res


def test_accountant_writes_are_exactly_the_approved_list():
    adm = _admitted()
    role_checked_writes = set()
    for r in _flat(app.routes):
        path = r.path.removeprefix(P)
        if _role_checks(r.dependant, []):
            for m in r.methods - {"GET", "HEAD"}:
                if adm[(m, path)]:
                    role_checked_writes.add((m, path))
    assert role_checked_writes == set(_ACCOUNTANT_WRITE_ALLOW), role_checked_writes ^ set(_ACCOUNTANT_WRITE_ALLOW)
    assert set(_ACCOUNTANT_WRITE_ALLOW) <= set(adm), "every allow-listed write must exist"


def test_never_admitted_routes():
    adm = _admitted()
    for key in _ACCOUNTANT_READ_DENY:
        assert adm.get(key) is False, key
    must_refuse = [
        ("POST", "/users"), ("PATCH", "/users/{user_id}/role"), ("PATCH", "/users/{user_id}/activate"),
        ("PATCH", "/users/{user_id}/deactivate"), ("POST", "/employees"), ("POST", "/employees/register"),
        ("POST", "/employees/{employee_id}/reset-password"), ("DELETE", "/territories/{territory_id}"),
        ("DELETE", "/areas/{area_id}"), ("POST", "/outlet-mapping/import/apply"), ("POST", "/outlet-mapping/import/revert"),
        ("POST", "/reports/monthly-periods/{period_id}/finalize"), ("POST", "/reports/monthly-periods/{period_id}/reopen"),
        ("GET", "/dashboard/my-day"), ("POST", "/devices/register"), ("DELETE", "/auth/me"),
    ]
    for key in must_refuse:
        assert key in adm, key
        assert adm[key] is False, key


def test_reads_mirror_admin_reads():
    adm = _admitted()
    for r in _flat(app.routes):
        path = r.path.removeprefix(P)
        checks = _role_checks(r.dependant, [])
        if "GET" in r.methods and checks and all(Role.ADMIN in c for c in checks) and ("GET", path) not in _ACCOUNTANT_READ_DENY:
            assert adm[("GET", path)] is True, path


# ---------------------------------------------------------------------------------------------------------
# HTTP behaviour with real accounts
# ---------------------------------------------------------------------------------------------------------

async def _make(role: Role, name: str):
    uid = uuid.uuid4()
    eid = uuid.uuid4()
    async with AsyncSessionLocal() as s:
        s.add(User(id=uid, email=f"acct_{uid.hex[:10]}@fieldtrack.test", password_hash=hash_password("x" * 16),
                   role=role, is_active=True))
        await s.flush()
        s.add(Employee(id=eid, user_id=uid, full_name=name, must_change_password=False))
        await s.commit()
    return uid, eid


async def _drop(*uids):
    async with AsyncSessionLocal() as s:
        await s.execute(delete(Employee).where(Employee.user_id.in_(uids)))
        await s.execute(delete(User).where(User.id.in_(uids)))
        await s.commit()


@pytest_asyncio.fixture
async def accountant():
    uid, eid = await _make(Role.ACCOUNTANT, "Acct Test")
    token = create_access_token(str(uid), Role.ACCOUNTANT.value, token_version=0)
    yield {"id": uid, "h": {"Authorization": f"Bearer {token}"}}
    await _drop(uid)


@pytest_asyncio.fixture
async def http():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@requires_db
@pytest.mark.asyncio
async def test_accountant_reads_admin_pages(http, accountant):
    h = accountant["h"]
    for path, params in [
        ("/reports/business-summary", {"month": "FY2025-26"}), ("/reports/employees", {}), ("/reports/visits-detailed", {}),
        ("/collections/overview", {"limit": "5"}), ("/dashboard/summary", {}), ("/dashboard/history-periods", {}),
        ("/employees", {"limit": "5"}), ("/customers", {"limit": "5"}), ("/territories", {}), ("/areas", {}),
        ("/payments/queue", {}), ("/outlet-mapping/queues", {}), ("/customers/outlet-proofs", {}),
        ("/location-proposals", {}), ("/organization", {}), ("/auth/me", {}), ("/employees/me", {}),
    ]:
        r = await http.get(P + path, params=params, headers=h)
        assert r.status_code == 200, (path, r.status_code, r.text[:200])
    # global scope: the customer list is not limited to an (empty) employee scope
    r = await http.get(P + "/customers", params={"limit": "5"}, headers=h)
    r_admin = await http.get(P + "/customers", params={"limit": "5"}, headers=admin_headers())
    assert r.headers.get("X-Total-Count") == r_admin.headers.get("X-Total-Count")


@requires_db
@pytest.mark.asyncio
async def test_accountant_refused_writes_and_hidden_reads(http, accountant):
    h = accountant["h"]
    rid = str(uuid.uuid4())
    for method, path in [
        ("POST", "/employees/register"), ("POST", f"/employees/{rid}/reset-password"), ("POST", "/users"),
        ("PATCH", f"/users/{rid}/role"), ("PATCH", f"/users/{rid}/deactivate"),
        ("DELETE", f"/territories/{rid}"), ("DELETE", f"/areas/{rid}"),
        ("POST", f"/reports/monthly-periods/{rid}/finalize"), ("POST", "/outlet-mapping/import/apply"),
        ("POST", "/customers/prospect"), ("POST", f"/visits/{rid}/check-in"), ("DELETE", f"/media/{rid}"),
        ("POST", "/devices/register"), ("GET", "/dashboard/my-day"), ("GET", "/security-audit-logs"),
        ("GET", f"/imports/{rid}/credentials.xlsx"),
    ]:
        r = await http.request(method, P + path, headers=h, json={})
        assert r.status_code == 403, (method, path, r.status_code, r.text[:200])


@requires_db
@pytest.mark.asyncio
async def test_accountant_edits_field_staff_but_never_admin_profiles(http, accountant):
    h = accountant["h"]
    staff_uid, staff_eid = await _make(Role.EMPLOYEE, "Field Staff Edit Target")
    admin_uid, admin_eid = await _make(Role.ADMIN, "Admin Edit Target")
    try:
        r = await http.patch(P + f"/employees/{staff_eid}", json={"working_profile": "FOS"}, headers=h)
        assert r.status_code == 200, r.text
        async with AsyncSessionLocal() as s:
            assert (await s.execute(select(Employee.working_profile).where(Employee.id == staff_eid))).scalar_one() == "FOS"
        r = await http.patch(P + f"/employees/{admin_eid}", json={"full_name": "Hijacked"}, headers=h)
        assert r.status_code == 403, r.text
        r = await http.post(P + f"/employees/{admin_eid}/areas", json={"area_id": str(uuid.uuid4())}, headers=h)
        assert r.status_code == 403, r.text
        async with AsyncSessionLocal() as s:
            assert (await s.execute(select(Employee.full_name).where(Employee.id == admin_eid))).scalar_one() == "Admin Edit Target"
    finally:
        await _drop(staff_uid, admin_uid)


@requires_db
@pytest.mark.asyncio
async def test_accountant_creates_and_edits_territories_but_cannot_delete(http, accountant):
    h = accountant["h"]
    name = f"Acct Zone {uuid.uuid4().hex[:6]}"
    r = await http.post(P + "/territories", json={"name": name}, headers=h)
    assert r.status_code in (200, 201), r.text
    tid = r.json()["id"]
    try:
        r = await http.patch(P + f"/territories/{tid}", json={"name": name + " X"}, headers=h)
        assert r.status_code == 200, r.text
        r = await http.delete(P + f"/territories/{tid}", headers=h)
        assert r.status_code == 403, r.text
    finally:
        await http.delete(P + f"/territories/{tid}", headers=admin_headers())


@requires_db
@pytest.mark.asyncio
async def test_admin_and_employee_access_unchanged(http):
    assert (await http.get(P + "/reports/employees", headers=admin_headers())).status_code == 200
    assert (await http.get(P + "/reports/business-summary", headers=admin_headers())).status_code == 200
    assert (await http.get(P + "/reports/business-summary", headers=employee_headers())).status_code == 403
    assert (await http.get(P + "/territories", headers=employee_headers())).status_code == 200
    assert (await http.get(P + "/employees", headers=employee_headers())).status_code == 403


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
