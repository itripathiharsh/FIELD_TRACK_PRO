"""
Integration: the form template builder (templates, sections, questions,
options, submissions, versioning, duplication).

Covers:
  POST/GET/PATCH/DELETE /api/v1/form-templates[/{id}]
  POST /api/v1/form-templates/{id}/{publish,unpublish,archive,duplicate}
  POST/PATCH/DELETE /api/v1/form-templates/{id}/sections, /sections/{id}
  POST/PATCH/DELETE .../questions, /questions/{id}, /questions/{id}/duplicate
  POST/PATCH/DELETE .../questions/{id}/options, /question-options/{id}
  GET  /api/v1/form-templates/{id}/render
  POST /api/v1/form-submissions[/{id}/submit], GET /form-submissions[/{id}]
"""
from __future__ import annotations

import contextlib
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import event

from tests.integration.conftest import create_visit, requires_db

pytestmark = [requires_db, pytest.mark.integration, pytest.mark.asyncio]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def create_form(client: AsyncClient, headers: dict, name: str = "__itest__Form", **extra) -> dict:
    resp = await client.post("/api/v1/form-templates", json={"name": name, **extra}, headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()


async def add_section(client: AsyncClient, headers: dict, form_id: str, title: str = "Section A") -> dict:
    resp = await client.post(f"/api/v1/form-templates/{form_id}/sections", json={"title": title}, headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()


async def add_question(client: AsyncClient, headers: dict, form_id: str, section_id: str, **kwargs) -> dict:
    payload = {
        "section_id": section_id,
        "question_text": kwargs.pop("question_text", "Question?"),
        "question_type": kwargs.pop("question_type", "SHORT_TEXT"),
        **kwargs,
    }
    resp = await client.post(f"/api/v1/form-templates/{form_id}/questions", json=payload, headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()


async def build_publishable_form(client: AsyncClient, headers: dict, created_forms: list[str]) -> dict:
    form = await create_form(client, headers)
    created_forms.append(form["id"])
    section = await add_section(client, headers, form["id"])
    question = await add_question(
        client, headers, form["id"], section["id"],
        question_text="Vehicle condition", question_type="MULTIPLE_CHOICE", required=True,
        options=[{"label": "Good", "value": "good"}, {"label": "Unsafe", "value": "unsafe"}],
    )
    return {"form_id": form["id"], "section_id": section["id"], "question_id": question["id"], "option_id": question["options"][0]["id"]}


# ---------------------------------------------------------------------------
# CREATE
# ---------------------------------------------------------------------------

async def test_create_requires_auth(client: AsyncClient):
    resp = await client.post("/api/v1/form-templates", json={"name": "X"})
    assert resp.status_code == 401


async def test_employee_cannot_create(client: AsyncClient, employee_headers):
    resp = await client.post("/api/v1/form-templates", json={"name": "__itest__Employee Attempt"}, headers=employee_headers)
    assert resp.status_code == 403, resp.text


# ---------------------------------------------------------------------------
# Item 4 - the /forms *management* API must be admin-only end to end. These
# routes were already enforced as AdminOnly in code but had no regression
# test proving an employee is actually blocked (only create/list/get were
# covered). Built against a single real admin-created form/section/question/
# option so every route is exercised against a genuine existing resource.
# ---------------------------------------------------------------------------

async def test_employee_cannot_manage_form_templates(client: AsyncClient, admin_headers, employee_headers, created_forms):
    built = await build_publishable_form(client, admin_headers, created_forms)
    form_id, section_id, question_id, option_id = (
        built["form_id"], built["section_id"], built["question_id"], built["option_id"],
    )

    # Template-level mutations.
    resp = await client.patch(f"/api/v1/form-templates/{form_id}", json={"name": "Hacked"}, headers=employee_headers)
    assert resp.status_code == 403, resp.text

    resp = await client.post(f"/api/v1/form-templates/{form_id}/publish", headers=employee_headers)
    assert resp.status_code == 403, resp.text

    resp = await client.post(f"/api/v1/form-templates/{form_id}/unpublish", headers=employee_headers)
    assert resp.status_code == 403, resp.text

    resp = await client.post(f"/api/v1/form-templates/{form_id}/duplicate", headers=employee_headers)
    assert resp.status_code == 403, resp.text

    resp = await client.post(f"/api/v1/form-templates/{form_id}/archive", headers=employee_headers)
    assert resp.status_code == 403, resp.text

    # Section-level mutations.
    resp = await client.post(f"/api/v1/form-templates/{form_id}/sections", json={"title": "New"}, headers=employee_headers)
    assert resp.status_code == 403, resp.text

    resp = await client.patch(f"/api/v1/sections/{section_id}", json={"title": "Hacked"}, headers=employee_headers)
    assert resp.status_code == 403, resp.text

    # Question-level mutations.
    resp = await client.post(
        f"/api/v1/form-templates/{form_id}/questions",
        json={"section_id": section_id, "question_text": "New?", "question_type": "SHORT_TEXT"},
        headers=employee_headers,
    )
    assert resp.status_code == 403, resp.text

    resp = await client.patch(f"/api/v1/questions/{question_id}", json={"question_text": "Hacked?"}, headers=employee_headers)
    assert resp.status_code == 403, resp.text

    resp = await client.post(f"/api/v1/questions/{question_id}/duplicate", headers=employee_headers)
    assert resp.status_code == 403, resp.text

    # Option-level mutations.
    resp = await client.post(
        f"/api/v1/questions/{question_id}/options", json={"label": "New", "value": "new"}, headers=employee_headers,
    )
    assert resp.status_code == 403, resp.text

    resp = await client.patch(f"/api/v1/question-options/{option_id}", json={"label": "Hacked"}, headers=employee_headers)
    assert resp.status_code == 403, resp.text

    resp = await client.delete(f"/api/v1/question-options/{option_id}", headers=employee_headers)
    assert resp.status_code == 403, resp.text

    resp = await client.delete(f"/api/v1/questions/{question_id}", headers=employee_headers)
    assert resp.status_code == 403, resp.text

    resp = await client.delete(f"/api/v1/sections/{section_id}", headers=employee_headers)
    assert resp.status_code == 403, resp.text

    resp = await client.delete(f"/api/v1/form-templates/{form_id}", headers=employee_headers)
    assert resp.status_code == 403, resp.text

    # None of the above blocked mutations actually took effect - the
    # template is still exactly what the admin built it as.
    get_resp = await client.get(f"/api/v1/form-templates/{form_id}", headers=admin_headers)
    assert get_resp.status_code == 200
    assert get_resp.json()["status"] == "DRAFT"
    assert len(get_resp.json()["sections"]) == 1


async def test_admin_can_create(client: AsyncClient, admin_headers, created_forms):
    form = await create_form(client, admin_headers, name="__itest__Admin Created")
    created_forms.append(form["id"])
    assert form["status"] == "DRAFT"
    assert form["version"] == 1
    assert form["sections"] == []


async def test_duplicate_names_allowed_with_unique_ids(client: AsyncClient, admin_headers, created_forms, db):
    name = "__itest__Same Name Form"
    f1 = await create_form(client, admin_headers, name=name)
    f2 = await create_form(client, admin_headers, name=name)
    created_forms.extend([f1["id"], f2["id"]])
    assert f1["id"] != f2["id"]
    rows = db.fetch_all("SELECT id FROM form_templates WHERE name = %s", (name,))
    assert len(rows) == 2


# ---------------------------------------------------------------------------
# SECTIONS
# ---------------------------------------------------------------------------

async def test_add_update_delete_section(client: AsyncClient, admin_headers, created_forms):
    form = await create_form(client, admin_headers)
    created_forms.append(form["id"])

    section = await add_section(client, admin_headers, form["id"], title="Original Title")
    assert section["title"] == "Original Title"
    assert section["questions"] == []

    resp = await client.patch(f"/api/v1/sections/{section['id']}", json={"title": "Renamed"}, headers=admin_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["title"] == "Renamed"

    resp = await client.delete(f"/api/v1/sections/{section['id']}", headers=admin_headers)
    assert resp.status_code == 204


async def test_reorder_sections(client: AsyncClient, admin_headers, created_forms):
    form = await create_form(client, admin_headers)
    created_forms.append(form["id"])
    a = await add_section(client, admin_headers, form["id"], title="A")
    b = await add_section(client, admin_headers, form["id"], title="B")

    await client.patch(f"/api/v1/sections/{a['id']}", json={"display_order": 1}, headers=admin_headers)
    await client.patch(f"/api/v1/sections/{b['id']}", json={"display_order": 0}, headers=admin_headers)

    resp = await client.get(f"/api/v1/form-templates/{form['id']}", headers=admin_headers)
    ordered = [s["title"] for s in sorted(resp.json()["sections"], key=lambda s: s["display_order"])]
    assert ordered == ["B", "A"]


async def test_cannot_add_section_to_published_form(client: AsyncClient, admin_headers, created_forms):
    setup = await build_publishable_form(client, admin_headers, created_forms)
    resp = await client.post(f"/api/v1/form-templates/{setup['form_id']}/publish", headers=admin_headers)
    assert resp.status_code == 200, resp.text

    resp = await client.post(
        f"/api/v1/form-templates/{setup['form_id']}/sections", json={"title": "Too Late"}, headers=admin_headers,
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "FORM_NOT_DRAFT"


# ---------------------------------------------------------------------------
# QUESTIONS
# ---------------------------------------------------------------------------

async def test_add_update_delete_question(client: AsyncClient, admin_headers, created_forms):
    form = await create_form(client, admin_headers)
    created_forms.append(form["id"])
    section = await add_section(client, admin_headers, form["id"])

    question = await add_question(client, admin_headers, form["id"], section["id"], question_text="Name?", required=True)
    assert question["required"] is True

    resp = await client.patch(f"/api/v1/questions/{question['id']}", json={"question_text": "Full Name?"}, headers=admin_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["question_text"] == "Full Name?"

    resp = await client.delete(f"/api/v1/questions/{question['id']}", headers=admin_headers)
    assert resp.status_code == 204


async def test_duplicate_question(client: AsyncClient, admin_headers, created_forms):
    form = await create_form(client, admin_headers)
    created_forms.append(form["id"])
    section = await add_section(client, admin_headers, form["id"])
    question = await add_question(
        client, admin_headers, form["id"], section["id"],
        question_text="Pick one", question_type="DROPDOWN",
        options=[{"label": "A", "value": "a"}, {"label": "B", "value": "b"}],
    )

    resp = await client.post(f"/api/v1/questions/{question['id']}/duplicate", headers=admin_headers)
    assert resp.status_code == 200, resp.text
    copy = resp.json()
    assert copy["id"] != question["id"]
    assert copy["question_text"] == "Pick one"
    assert len(copy["options"]) == 2
    assert {o["id"] for o in copy["options"]}.isdisjoint({o["id"] for o in question["options"]})


@pytest.mark.parametrize("question_type", [
    "SHORT_TEXT", "LONG_TEXT", "MULTIPLE_CHOICE", "CHECKBOXES", "DROPDOWN", "YES_NO",
    "NUMBER", "DATE", "TIME", "DATE_TIME", "FILE_UPLOAD", "PHOTO_UPLOAD",
    "EMAIL", "PHONE", "URL", "RATING",
])
async def test_every_question_type_can_be_created(client: AsyncClient, admin_headers, created_forms, question_type):
    """Every QuestionType the backend declares must actually be acceptable to add_question."""
    form = await create_form(client, admin_headers, name=f"__itest__{question_type}")
    created_forms.append(form["id"])
    section = await add_section(client, admin_headers, form["id"])
    resp = await client.post(
        f"/api/v1/form-templates/{form['id']}/questions",
        json={"section_id": section["id"], "question_text": "Q", "question_type": question_type},
        headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["question_type"] == question_type


async def test_validation_config_round_trips(client: AsyncClient, admin_headers, created_forms):
    form = await create_form(client, admin_headers)
    created_forms.append(form["id"])
    section = await add_section(client, admin_headers, form["id"])
    config = {"min": 0, "max": 100}
    question = await add_question(
        client, admin_headers, form["id"], section["id"],
        question_text="Score", question_type="NUMBER", validation_config=config,
    )
    assert question["validation_config"] == config

    resp = await client.get(f"/api/v1/form-templates/{form['id']}", headers=admin_headers)
    stored = resp.json()["sections"][0]["questions"][0]["validation_config"]
    assert stored == config


async def test_cannot_delete_question_with_recorded_answers(
    client: AsyncClient, admin_headers, employee_headers, seeded_world, created_forms, created_visits,
):
    setup = await build_publishable_form(client, admin_headers, created_forms)
    await client.post(f"/api/v1/form-templates/{setup['form_id']}/publish", headers=admin_headers)

    visit_id = await create_visit(
        client, admin_headers, seeded_world["customer_id"], seeded_world["employee_id"], created_visits,
    )
    resp = await client.post(
        "/api/v1/form-submissions",
        json={"form_id": setup["form_id"], "visit_id": visit_id, "answers": [{"question_id": setup["question_id"], "answer_value": "good"}]},
        headers=employee_headers,
    )
    assert resp.status_code == 200, resp.text

    await client.post(f"/api/v1/form-templates/{setup['form_id']}/unpublish", headers=admin_headers)
    resp = await client.delete(f"/api/v1/questions/{setup['question_id']}", headers=admin_headers)
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "QUESTION_HAS_ANSWERS"


# ---------------------------------------------------------------------------
# OPTIONS
# ---------------------------------------------------------------------------

async def test_add_update_delete_reorder_options(client: AsyncClient, admin_headers, created_forms):
    form = await create_form(client, admin_headers)
    created_forms.append(form["id"])
    section = await add_section(client, admin_headers, form["id"])
    question = await add_question(client, admin_headers, form["id"], section["id"], question_type="CHECKBOXES")

    resp = await client.post(f"/api/v1/questions/{question['id']}/options", json={"label": "First", "value": "first"}, headers=admin_headers)
    assert resp.status_code == 200, resp.text
    opt1 = resp.json()
    resp = await client.post(f"/api/v1/questions/{question['id']}/options", json={"label": "Second", "value": "second"}, headers=admin_headers)
    opt2 = resp.json()

    # Rename
    resp = await client.patch(f"/api/v1/question-options/{opt1['id']}", json={"label": "Renamed First"}, headers=admin_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["label"] == "Renamed First"

    # Reorder
    await client.patch(f"/api/v1/question-options/{opt1['id']}", json={"display_order": 1}, headers=admin_headers)
    await client.patch(f"/api/v1/question-options/{opt2['id']}", json={"display_order": 0}, headers=admin_headers)
    resp = await client.get(f"/api/v1/form-templates/{form['id']}", headers=admin_headers)
    options = resp.json()["sections"][0]["questions"][0]["options"]
    ordered = [o["label"] for o in sorted(options, key=lambda o: o["display_order"])]
    assert ordered == ["Second", "Renamed First"]

    # Delete
    resp = await client.delete(f"/api/v1/question-options/{opt2['id']}", headers=admin_headers)
    assert resp.status_code == 204


# ---------------------------------------------------------------------------
# LIFECYCLE
# ---------------------------------------------------------------------------

async def test_cannot_publish_form_without_sections(client: AsyncClient, admin_headers, created_forms):
    form = await create_form(client, admin_headers)
    created_forms.append(form["id"])
    resp = await client.post(f"/api/v1/form-templates/{form['id']}/publish", headers=admin_headers)
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "FORM_EMPTY"


async def test_full_lifecycle_draft_publish_archive(client: AsyncClient, admin_headers, created_forms):
    setup = await build_publishable_form(client, admin_headers, created_forms)

    resp = await client.post(f"/api/v1/form-templates/{setup['form_id']}/publish", headers=admin_headers)
    assert resp.status_code == 200 and resp.json()["status"] == "PUBLISHED"

    resp = await client.post(f"/api/v1/form-templates/{setup['form_id']}/archive", headers=admin_headers)
    assert resp.status_code == 200 and resp.json()["status"] == "ARCHIVED"


async def test_cannot_publish_archived_form(client: AsyncClient, admin_headers, created_forms):
    setup = await build_publishable_form(client, admin_headers, created_forms)
    await client.post(f"/api/v1/form-templates/{setup['form_id']}/publish", headers=admin_headers)
    await client.post(f"/api/v1/form-templates/{setup['form_id']}/archive", headers=admin_headers)

    resp = await client.post(f"/api/v1/form-templates/{setup['form_id']}/publish", headers=admin_headers)
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "FORM_ARCHIVED"


async def test_cannot_unpublish_a_draft(client: AsyncClient, admin_headers, created_forms):
    setup = await build_publishable_form(client, admin_headers, created_forms)
    resp = await client.post(f"/api/v1/form-templates/{setup['form_id']}/unpublish", headers=admin_headers)
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "FORM_NOT_PUBLISHED"


async def test_employee_cannot_render_a_draft_form(client: AsyncClient, admin_headers, employee_headers, created_forms):
    """The employee fill screen calls /render directly - it must never hand back a DRAFT/ARCHIVED form's structure."""
    setup = await build_publishable_form(client, admin_headers, created_forms)  # never published

    resp = await client.get(f"/api/v1/form-templates/{setup['form_id']}/render", headers=employee_headers)
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "FORM_NOT_PUBLISHED"


async def test_employee_cannot_render_an_archived_form(client: AsyncClient, admin_headers, employee_headers, created_forms):
    setup = await build_publishable_form(client, admin_headers, created_forms)
    await client.post(f"/api/v1/form-templates/{setup['form_id']}/publish", headers=admin_headers)
    await client.post(f"/api/v1/form-templates/{setup['form_id']}/archive", headers=admin_headers)

    resp = await client.get(f"/api/v1/form-templates/{setup['form_id']}/render", headers=employee_headers)
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "FORM_NOT_PUBLISHED"


async def test_employee_can_render_a_published_form(client: AsyncClient, admin_headers, employee_headers, created_forms):
    setup = await build_publishable_form(client, admin_headers, created_forms)
    await client.post(f"/api/v1/form-templates/{setup['form_id']}/publish", headers=admin_headers)

    resp = await client.get(f"/api/v1/form-templates/{setup['form_id']}/render", headers=employee_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "PUBLISHED"


async def test_admin_can_render_a_draft_form_for_preview(client: AsyncClient, admin_headers, created_forms):
    """Admin preview uses GET /form-templates/{id} (unaffected), but /render itself must stay open to admins too."""
    setup = await build_publishable_form(client, admin_headers, created_forms)  # never published
    resp = await client.get(f"/api/v1/form-templates/{setup['form_id']}/render", headers=admin_headers)
    assert resp.status_code == 200, resp.text


# ---------------------------------------------------------------------------
# P1-1: employee template visibility (DRAFT/ARCHIVED must not be exposed)
# ---------------------------------------------------------------------------

async def test_employee_cannot_list_draft_templates(client: AsyncClient, admin_headers, employee_headers, created_forms):
    setup = await build_publishable_form(client, admin_headers, created_forms)  # never published, still DRAFT

    resp = await client.get("/api/v1/form-templates", headers=employee_headers)
    assert resp.status_code == 200, resp.text
    assert setup["form_id"] not in [t["id"] for t in resp.json()], (
        "P1-1: an employee's template list must never include a DRAFT template"
    )

    # Even an explicit status=DRAFT query param must not widen an employee's view.
    resp = await client.get("/api/v1/form-templates", params={"status": "DRAFT"}, headers=employee_headers)
    assert resp.status_code == 200, resp.text
    assert setup["form_id"] not in [t["id"] for t in resp.json()]


async def test_employee_cannot_list_archived_templates(client: AsyncClient, admin_headers, employee_headers, created_forms):
    setup = await build_publishable_form(client, admin_headers, created_forms)
    await client.post(f"/api/v1/form-templates/{setup['form_id']}/publish", headers=admin_headers)
    await client.post(f"/api/v1/form-templates/{setup['form_id']}/archive", headers=admin_headers)

    resp = await client.get("/api/v1/form-templates", params={"status": "ARCHIVED"}, headers=employee_headers)
    assert resp.status_code == 200, resp.text
    assert setup["form_id"] not in [t["id"] for t in resp.json()]


async def test_employee_cannot_retrieve_draft_template_by_id(client: AsyncClient, admin_headers, employee_headers, created_forms):
    """P1-1: IDOR-style access - the employee knows the id directly, never saw it via list."""
    setup = await build_publishable_form(client, admin_headers, created_forms)  # never published

    resp = await client.get(f"/api/v1/form-templates/{setup['form_id']}", headers=employee_headers)
    assert resp.status_code == 403, resp.text
    assert resp.json()["error"]["code"] == "FORM_NOT_PUBLISHED"


async def test_employee_cannot_retrieve_archived_template_by_id(client: AsyncClient, admin_headers, employee_headers, created_forms):
    setup = await build_publishable_form(client, admin_headers, created_forms)
    await client.post(f"/api/v1/form-templates/{setup['form_id']}/publish", headers=admin_headers)
    await client.post(f"/api/v1/form-templates/{setup['form_id']}/archive", headers=admin_headers)

    resp = await client.get(f"/api/v1/form-templates/{setup['form_id']}", headers=employee_headers)
    assert resp.status_code == 403, resp.text
    assert resp.json()["error"]["code"] == "FORM_NOT_PUBLISHED"


async def test_employee_can_list_and_retrieve_published_templates(client: AsyncClient, admin_headers, employee_headers, created_forms):
    setup = await build_publishable_form(client, admin_headers, created_forms)
    await client.post(f"/api/v1/form-templates/{setup['form_id']}/publish", headers=admin_headers)

    listing = await client.get("/api/v1/form-templates", headers=employee_headers)
    assert listing.status_code == 200, listing.text
    assert setup["form_id"] in [t["id"] for t in listing.json()]

    detail = await client.get(f"/api/v1/form-templates/{setup['form_id']}", headers=employee_headers)
    assert detail.status_code == 200, detail.text
    assert detail.json()["status"] == "PUBLISHED"


async def test_admin_retains_full_template_management_visibility(client: AsyncClient, admin_headers, created_forms):
    """Preserve existing admin behaviour: DRAFT/ARCHIVED remain fully visible and manageable."""
    setup = await build_publishable_form(client, admin_headers, created_forms)  # DRAFT

    draft_list = await client.get("/api/v1/form-templates", params={"status": "DRAFT"}, headers=admin_headers)
    assert setup["form_id"] in [t["id"] for t in draft_list.json()]

    draft_detail = await client.get(f"/api/v1/form-templates/{setup['form_id']}", headers=admin_headers)
    assert draft_detail.status_code == 200, draft_detail.text

    await client.post(f"/api/v1/form-templates/{setup['form_id']}/publish", headers=admin_headers)
    await client.post(f"/api/v1/form-templates/{setup['form_id']}/archive", headers=admin_headers)

    archived_list = await client.get("/api/v1/form-templates", params={"status": "ARCHIVED"}, headers=admin_headers)
    assert setup["form_id"] in [t["id"] for t in archived_list.json()]

    archived_detail = await client.get(f"/api/v1/form-templates/{setup['form_id']}", headers=admin_headers)
    assert archived_detail.status_code == 200, archived_detail.text


async def test_employee_cannot_create_draft_submission_against_unpublished_form(
    client: AsyncClient, admin_headers, employee_headers, seeded_world, created_forms, created_visits,
):
    """
    P1-1: closes the gap where an employee who merely knows/guesses a
    DRAFT/ARCHIVED form_id could still create a draft submission against it
    (the old check only fired at final submit, never at draft-save).
    """
    setup = await build_publishable_form(client, admin_headers, created_forms)  # never published
    visit_id = await create_visit(
        client, admin_headers, seeded_world["customer_id"], seeded_world["employee_id"], created_visits,
    )
    resp = await client.post(
        "/api/v1/form-submissions",
        json={"form_id": setup["form_id"], "visit_id": visit_id, "answers": []},
        headers=employee_headers,
    )
    assert resp.status_code == 400, resp.text
    assert resp.json()["error"]["code"] == "FORM_NOT_PUBLISHED"


async def test_admin_can_still_draft_save_against_unpublished_form(
    client: AsyncClient, admin_headers, seeded_world, created_forms, created_visits,
):
    """Preserve existing admin QA/test-fill workflow against a non-published form (matches /render's admin preview allowance)."""
    setup = await build_publishable_form(client, admin_headers, created_forms)  # never published
    visit_id = await create_visit(
        client, admin_headers, seeded_world["customer_id"], seeded_world["other_employee_id"], created_visits,
    )
    resp = await client.post(
        "/api/v1/form-submissions",
        json={"form_id": setup["form_id"], "visit_id": visit_id, "answers": []},
        headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text


# ---------------------------------------------------------------------------
# SUBMISSIONS
# ---------------------------------------------------------------------------

async def test_submission_requires_visit_ownership(
    client: AsyncClient, admin_headers, employee_headers, other_employee_headers, seeded_world, created_forms, created_visits,
):
    setup = await build_publishable_form(client, admin_headers, created_forms)
    await client.post(f"/api/v1/form-templates/{setup['form_id']}/publish", headers=admin_headers)

    visit_id = await create_visit(
        client, admin_headers, seeded_world["customer_id"], seeded_world["employee_id"], created_visits,
    )

    # Employee B (other_employee) is not assigned to this visit -> 403.
    resp = await client.post(
        "/api/v1/form-submissions",
        json={"form_id": setup["form_id"], "visit_id": visit_id, "answers": []},
        headers=other_employee_headers,
    )
    assert resp.status_code == 403, resp.text
    assert resp.json()["error"]["code"] == "VISIT_NOT_ASSIGNED"

    # Employee A (assigned) succeeds.
    resp = await client.post(
        "/api/v1/form-submissions",
        json={"form_id": setup["form_id"], "visit_id": visit_id, "answers": []},
        headers=employee_headers,
    )
    assert resp.status_code == 200, resp.text


async def test_admin_can_submit_for_any_visit(
    client: AsyncClient, admin_headers, seeded_world, created_forms, created_visits,
):
    setup = await build_publishable_form(client, admin_headers, created_forms)
    await client.post(f"/api/v1/form-templates/{setup['form_id']}/publish", headers=admin_headers)
    visit_id = await create_visit(
        client, admin_headers, seeded_world["customer_id"], seeded_world["other_employee_id"], created_visits,
    )
    resp = await client.post(
        "/api/v1/form-submissions",
        json={"form_id": setup["form_id"], "visit_id": visit_id, "answers": []},
        headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text


async def test_draft_save_then_submit_persists_answers(
    client: AsyncClient, admin_headers, employee_headers, seeded_world, created_forms, created_visits, db,
):
    setup = await build_publishable_form(client, admin_headers, created_forms)
    await client.post(f"/api/v1/form-templates/{setup['form_id']}/publish", headers=admin_headers)
    visit_id = await create_visit(
        client, admin_headers, seeded_world["customer_id"], seeded_world["employee_id"], created_visits,
    )

    draft = await client.post(
        "/api/v1/form-submissions",
        json={"form_id": setup["form_id"], "visit_id": visit_id, "answers": [{"question_id": setup["question_id"], "answer_value": "good"}]},
        headers=employee_headers,
    )
    assert draft.status_code == 200, draft.text
    submission_id = draft.json()["id"]
    assert draft.json()["status"] == "DRAFT"

    row = db.fetch_one("SELECT status FROM form_submissions WHERE id = %s", (submission_id,))
    assert row["status"] == "DRAFT"
    answer_row = db.fetch_one("SELECT answer_value FROM form_answers WHERE submission_id = %s", (submission_id,))
    assert answer_row["answer_value"] == "good"

    submitted = await client.post(f"/api/v1/form-submissions/{submission_id}/submit", headers=employee_headers)
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["status"] == "SUBMITTED"
    row = db.fetch_one("SELECT status, submitted_at FROM form_submissions WHERE id = %s", (submission_id,))
    assert row["status"] == "SUBMITTED"
    assert row["submitted_at"] is not None


async def test_second_submit_is_rejected_with_already_submitted_409(
    client: AsyncClient, admin_headers, employee_headers, seeded_world, created_forms, created_visits, db,
):
    """
    P1-14: FormTemplateService.finalize_submission's ALREADY_SUBMITTED path
    (a double-tap/retried final submit) had zero prior test coverage.
    """
    setup = await build_publishable_form(client, admin_headers, created_forms)
    await client.post(f"/api/v1/form-templates/{setup['form_id']}/publish", headers=admin_headers)
    visit_id = await create_visit(
        client, admin_headers, seeded_world["customer_id"], seeded_world["employee_id"], created_visits,
    )
    draft = await client.post(
        "/api/v1/form-submissions",
        json={"form_id": setup["form_id"], "visit_id": visit_id, "answers": [{"question_id": setup["question_id"], "answer_value": "good"}]},
        headers=employee_headers,
    )
    submission_id = draft.json()["id"]

    first = await client.post(f"/api/v1/form-submissions/{submission_id}/submit", headers=employee_headers)
    assert first.status_code == 200, first.text
    first_submitted_at = first.json()["submitted_at"]
    assert first_submitted_at is not None

    second = await client.post(f"/api/v1/form-submissions/{submission_id}/submit", headers=employee_headers)
    assert second.status_code == 409, second.text
    assert second.json()["error"]["code"] == "ALREADY_SUBMITTED"

    # The original submission is untouched - no second record, timestamp unchanged.
    row = db.fetch_one("SELECT status, submitted_at FROM form_submissions WHERE id = %s", (submission_id,))
    assert row["status"] == "SUBMITTED"
    assert row["submitted_at"] is not None

    still_submitted = await client.get(f"/api/v1/form-submissions/{submission_id}", headers=employee_headers)
    assert still_submitted.json()["submitted_at"] == first_submitted_at, (
        "a rejected duplicate submit must never alter the original submission"
    )

    count_row = db.fetch_one(
        "SELECT count(*) AS c FROM form_submissions WHERE visit_id = %s AND form_id = %s",
        (visit_id, setup["form_id"]),
    )
    assert count_row["c"] == 1, "a duplicate submit must never create a second submission record"


async def test_required_answer_missing_blocks_submit(
    client: AsyncClient, admin_headers, employee_headers, seeded_world, created_forms, created_visits,
):
    setup = await build_publishable_form(client, admin_headers, created_forms)
    await client.post(f"/api/v1/form-templates/{setup['form_id']}/publish", headers=admin_headers)
    visit_id = await create_visit(
        client, admin_headers, seeded_world["customer_id"], seeded_world["employee_id"], created_visits,
    )
    # Submit with the required question left unanswered.
    resp = await client.post(
        "/api/v1/form-submissions",
        json={"form_id": setup["form_id"], "visit_id": visit_id, "answers": []},
        headers=employee_headers,
    )
    submission_id = resp.json()["id"]
    resp = await client.post(f"/api/v1/form-submissions/{submission_id}/submit", headers=employee_headers)
    assert resp.status_code == 422, resp.text
    assert resp.json()["error"]["code"] == "REQUIRED_ANSWERS_MISSING"


async def test_cannot_submit_to_unpublished_form(
    client: AsyncClient, admin_headers, employee_headers, seeded_world, created_forms, created_visits,
):
    """
    finalize_submission's FORM_NOT_PUBLISHED check applies unconditionally
    (even to an admin) and is separate from P1-1's draft-save gate. Create
    the draft while the form is legitimately PUBLISHED, then unpublish it
    before submitting, to isolate exactly the rule this test targets.
    """
    setup = await build_publishable_form(client, admin_headers, created_forms)
    await client.post(f"/api/v1/form-templates/{setup['form_id']}/publish", headers=admin_headers)
    visit_id = await create_visit(
        client, admin_headers, seeded_world["customer_id"], seeded_world["employee_id"], created_visits,
    )
    resp = await client.post(
        "/api/v1/form-submissions",
        json={"form_id": setup["form_id"], "visit_id": visit_id, "answers": [{"question_id": setup["question_id"], "answer_value": "good"}]},
        headers=employee_headers,
    )
    assert resp.status_code == 200, resp.text
    submission_id = resp.json()["id"]

    await client.post(f"/api/v1/form-templates/{setup['form_id']}/unpublish", headers=admin_headers)

    resp = await client.post(f"/api/v1/form-submissions/{submission_id}/submit", headers=employee_headers)
    assert resp.status_code == 400, resp.text
    assert resp.json()["error"]["code"] == "FORM_NOT_PUBLISHED"


async def test_non_owner_non_admin_cannot_read_submission(
    client: AsyncClient, admin_headers, employee_headers, other_employee_headers, seeded_world, created_forms, created_visits,
):
    setup = await build_publishable_form(client, admin_headers, created_forms)
    await client.post(f"/api/v1/form-templates/{setup['form_id']}/publish", headers=admin_headers)
    visit_id = await create_visit(
        client, admin_headers, seeded_world["customer_id"], seeded_world["employee_id"], created_visits,
    )
    resp = await client.post(
        "/api/v1/form-submissions",
        json={"form_id": setup["form_id"], "visit_id": visit_id, "answers": []},
        headers=employee_headers,
    )
    submission_id = resp.json()["id"]

    resp = await client.get(f"/api/v1/form-submissions/{submission_id}", headers=other_employee_headers)
    assert resp.status_code == 403

    resp = await client.get(f"/api/v1/form-submissions/{submission_id}", headers=admin_headers)
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# VERSIONING
# ---------------------------------------------------------------------------

async def test_old_submission_keeps_its_original_version_structure(
    client: AsyncClient, admin_headers, employee_headers, seeded_world, created_forms, created_visits,
):
    setup = await build_publishable_form(client, admin_headers, created_forms)
    publish1 = await client.post(f"/api/v1/form-templates/{setup['form_id']}/publish", headers=admin_headers)
    assert publish1.json()["version"] == 1

    visit_id = await create_visit(
        client, admin_headers, seeded_world["customer_id"], seeded_world["employee_id"], created_visits,
    )
    resp = await client.post(
        "/api/v1/form-submissions",
        json={"form_id": setup["form_id"], "visit_id": visit_id, "answers": [{"question_id": setup["question_id"], "answer_value": "good"}]},
        headers=employee_headers,
    )
    submission_id = resp.json()["id"]
    await client.post(f"/api/v1/form-submissions/{submission_id}/submit", headers=employee_headers)

    # Edit the form materially and publish again -> version must bump to 2.
    await client.post(f"/api/v1/form-templates/{setup['form_id']}/unpublish", headers=admin_headers)
    await add_question(client, admin_headers, setup["form_id"], setup["section_id"], question_text="New field", question_type="SHORT_TEXT")
    publish2 = await client.post(f"/api/v1/form-templates/{setup['form_id']}/publish", headers=admin_headers)
    assert publish2.status_code == 200, publish2.text
    assert publish2.json()["version"] == 2

    # The live render reflects v2: the original question plus the new one.
    render = await client.get(f"/api/v1/form-templates/{setup['form_id']}/render", headers=employee_headers)
    live_question_texts = {q["question_text"] for s in render.json()["sections"] for q in s["questions"]}
    assert "New field" in live_question_texts
    assert "Vehicle condition" in live_question_texts

    # The already-submitted record must still show v1's exact structure/answer.
    detail = await client.get(f"/api/v1/form-submissions/{submission_id}", headers=admin_headers)
    assert detail.status_code == 200, detail.text
    body = detail.json()
    assert body["form_version"] == 1
    question_texts = {q["question_text"] for s in body["sections"] for q in s["questions"]}
    assert "New field" not in question_texts
    answer = next(a for a in body["answers"] if a["question_id"] == setup["question_id"])
    assert answer["answer_value"] == "good"


async def test_republishing_without_prior_publish_snapshot_does_not_bump_version(
    client: AsyncClient, admin_headers, created_forms,
):
    """First-ever publish of a version must not bump - only a re-publish does."""
    setup = await build_publishable_form(client, admin_headers, created_forms)
    resp = await client.post(f"/api/v1/form-templates/{setup['form_id']}/publish", headers=admin_headers)
    assert resp.json()["version"] == 1


# ---------------------------------------------------------------------------
# DUPLICATION
# ---------------------------------------------------------------------------

async def test_duplicate_form_copies_structure_with_new_ids(client: AsyncClient, admin_headers, created_forms):
    setup = await build_publishable_form(client, admin_headers, created_forms)
    await client.post(f"/api/v1/form-templates/{setup['form_id']}/publish", headers=admin_headers)

    resp = await client.post(f"/api/v1/form-templates/{setup['form_id']}/duplicate", headers=admin_headers)
    assert resp.status_code == 200, resp.text
    copy = resp.json()
    created_forms.append(copy["id"])

    assert copy["id"] != setup["form_id"]
    assert copy["status"] == "DRAFT"
    assert copy["version"] == 1
    assert len(copy["sections"]) == 1
    assert len(copy["sections"][0]["questions"]) == 1
    copied_question = copy["sections"][0]["questions"][0]
    assert copied_question["id"] != setup["question_id"]
    assert len(copied_question["options"]) == 2
    assert {o["id"] for o in copied_question["options"]}.isdisjoint({setup["option_id"]})


async def test_duplicate_form_allows_reusing_original_name(client: AsyncClient, admin_headers, created_forms):
    original = await create_form(client, admin_headers, name="__itest__Dup Source")
    created_forms.append(original["id"])
    await add_section(client, admin_headers, original["id"])  # so it CAN be published later if needed

    resp = await client.post(f"/api/v1/form-templates/{original['id']}/duplicate", headers=admin_headers)
    copy = resp.json()
    created_forms.append(copy["id"])
    assert copy["name"] == f"{original['name']} (Copy)"

    # Renaming the copy back to the exact original name must be allowed (no unique constraint).
    resp = await client.patch(f"/api/v1/form-templates/{copy['id']}", json={"name": original["name"]}, headers=admin_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["name"] == original["name"]


# ---------------------------------------------------------------------------
# P1-15: GET /form-submissions pagination + N+1 elimination
# ---------------------------------------------------------------------------

@contextlib.contextmanager
def _count_sql_statements():
    """Counts real SQL round trips issued to the app's actual async engine
    during the block - the test client runs in-process (ASGITransport), so
    this observes exactly what one HTTP request executes."""
    from app.database import engine

    counter = {"n": 0}

    def _before_cursor_execute(*args, **kwargs):
        counter["n"] += 1

    event.listen(engine.sync_engine, "before_cursor_execute", _before_cursor_execute)
    try:
        yield counter
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", _before_cursor_execute)


async def test_list_submissions_pagination(
    client: AsyncClient, admin_headers, employee_headers, seeded_world, created_forms, created_visits,
):
    setup = await build_publishable_form(client, admin_headers, created_forms)
    await client.post(f"/api/v1/form-templates/{setup['form_id']}/publish", headers=admin_headers)

    submission_ids = []
    for _ in range(3):
        visit_id = await create_visit(
            client, admin_headers, seeded_world["customer_id"], seeded_world["employee_id"], created_visits,
        )
        resp = await client.post(
            "/api/v1/form-submissions",
            json={"form_id": setup["form_id"], "visit_id": visit_id, "answers": []},
            headers=employee_headers,
        )
        submission_ids.append(resp.json()["id"])

    page1 = await client.get(
        "/api/v1/form-submissions",
        params={"form_id": setup["form_id"], "skip": 0, "limit": 2},
        headers=admin_headers,
    )
    assert page1.status_code == 200, page1.text
    assert len(page1.json()) == 2

    page2 = await client.get(
        "/api/v1/form-submissions",
        params={"form_id": setup["form_id"], "skip": 2, "limit": 2},
        headers=admin_headers,
    )
    assert page2.status_code == 200, page2.text
    assert len(page2.json()) == 1

    ids_page1 = {s["id"] for s in page1.json()}
    ids_page2 = {s["id"] for s in page2.json()}
    assert ids_page1.isdisjoint(ids_page2), "pages must not overlap"
    assert ids_page1 | ids_page2 == set(submission_ids)


async def test_list_submissions_empty_page_beyond_range(
    client: AsyncClient, admin_headers, employee_headers, seeded_world, created_forms, created_visits,
):
    setup = await build_publishable_form(client, admin_headers, created_forms)
    await client.post(f"/api/v1/form-templates/{setup['form_id']}/publish", headers=admin_headers)
    visit_id = await create_visit(
        client, admin_headers, seeded_world["customer_id"], seeded_world["employee_id"], created_visits,
    )
    await client.post(
        "/api/v1/form-submissions",
        json={"form_id": setup["form_id"], "visit_id": visit_id, "answers": []},
        headers=employee_headers,
    )

    resp = await client.get(
        "/api/v1/form-submissions",
        params={"form_id": setup["form_id"], "skip": 1000, "limit": 10},
        headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json() == []


async def test_list_submissions_does_not_n_plus_one(
    client: AsyncClient, admin_headers, employee_headers, seeded_world, created_forms, created_visits,
):
    """
    P1-15: the previous per-row _resolve_submission_context issued 2-3
    queries PER submission on top of the base list query - for 6 rows that
    is 12-18+ round trips. The batched version issues a small, constant
    number regardless of how many rows are on the page.
    """
    setup = await build_publishable_form(client, admin_headers, created_forms)
    await client.post(f"/api/v1/form-templates/{setup['form_id']}/publish", headers=admin_headers)

    for _ in range(6):
        visit_id = await create_visit(
            client, admin_headers, seeded_world["customer_id"], seeded_world["employee_id"], created_visits,
        )
        await client.post(
            "/api/v1/form-submissions",
            json={"form_id": setup["form_id"], "visit_id": visit_id, "answers": []},
            headers=employee_headers,
        )

    with _count_sql_statements() as counter:
        resp = await client.get(
            "/api/v1/form-submissions", params={"form_id": setup["form_id"]}, headers=admin_headers
        )
    assert resp.status_code == 200, resp.text
    assert len(resp.json()) == 6
    assert counter["n"] < 12, (
        f"P1-15: expected a roughly constant, small query count independent of row count, got {counter['n']}"
    )
    # Context enrichment must still be correct, just batched.
    for row in resp.json():
        assert row["employee_name"] is not None
        assert row["customer_name"] is not None
