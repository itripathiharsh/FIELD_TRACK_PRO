import pytest
from httpx import AsyncClient
from tests.integration.conftest import requires_db

pytestmark = [requires_db, pytest.mark.integration, pytest.mark.asyncio]

async def test_territory_duplicate_name_conflict(client: AsyncClient, admin_headers, created_territories):
    t_name = "__itest__Duplicate Territory Name"
    # Create first
    resp1 = await client.post("/api/v1/territories", json={"name": t_name}, headers=admin_headers)
    assert resp1.status_code == 201, resp1.text
    created_territories.append(resp1.json()["id"])

    # Attempt duplicate
    resp2 = await client.post("/api/v1/territories", json={"name": t_name}, headers=admin_headers)
    assert resp2.status_code == 409, f"Expected 409 Conflict for duplicate territory name, got {resp2.status_code}: {resp2.text}"
    err = resp2.json()["error"]
    assert err["code"] == "TERRITORY_ALREADY_EXISTS" or err["code"] == "DUPLICATE_RESOURCE" or "already exists" in err["message"].lower()

async def test_employee_duplicate_email_conflict(client: AsyncClient, admin_headers, seeded_world):
    # Attempt to register employee with already existing user email
    resp = await client.post(
        "/api/v1/employees/register",
        json={
            "user": {
                "email": seeded_world["admin_email"],
                "password": "Password123!",
                "mobile_number": "+919888800099",
                "role": "EMPLOYEE",
            },
            "full_name": "__itest__ Duplicate Employee",
            "territory_id": seeded_world["territory_id"],
        },
        headers=admin_headers,
    )
    assert resp.status_code == 409, f"Expected 409 Conflict for duplicate email, got {resp.status_code}: {resp.text}"
    err = resp.json()["error"]
    assert err["code"] in ("USER_ALREADY_EXISTS", "DUPLICATE_RESOURCE", "EMAIL_ALREADY_EXISTS") or "already exists" in err["message"].lower()

async def test_form_submission_creation_returns_201(client: AsyncClient, admin_headers, created_forms, created_visits, seeded_world):
    # WEB-GLOBAL-037: create form submission returns HTTP 201
    f_resp = await client.post(
        "/api/v1/form-templates",
        json={"name": "__itest__ WEB-GLOBAL-037 Template", "description": "Testing 201 Created"},
        headers=admin_headers,
    )
    assert f_resp.status_code == 200, f_resp.text
    form_id = f_resp.json()["id"]
    created_forms.append(form_id)
    await client.post(f"/api/v1/form-templates/{form_id}/publish", headers=admin_headers)

    from tests.integration.conftest import create_visit, iso_in
    visit_id = await create_visit(
        client, admin_headers, seeded_world["customer_id"], seeded_world["employee_id"], created_visits,
        scheduled_at=iso_in(2.0),
    )

    sub_resp = await client.post(
        "/api/v1/form-submissions",
        json={"form_id": form_id, "visit_id": visit_id, "answers": []},
        headers=admin_headers,
    )
    assert sub_resp.status_code == 201, f"Expected 201 Created, got {sub_resp.status_code}: {sub_resp.text}"
    assert sub_resp.json()["id"] is not None

