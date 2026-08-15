"""
Integration tests for the Visit-based Form workflow fix:
Form Template -> assigned to Visit -> Employee fills Form -> Submission
belongs to that Visit.

Covers:
  - Visit.required_form_id: creation (single + bulk), validation, PATCH
    assign/change/clear
  - GET /form-templates?status=PUBLISHED as the assignable-options source
  - delete_template blocked while a visit still requires it
  - FormTemplateListRead.visit_count
  - Submission context enrichment (employee full name, outlet, visit date)
  - Authorization: only admin can assign/change a visit's required form
"""
from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

from tests.integration.conftest import create_visit, requires_db

pytestmark = [requires_db, pytest.mark.integration, pytest.mark.asyncio]


async def _create_form(client: AsyncClient, headers: dict, name: str = "__itest__VFWForm", **extra) -> dict:
    resp = await client.post("/api/v1/form-templates", json={"name": name, **extra}, headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _build_and_publish_form(client: AsyncClient, admin_headers, created_forms, name: str = "__itest__VFWForm") -> dict:
    form = await _create_form(client, admin_headers, name=name)
    created_forms.append(form["id"])
    section_resp = await client.post(
        f"/api/v1/form-templates/{form['id']}/sections", json={"title": "Section A"}, headers=admin_headers
    )
    assert section_resp.status_code == 200, section_resp.text
    section = section_resp.json()
    question_resp = await client.post(
        f"/api/v1/form-templates/{form['id']}/questions",
        json={"section_id": section["id"], "question_text": "Q1", "question_type": "SHORT_TEXT"},
        headers=admin_headers,
    )
    assert question_resp.status_code == 200, question_resp.text
    question = question_resp.json()
    publish_resp = await client.post(f"/api/v1/form-templates/{form['id']}/publish", headers=admin_headers)
    assert publish_resp.status_code == 200, publish_resp.text
    return {"form_id": form["id"], "question_id": question["id"], "published": publish_resp.json()}


# -- Scenario A: admin creates + publishes template -> selectable ----------------

async def test_published_template_is_selectable(client: AsyncClient, admin_headers, created_forms):
    setup = await _build_and_publish_form(client, admin_headers, created_forms)
    resp = await client.get("/api/v1/form-templates", params={"status": "PUBLISHED"}, headers=admin_headers)
    assert resp.status_code == 200
    assert any(t["id"] == setup["form_id"] for t in resp.json())


async def test_draft_template_is_not_in_published_list(client: AsyncClient, admin_headers, created_forms):
    form = await _create_form(client, admin_headers)
    created_forms.append(form["id"])
    resp = await client.get("/api/v1/form-templates", params={"status": "PUBLISHED"}, headers=admin_headers)
    assert not any(t["id"] == form["id"] for t in resp.json())


# -- Scenario B: admin creates visit with a required form ------------------------

async def test_visit_creation_stores_required_form(
    client: AsyncClient, admin_headers, seeded_world, created_forms, created_visits
):
    setup = await _build_and_publish_form(client, admin_headers, created_forms)
    visit_id = await create_visit(
        client, admin_headers, seeded_world["customer_id"], seeded_world["employee_id"], created_visits,
        required_form_id=setup["form_id"],
    )
    resp = await client.get(f"/api/v1/visits/{visit_id}", headers=admin_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["required_form_id"] == setup["form_id"]
    assert body["required_form_name"] == "__itest__VFWForm"
    assert body["required_form_status"] == "PUBLISHED"


async def test_visit_creation_rejects_draft_template(
    client: AsyncClient, admin_headers, seeded_world, created_forms, created_visits
):
    form = await _create_form(client, admin_headers)
    created_forms.append(form["id"])
    resp = await client.post(
        "/api/v1/visits",
        json={
            "customer_id": seeded_world["customer_id"], "employee_id": seeded_world["employee_id"],
            "scheduled_at": "2026-08-20T10:00:00Z", "required_form_id": form["id"],
        },
        headers=admin_headers,
    )
    assert resp.status_code == 400, resp.text
    assert resp.json()["error"]["code"] == "FORM_NOT_PUBLISHED"


async def test_visit_creation_rejects_archived_template(
    client: AsyncClient, admin_headers, seeded_world, created_forms, created_visits
):
    setup = await _build_and_publish_form(client, admin_headers, created_forms)
    archive_resp = await client.post(f"/api/v1/form-templates/{setup['form_id']}/archive", headers=admin_headers)
    assert archive_resp.status_code == 200
    resp = await client.post(
        "/api/v1/visits",
        json={
            "customer_id": seeded_world["customer_id"], "employee_id": seeded_world["employee_id"],
            "scheduled_at": "2026-08-20T10:00:00Z", "required_form_id": setup["form_id"],
        },
        headers=admin_headers,
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "FORM_NOT_PUBLISHED"


async def test_visit_creation_rejects_unknown_form_id(
    client: AsyncClient, admin_headers, seeded_world, created_visits
):
    resp = await client.post(
        "/api/v1/visits",
        json={
            "customer_id": seeded_world["customer_id"], "employee_id": seeded_world["employee_id"],
            "scheduled_at": "2026-08-20T10:00:00Z", "required_form_id": str(uuid.uuid4()),
        },
        headers=admin_headers,
    )
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "FORM_NOT_FOUND"


# -- Scenario E: no form required ------------------------------------------------

async def test_visit_with_no_required_form(
    client: AsyncClient, admin_headers, seeded_world, created_visits
):
    visit_id = await create_visit(
        client, admin_headers, seeded_world["customer_id"], seeded_world["employee_id"], created_visits,
    )
    resp = await client.get(f"/api/v1/visits/{visit_id}", headers=admin_headers)
    body = resp.json()
    assert body["required_form_id"] is None
    assert body["required_form_name"] is None
    assert body["required_form_status"] is None


# -- Bulk creation ----------------------------------------------------------------

async def test_bulk_visit_creation_applies_required_form_to_all(
    client: AsyncClient, admin_headers, seeded_world, created_customers, created_forms, created_visits
):
    setup = await _build_and_publish_form(client, admin_headers, created_forms, name="__itest__BulkForm")
    cust_resp = await client.post(
        "/api/v1/customers",
        json={
            "name": "__itest__Bulk Outlet 2", "contact_number": "+919800000099",
            "address": "1 Bulk Rd", "location": {"latitude": 12.97, "longitude": 77.59},
        },
        headers=admin_headers,
    )
    assert cust_resp.status_code == 201, cust_resp.text
    second_customer_id = cust_resp.json()["id"]
    created_customers.append(second_customer_id)

    resp = await client.post(
        "/api/v1/visits/bulk",
        json={
            "customer_ids": [seeded_world["customer_id"], second_customer_id],
            "employee_id": seeded_world["employee_id"],
            "scheduled_at": "2026-08-20T10:00:00Z",
            "required_form_id": setup["form_id"],
        },
        headers=admin_headers,
    )
    assert resp.status_code == 201, resp.text
    visits = resp.json()
    assert len(visits) == 2
    for v in visits:
        created_visits.append(v["id"])
        assert v["required_form_id"] == setup["form_id"]


# -- PATCH required-form: assign/change/clear -------------------------------------

async def test_admin_can_assign_change_and_clear_required_form(
    client: AsyncClient, admin_headers, seeded_world, created_forms, created_visits
):
    setup1 = await _build_and_publish_form(client, admin_headers, created_forms, name="__itest__PatchFormA")
    setup2 = await _build_and_publish_form(client, admin_headers, created_forms, name="__itest__PatchFormB")
    visit_id = await create_visit(
        client, admin_headers, seeded_world["customer_id"], seeded_world["employee_id"], created_visits,
    )

    assign = await client.patch(
        f"/api/v1/visits/{visit_id}/required-form", json={"required_form_id": setup1["form_id"]}, headers=admin_headers
    )
    assert assign.status_code == 200, assign.text
    assert assign.json()["required_form_id"] == setup1["form_id"]

    change = await client.patch(
        f"/api/v1/visits/{visit_id}/required-form", json={"required_form_id": setup2["form_id"]}, headers=admin_headers
    )
    assert change.status_code == 200
    assert change.json()["required_form_id"] == setup2["form_id"]

    clear = await client.patch(
        f"/api/v1/visits/{visit_id}/required-form", json={"required_form_id": None}, headers=admin_headers
    )
    assert clear.status_code == 200
    assert clear.json()["required_form_id"] is None


async def test_employee_cannot_assign_required_form(
    client: AsyncClient, admin_headers, employee_headers, seeded_world, created_forms, created_visits
):
    setup = await _build_and_publish_form(client, admin_headers, created_forms)
    visit_id = await create_visit(
        client, admin_headers, seeded_world["customer_id"], seeded_world["employee_id"], created_visits,
    )
    resp = await client.patch(
        f"/api/v1/visits/{visit_id}/required-form", json={"required_form_id": setup["form_id"]}, headers=employee_headers
    )
    assert resp.status_code == 403


# -- delete_template blocked while required by a visit ----------------------------

async def test_cannot_delete_template_required_by_a_visit(
    client: AsyncClient, admin_headers, seeded_world, created_forms, created_visits
):
    setup = await _build_and_publish_form(client, admin_headers, created_forms)
    await create_visit(
        client, admin_headers, seeded_world["customer_id"], seeded_world["employee_id"], created_visits,
        required_form_id=setup["form_id"],
    )
    resp = await client.delete(f"/api/v1/form-templates/{setup['form_id']}", headers=admin_headers)
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "FORM_REQUIRED_BY_VISITS"


# -- visit_count metric ------------------------------------------------------------

async def test_template_list_reports_visit_count(
    client: AsyncClient, admin_headers, seeded_world, created_forms, created_visits
):
    setup = await _build_and_publish_form(client, admin_headers, created_forms, name="__itest__CountForm")
    await create_visit(
        client, admin_headers, seeded_world["customer_id"], seeded_world["employee_id"], created_visits,
        required_form_id=setup["form_id"],
    )
    resp = await client.get("/api/v1/form-templates", params={"status": "PUBLISHED"}, headers=admin_headers)
    template = next(t for t in resp.json() if t["id"] == setup["form_id"])
    assert template["visit_count"] == 1


# -- Scenario C/D: submission context (employee/outlet/visit) ---------------------

async def test_submission_detail_shows_full_context(
    client: AsyncClient, admin_headers, employee_headers, seeded_world, created_forms, created_visits
):
    setup = await _build_and_publish_form(client, admin_headers, created_forms, name="__itest__ContextForm")
    visit_id = await create_visit(
        client, admin_headers, seeded_world["customer_id"], seeded_world["employee_id"], created_visits,
        required_form_id=setup["form_id"],
    )

    submit = await client.post(
        "/api/v1/form-submissions",
        json={"form_id": setup["form_id"], "visit_id": visit_id, "answers": [{"question_id": setup["question_id"], "answer_value": "Fine"}]},
        headers=employee_headers,
    )
    assert submit.status_code == 200, submit.text
    submission_id = submit.json()["id"]

    detail = await client.get(f"/api/v1/form-submissions/{submission_id}", headers=admin_headers)
    assert detail.status_code == 200, detail.text
    body = detail.json()
    assert body["form_name"] == "__itest__ContextForm"
    assert body["visit_id"] == visit_id
    assert body["employee_name"] == "__itest__ Primary Rep"
    assert body["customer_name"] == "__itest__Customer"
    assert body["visit_scheduled_at"] is not None


async def test_submission_list_shows_full_context(
    client: AsyncClient, admin_headers, employee_headers, seeded_world, created_forms, created_visits
):
    """Regression coverage: list_submissions previously returned form_name/
    employee_name as null unconditionally (never enriched)."""
    setup = await _build_and_publish_form(client, admin_headers, created_forms, name="__itest__ListContextForm")
    visit_id = await create_visit(
        client, admin_headers, seeded_world["customer_id"], seeded_world["employee_id"], created_visits,
        required_form_id=setup["form_id"],
    )
    submit = await client.post(
        "/api/v1/form-submissions",
        json={"form_id": setup["form_id"], "visit_id": visit_id, "answers": []},
        headers=employee_headers,
    )
    assert submit.status_code == 200

    resp = await client.get("/api/v1/form-submissions", params={"form_id": setup["form_id"]}, headers=admin_headers)
    assert resp.status_code == 200
    row = next(s for s in resp.json() if s["visit_id"] == visit_id)
    assert row["form_name"] == "__itest__ListContextForm"
    assert row["employee_name"] == "__itest__ Primary Rep"
    assert row["customer_name"] == "__itest__Customer"


# -- Authorization matrix ----------------------------------------------------------

async def test_employee_cannot_create_or_publish_templates(client: AsyncClient, employee_headers):
    create_resp = await client.post("/api/v1/form-templates", json={"name": "x"}, headers=employee_headers)
    assert create_resp.status_code == 403

    publish_resp = await client.post(f"/api/v1/form-templates/{uuid.uuid4()}/publish", headers=employee_headers)
    assert publish_resp.status_code == 403


async def test_employee_cannot_bulk_assign_required_form(
    client: AsyncClient, admin_headers, employee_headers, seeded_world, created_forms
):
    setup = await _build_and_publish_form(client, admin_headers, created_forms)
    resp = await client.post(
        "/api/v1/visits/bulk",
        json={
            "customer_ids": [seeded_world["customer_id"]], "employee_id": seeded_world["employee_id"],
            "scheduled_at": "2026-08-20T10:00:00Z", "required_form_id": setup["form_id"],
        },
        headers=employee_headers,
    )
    assert resp.status_code == 403
