"""
Integration: ad-hoc visit admin review, 404-for-foreign-records and
account-deletion follow-up (backend task B2). Synthetic data only.
"""
from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
import pytest_asyncio

from app.core.datetime_utils import get_ist_now
from tests.integration.conftest import (
    TEST_PASSWORD,
    auth_headers,
    db_cursor,
    iso_in,
    requires_db,
)
from tests.integration.test_access_scoping_integration import (
    _cleanup_user,
    _make_customer,
    _make_user,
)

pytestmark = [requires_db, pytest.mark.integration, pytest.mark.asyncio]

OUTSIDE_LABEL = "AD-HOC · OUTSIDE ASSIGNMENT"


async def _adhoc(client, headers, customer_id, track, reason="Walk-in"):
    resp = await client.post(
        "/api/v1/visits/ad-hoc",
        json={"customer_id": customer_id, "adhoc_reason": reason, "adhoc_notes": "n1"},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    track.append(resp.json()["id"])
    return resp.json()


@pytest_asyncio.fixture
async def outlets(client, admin_headers, created_customers):
    return {
        "outside": await _make_customer(client, admin_headers, created_customers, "AdhocOut"),
        "inside": await _make_customer(client, admin_headers, created_customers, "AdhocIn"),
    }


@pytest.fixture
def assigned_inside(seeded_world, outlets):
    with db_cursor() as cur:
        cur.execute(
            "INSERT INTO employee_customer_assignments (id,employee_id,customer_id,created_by,created_at) "
            "VALUES (%s,%s,%s,%s,now())",
            (str(uuid.uuid4()), seeded_world["employee_id"], outlets["inside"]["id"], seeded_world["admin_user_id"]),
        )
    yield
    with db_cursor(privileged=True) as cur:
        cur.execute("DELETE FROM employee_customer_assignments WHERE customer_id=%s", (outlets["inside"]["id"],))


async def test_adhoc_flags_admin_filters_review_endpoint_and_employee_privacy(
    client, admin_headers, employee_headers, other_employee_headers, outlets, assigned_inside, created_visits, seeded_world
):
    out = await _adhoc(client, employee_headers, outlets["outside"]["id"], created_visits)
    inn = await _adhoc(client, employee_headers, outlets["inside"]["id"], created_visits)

    # Employee response: is_adhoc yes, review flags never exposed.
    assert out["is_adhoc"] is True
    assert out["outside_assignment"] is None and out["review_label"] is None

    # Admin detail carries the flags.
    d_out = (await client.get(f"/api/v1/visits/{out['id']}", headers=admin_headers)).json()
    d_in = (await client.get(f"/api/v1/visits/{inn['id']}", headers=admin_headers)).json()
    assert (d_out["is_adhoc"], d_out["outside_assignment"], d_out["review_label"]) == (True, True, OUTSIDE_LABEL)
    assert (d_in["is_adhoc"], d_in["outside_assignment"], d_in["review_label"]) == (True, False, "AD-HOC")

    # A planned visit stays unflagged.
    planned = await client.post(
        "/api/v1/visits",
        json={
            "customer_id": seeded_world["customer_id"],
            "employee_id": seeded_world["other_employee_id"],
            "scheduled_at": iso_in(5),
        },
        headers=admin_headers,
    )
    assert planned.status_code == 201, planned.text
    created_visits.append(planned.json()["id"])
    p = (await client.get(f"/api/v1/visits/{planned.json()['id']}", headers=admin_headers)).json()
    assert (p["is_adhoc"], p["outside_assignment"], p["review_label"]) == (False, False, None)

    # Filters on the admin list (ADHOC alias + AD_HOC + outside_assignment).
    for vt in ("ADHOC", "AD_HOC"):
        r = await client.get(f"/api/v1/visits?visit_type={vt}&limit=200", headers=admin_headers)
        assert r.status_code == 200, r.text
        ids = {v["id"] for v in r.json()}
        assert {out["id"], inn["id"]} <= ids and planned.json()["id"] not in ids
    r = await client.get("/api/v1/visits?outside_assignment=true&limit=200", headers=admin_headers)
    ids = {v["id"] for v in r.json()}
    assert out["id"] in ids and inn["id"] not in ids and planned.json()["id"] not in ids
    assert int(r.headers["X-Total-Count"]) == len(r.json())
    assert (await client.get("/api/v1/visits?visit_type=BOGUS", headers=admin_headers)).status_code == 422

    # Review endpoint: admin only, newest first, carries name/outlet/reason/notes.
    rev = await client.get("/api/v1/visits/adhoc-review?limit=200", headers=admin_headers)
    assert rev.status_code == 200, rev.text
    items = rev.json()
    assert all(i["is_adhoc"] for i in items)
    order = [i["id"] for i in items]
    assert order.index(inn["id"]) < order.index(out["id"])  # newest first
    item = next(i for i in items if i["id"] == out["id"])
    assert item["employee_name"] and item["customer_name"] and item["adhoc_reason"] == "Walk-in"
    assert item["adhoc_notes"] == "n1" and item["outside_assignment"] is True
    only_out = await client.get("/api/v1/visits/adhoc-review?outside_assignment=true&limit=200", headers=admin_headers)
    out_ids = {i["id"] for i in only_out.json()}
    assert out["id"] in out_ids and inn["id"] not in out_ids
    assert (await client.get("/api/v1/visits/adhoc-review", headers=employee_headers)).status_code == 403

    # Employee list never exposes flags, and ignores the outside_assignment filter.
    mine = await client.get("/api/v1/visits?outside_assignment=true&limit=200", headers=employee_headers)
    assert mine.status_code == 200
    assert all(v["outside_assignment"] is None and v["review_label"] is None for v in mine.json())
    assert {out["id"], inn["id"]} <= {v["id"] for v in mine.json()}

    # Foreign visit -> 404 for the other employee, identical to a truly missing id.
    foreign = await client.get(f"/api/v1/visits/{out['id']}", headers=other_employee_headers)
    missing = await client.get(f"/api/v1/visits/{uuid.uuid4()}", headers=other_employee_headers)
    assert foreign.status_code == missing.status_code == 404
    assert foreign.json()["error"]["code"] == missing.json()["error"]["code"] == "VISIT_NOT_FOUND"


async def test_outside_adhoc_notifies_admins_inside_does_not(
    client, admin_headers, employee_headers, outlets, assigned_inside, created_visits
):
    title = "Ad-hoc visit outside assignment"

    def n_alerts():
        with db_cursor() as cur:
            cur.execute("SELECT count(*) AS c FROM notifications WHERE title=%s", (title,))
            return cur.fetchone()["c"]

    before = n_alerts()
    await _adhoc(client, employee_headers, outlets["inside"]["id"], created_visits)
    assert n_alerts() == before
    out = await _adhoc(client, employee_headers, outlets["outside"]["id"], created_visits)
    try:
        assert n_alerts() > before
        notes = (await client.get("/api/v1/notifications/me", headers=admin_headers)).json()
        assert any(n["title"] == title and str(n.get("visit_id")) == out["id"] for n in notes)
    finally:
        with db_cursor(privileged=True) as cur:
            cur.execute("DELETE FROM notifications WHERE title=%s", (title,))


async def test_foreign_customer_and_requirement_return_404(
    client, employee_headers, other_employee_headers, outlets, assigned_inside
):
    cid = outlets["outside"]["id"]
    r = await client.get(f"/api/v1/customers/{cid}", headers=other_employee_headers)
    assert r.status_code == 404 and r.json()["error"]["code"] == "CUSTOMER_NOT_FOUND"

    created = await client.post(
        "/api/v1/requirements",
        json={"customer_id": outlets["inside"]["id"], "product_name": "Widget", "quantity": 1},
        headers=employee_headers,
    )
    assert created.status_code in (200, 201), created.text
    rid = created.json()["id"]
    try:
        foreign = await client.get(f"/api/v1/requirements/{rid}", headers=other_employee_headers)
        missing = await client.get(f"/api/v1/requirements/{uuid.uuid4()}", headers=other_employee_headers)
        assert foreign.status_code == missing.status_code == 404
        assert foreign.json()["error"]["code"] == "REQUIREMENT_NOT_FOUND"
    finally:
        with db_cursor(privileged=True) as cur:
            cur.execute("DELETE FROM customer_requirements WHERE id=%s", (rid,))


async def test_account_deletion_cancels_future_planned_and_notifies_admins(
    client, admin_headers, outlets, created_visits, seeded_world
):
    uid, eid, email = await _make_user("EMPLOYEE", True)
    today = get_ist_now().date()
    plan_id = str(uuid.uuid4())
    try:
        future_id, past_id = str(uuid.uuid4()), str(uuid.uuid4())
        with db_cursor() as cur:
            cur.execute(
                "INSERT INTO monthly_visit_plans (id,employee_id,year,month,created_by) VALUES (%s,%s,%s,%s,%s)",
                (plan_id, eid, today.year, today.month, seeded_world["admin_user_id"]),
            )
            for pid, d in ((future_id, today + timedelta(days=2)), (past_id, today - timedelta(days=2))):
                cur.execute(
                    "INSERT INTO planned_visits (id,monthly_plan_id,employee_id,customer_id,planned_date) "
                    "VALUES (%s,%s,%s,%s,%s)",
                    (pid, plan_id, eid, outlets["inside"]["id"], d),
                )
        pending = await client.post(
            "/api/v1/visits",
            json={"customer_id": outlets["inside"]["id"], "employee_id": eid, "scheduled_at": iso_in(30)},
            headers=admin_headers,
        )
        assert pending.status_code == 201, pending.text
        created_visits.append(pending.json()["id"])

        headers = await auth_headers(client, email, TEST_PASSWORD)
        resp = await client.request(
            "DELETE", "/api/v1/auth/me", json={"password": TEST_PASSWORD, "reason": "x"}, headers=headers
        )
        assert resp.status_code == 200, resp.text

        with db_cursor() as cur:
            cur.execute("SELECT id, status FROM planned_visits WHERE monthly_plan_id=%s", (plan_id,))
            st = {str(r["id"]): r["status"] for r in cur.fetchall()}
            cur.execute("SELECT status FROM visits WHERE id=%s", (pending.json()["id"],))
            vstatus = cur.fetchone()["status"]
        assert st[future_id] == "CANCELLED" and st[past_id] == "PLANNED"
        assert vstatus == "PENDING"  # visits have no CANCELLED status; left for admin reassignment

        notes = (await client.get("/api/v1/notifications/me", headers=admin_headers)).json()
        msg = [n["message"] for n in notes if n["message"].startswith("Reassign visits of deleted employee Delete Me")]
        assert msg and ": 2 visits" in msg[0], msg
    finally:
        with db_cursor(privileged=True) as cur:
            cur.execute("DELETE FROM notifications WHERE message LIKE 'Reassign visits of deleted employee Delete Me%%'")
            cur.execute("DELETE FROM planned_visits WHERE monthly_plan_id=%s", (plan_id,))
            cur.execute("DELETE FROM monthly_visit_plans WHERE id=%s", (plan_id,))
            cur.execute("DELETE FROM visits WHERE employee_id=%s", (eid,))
        _cleanup_user(uid)
