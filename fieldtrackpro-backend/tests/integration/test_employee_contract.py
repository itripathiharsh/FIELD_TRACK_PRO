"""
Integration: the employee list contract.

FT-073. Found during the final forensic pass by diffing the frontend `Employee`
type against the OpenAPI schemas.

`GET /employees` declared `EmployeeRead`, which has no `user` object, while the
admin Employees page renders `emp.user?.email`, `emp.user?.mobile_number` and
`emp.user?.role`. Optional chaining meant this compiled and never threw - the
Role and Contact Info columns were simply blank forever, with no error anywhere.

This is the same failure mode as FT-012 (customer coordinates omitted from the
read model): the UI is not wrong, the response model is incomplete.

The repository already eager-loads the relationship via `list_with_user()`, so
the data was fetched and then discarded during serialisation. No extra query is
introduced by returning it.
"""
from __future__ import annotations

import pytest
from httpx import AsyncClient

from tests.integration.conftest import requires_db

pytestmark = [requires_db, pytest.mark.integration, pytest.mark.asyncio]


async def test_employee_list_includes_linked_user_account(
    client: AsyncClient, admin_headers, seeded_world
):
    """
    FT-073: the list must carry the account the UI displays, so the Role and
    Contact columns are populated.
    """
    resp = await client.get("/api/v1/employees", headers=admin_headers)
    assert resp.status_code == 200, resp.text

    employees = resp.json()
    assert employees, "fixture employees should be listed"

    target = next(
        (e for e in employees if e["id"] == seeded_world["employee_id"]), None
    )
    assert target is not None, "the seeded employee should appear in the list"

    assert "user" in target, (
        "FT-073: GET /employees omits the linked user, so the admin table's "
        "Role and Contact Info columns can never be populated"
    )
    assert target["user"]["email"] == seeded_world["employee_email"]
    assert target["user"]["role"] == "EMPLOYEE"
    assert "mobile_number" in target["user"]


async def test_employee_list_and_detail_agree(
    client: AsyncClient, admin_headers, seeded_world
):
    """A record must not change shape depending on how it was fetched."""
    listed = (await client.get("/api/v1/employees", headers=admin_headers)).json()
    target = next(e for e in listed if e["id"] == seeded_world["employee_id"])

    detail = await client.get(
        f"/api/v1/employees/{seeded_world['employee_id']}", headers=admin_headers
    )
    assert detail.status_code == 200, detail.text

    assert set(target.keys()) == set(detail.json().keys()), (
        "FT-073: list and detail return different field sets for the same entity"
    )


async def test_employee_me_still_returns_the_account(
    client: AsyncClient, employee_headers, seeded_world
):
    """Regression guard: /employees/me must keep its embedded account."""
    resp = await client.get("/api/v1/employees/me", headers=employee_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["user"]["email"] == seeded_world["employee_email"]


async def test_employee_cannot_get_another_employee_by_id(
    client: AsyncClient, employee_headers, seeded_world
):
    """
    P0 (Authentication & Roles): GET /employees/{id} previously allowed any
    authenticated employee to fetch any other employee's full profile,
    including the linked account's email/mobile/role, with no ownership
    check. It must be admin-only, matching GET /employees.
    """
    resp = await client.get(
        f"/api/v1/employees/{seeded_world['other_employee_id']}",
        headers=employee_headers,
    )
    assert resp.status_code == 403, resp.text


async def test_employee_cannot_get_own_employee_by_id(
    client: AsyncClient, employee_headers, seeded_world
):
    """Employees must use /employees/me; the by-id route is admin-only even for self."""
    resp = await client.get(
        f"/api/v1/employees/{seeded_world['employee_id']}",
        headers=employee_headers,
    )
    assert resp.status_code == 403, resp.text


async def test_unauthenticated_cannot_get_employee_by_id(
    client: AsyncClient, seeded_world
):
    resp = await client.get(f"/api/v1/employees/{seeded_world['employee_id']}")
    assert resp.status_code == 401, resp.text


async def test_admin_can_still_get_employee_by_id(
    client: AsyncClient, admin_headers, seeded_world
):
    """Regression guard: the AdminOnly fix must not break admin access."""
    resp = await client.get(
        f"/api/v1/employees/{seeded_world['employee_id']}", headers=admin_headers
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["id"] == str(seeded_world["employee_id"])
