"""Tally -> FieldTrack FOS assignment synchronisation, end to end through the agent's ledger endpoint."""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import delete, func, select

from app.config import settings
from app.core.security import create_access_token, hash_password
from app.database import AsyncSessionLocal
from app.models.customer import Customer
from app.models.employee import Employee
from app.models.employee_customer_assignment import EmployeeCustomerAssignment as ECA
from app.models.tally_debtor_ledger import TallyDebtorLedger
from app.models.tally_fos import FosAssignmentAudit, FosSyncRun, TallyFosGroup
from app.models.user import Role, User
from app.repositories.customer_repo import CustomerRepository
from app.services import fos_sync_service as svc
from tests.conftest import requires_db
from tests.test_tally_v2_sync import _post, env as tally_env  # noqa: F401  (agent fixture)

pytestmark = [requires_db, pytest.mark.asyncio]


@pytest_asyncio.fixture
async def fx(tally_env, monkeypatch):
    """Two FOS employees with unique names, one outlet ledger, tagged Tally groups. Sync enabled (apply)."""
    monkeypatch.setattr(settings, "tally_fos_sync_enabled", True)
    monkeypatch.setattr(settings, "tally_fos_legacy_policy", "REPORT_ONLY")
    tag = tally_env["tag"]
    async with AsyncSessionLocal() as s:
        users, emps = [], {}
        for n in ("zorvak", "quillan"):
            u = User(email=f"{n}_{tag}@fieldtrack.test", password_hash=hash_password("x"), role=Role.EMPLOYEE, is_active=True)
            s.add(u)
            users.append(u)
        await s.flush()
        for n, u in zip(("zorvak", "quillan"), users):
            e = Employee(user_id=u.id, full_name=f"{n.title()}{tag}")
            s.add(e)
            emps[n] = e
        await s.flush()
        await s.commit()
        ids = {"zorvak": emps["zorvak"].id, "quillan": emps["quillan"].id}
        uids = [u.id for u in users]
    out = {**tally_env, "emp": ids, "uids": uids,
           "g": {"z": f"Zorvak{tag} Usha", "q": f"Quillan{tag} (ZBR)", "dist": f"Sundry Debtors Fos{tag}", "new": f"Fresh Group {tag}"}}
    yield out
    async with AsyncSessionLocal() as s:
        cids = (await s.execute(select(TallyDebtorLedger.customer_id).where(TallyDebtorLedger.tally_guid.like(f"FOS-{tag}-%")))).scalars().all()
        if cids:
            await s.execute(delete(FosAssignmentAudit).where(FosAssignmentAudit.customer_id.in_(cids)))
            await s.execute(delete(ECA).where(ECA.customer_id.in_(cids)))
        await s.execute(delete(FosAssignmentAudit).where(FosAssignmentAudit.tally_group.like(f"%{tag}%")))
        await s.execute(delete(TallyFosGroup).where(TallyFosGroup.group_name.like(f"%{tag}%")))
        await s.execute(delete(FosSyncRun).where(FosSyncRun.trigger.in_(("ADMIN", "GROUP_MAPPING")), FosSyncRun.triggered_by.in_(out["uids"])))
        await s.commit()


def led(fx, n, group):
    return {"guid": f"FOS-{fx['tag']}-{n}", "name": f"Fos Outlet {fx['tag']} {n}", "is_debtor": True, "parent": group,
            "opening_balance": "0", "closing_balance": "0"}


async def push(fx, *ledgers):
    r = await _post(fx, "ledgers", {"ledgers": list(ledgers)})
    assert r["failed_count"] == 0, r
    return r


async def customer_of(fx, n) -> Customer:
    async with AsyncSessionLocal() as s:
        return (await s.execute(select(Customer).where(Customer.tally_guid == f"FOS-{fx['tag']}-{n}"))).scalar_one()


async def rows_of(cid):
    async with AsyncSessionLocal() as s:
        return (await s.execute(select(ECA).where(ECA.customer_id == cid))).scalars().all()


async def audits_of(cid):
    async with AsyncSessionLocal() as s:
        return (await s.execute(select(FosAssignmentAudit).where(FosAssignmentAudit.customer_id == cid)
                                .order_by(FosAssignmentAudit.created_at))).scalars().all()


async def group_row(name) -> TallyFosGroup:
    async with AsyncSessionLocal() as s:
        return (await s.execute(select(TallyFosGroup).where(TallyFosGroup.group_key == " ".join(name.lower().split())))).scalar_one()


async def admin_user(fx):
    async with AsyncSessionLocal() as s:
        return (await s.execute(select(User).where(User.email == f"admin_v2_{fx['tag']}@fieldtrack.test"))).scalar_one()


async def map_group(fx, name, *, employee=None, not_fos=False):
    g = await group_row(name)
    body = {"employee_id": str(fx["emp"][employee])} if employee else {"not_fos": not_fos}
    r = await fx["c"].put(f"/api/v1/fos-assignments/groups/{g.id}", json=body, headers=fx["admin_h"])
    assert r.status_code == 200, r.text
    return r.json()


# --------------------------------------------------------------------------------------------------------------------

async def test_groups_are_discovered_unmapped_with_a_suggestion_and_nothing_is_assigned(fx):
    await push(fx, led(fx, 1, fx["g"]["z"]))
    g = await group_row(fx["g"]["z"])
    assert g.status == "UNMAPPED" and g.suggested_employee_id == fx["emp"]["zorvak"]
    assert "exactly" in g.suggestion_basis
    c = await customer_of(fx, 1)
    assert await rows_of(c.id) == []          # a suggestion is never applied by itself
    assert c.fos_status == "UNMAPPED_GROUP"


async def test_disabled_flag_changes_no_assignment(fx, monkeypatch):
    await push(fx, led(fx, 1, fx["g"]["z"]))
    await map_group(fx, fx["g"]["z"], employee="zorvak")
    c = await customer_of(fx, 1)
    assert [r.employee_id for r in await rows_of(c.id)] == [fx["emp"]["zorvak"]]
    monkeypatch.setattr(settings, "tally_fos_sync_enabled", False)
    await push(fx, led(fx, 2, fx["g"]["z"]))
    c2 = await customer_of(fx, 2)
    assert await rows_of(c2.id) == [] and c2.fos_status is None


async def test_mapping_a_group_assigns_its_outlets_with_audit(fx):
    await push(fx, led(fx, 1, fx["g"]["z"]), led(fx, 2, fx["g"]["z"]))
    await map_group(fx, fx["g"]["z"], employee="zorvak")
    for n in (1, 2):
        c = await customer_of(fx, n)
        rows = await rows_of(c.id)
        assert len(rows) == 1 and rows[0].employee_id == fx["emp"]["zorvak"] and rows[0].source == "TALLY"
        assert rows[0].tally_group == fx["g"]["z"] and rows[0].tally_ledger_guid == f"FOS-{fx['tag']}-{n}"
        assert c.fos_status == "ASSIGNED" and c.fos_synced_at is not None
        a = (await audits_of(c.id))[-1]
        assert (a.action, a.source, a.result, a.previous_fos, a.new_fos) == ("ASSIGNED", "TALLY", "APPLIED", None, f"Zorvak{fx['tag']}")
        assert a.tally_group == fx["g"]["z"] and a.tally_ledger_guid == f"FOS-{fx['tag']}-{n}" and a.run_id is not None


async def test_accountant_moves_the_ledger_to_another_fos_group(fx):
    await push(fx, led(fx, 1, fx["g"]["z"]))
    await map_group(fx, fx["g"]["z"], employee="zorvak")
    await map_group(fx, fx["g"]["q"] if False else fx["g"]["z"], employee="zorvak")  # idempotent re-map
    await push(fx, led(fx, 1, fx["g"]["q"]))
    await map_group(fx, fx["g"]["q"], employee="quillan")
    c = await customer_of(fx, 1)
    rows = await rows_of(c.id)
    assert [r.employee_id for r in rows] == [fx["emp"]["quillan"]]
    a = [x for x in await audits_of(c.id) if x.action == "CHANGED"]
    assert len(a) == 1 and a[0].previous_fos == f"Zorvak{fx['tag']}" and a[0].new_fos == f"Quillan{fx['tag']}"


async def test_ledger_synced_into_an_already_mapped_group_is_assigned_straight_away(fx):
    await push(fx, led(fx, 1, fx["g"]["z"]))
    await map_group(fx, fx["g"]["z"], employee="zorvak")
    await push(fx, led(fx, 2, fx["g"]["z"]))      # a new outlet appears in Raunak-like group in Tally
    assert [r.employee_id for r in await rows_of((await customer_of(fx, 2)).id)] == [fx["emp"]["zorvak"]]


async def test_moving_to_a_non_fos_group_removes_the_assignment(fx):
    await push(fx, led(fx, 1, fx["g"]["z"]), led(fx, 9, fx["g"]["dist"]))
    await map_group(fx, fx["g"]["z"], employee="zorvak")
    await map_group(fx, fx["g"]["dist"], not_fos=True)
    await push(fx, led(fx, 1, fx["g"]["dist"]))
    c = await customer_of(fx, 1)
    assert await rows_of(c.id) == [] and c.fos_status == "UNASSIGNED"
    a = [x for x in await audits_of(c.id) if x.action == "REMOVED"]
    assert len(a) == 1 and a[0].previous_fos == f"Zorvak{fx['tag']}" and a[0].new_fos is None


async def test_unmapped_destination_keeps_the_existing_assignment(fx):
    await push(fx, led(fx, 1, fx["g"]["z"]))
    await map_group(fx, fx["g"]["z"], employee="zorvak")
    await push(fx, led(fx, 1, fx["g"]["new"]))   # moved to a group nobody has mapped yet
    c = await customer_of(fx, 1)
    assert [r.employee_id for r in await rows_of(c.id)] == [fx["emp"]["zorvak"]]
    assert c.fos_status == "UNMAPPED_GROUP"
    assert any(x.action == "UNMAPPED_GROUP" and x.result == "FLAGGED" for x in await audits_of(c.id))


async def test_sync_is_idempotent_and_does_not_duplicate_audit_rows(fx):
    await push(fx, led(fx, 1, fx["g"]["z"]))
    await map_group(fx, fx["g"]["z"], employee="zorvak")
    c = await customer_of(fx, 1)
    before = len(await audits_of(c.id))
    for _ in range(3):
        await push(fx, led(fx, 1, fx["g"]["z"]))
    async with AsyncSessionLocal() as s:
        run, _ = await svc.run_sync(s, trigger="CLI", dry_run=False, customer_ids=[c.id])
        await s.commit()
    assert len(await rows_of(c.id)) == 1 and len(await audits_of(c.id)) == before
    assert run.summary["counts"].get("unchanged") == 1


async def test_legacy_assignment_matching_tally_is_adopted_and_a_conflicting_one_is_kept(fx):
    await push(fx, led(fx, 1, fx["g"]["z"]), led(fx, 2, fx["g"]["z"]))
    a = await admin_user(fx)
    async with AsyncSessionLocal() as s:
        for n, emp in ((1, "zorvak"), (2, "quillan")):
            c = await customer_of(fx, n)
            s.add(ECA(employee_id=fx["emp"][emp], customer_id=c.id, created_by=a.id, source="LEGACY"))
        await s.commit()
    await map_group(fx, fx["g"]["z"], employee="zorvak")
    c1, c2 = await customer_of(fx, 1), await customer_of(fx, 2)
    r1 = await rows_of(c1.id)
    assert len(r1) == 1 and r1[0].source == "TALLY" and r1[0].employee_id == fx["emp"]["zorvak"]
    assert (await audits_of(c1.id))[-1].action == "ADOPTED"
    r2 = await rows_of(c2.id)
    assert [(r.employee_id, r.source) for r in r2] == [(fx["emp"]["quillan"], "LEGACY")]   # untouched
    assert c2.fos_status == "CONFLICT"
    # once approved (TALLY_WINS) Tally replaces it, with an audit trail
    async with AsyncSessionLocal() as s:
        await svc.run_sync(s, trigger="CLI", dry_run=False, customer_ids=[c2.id], policy="TALLY_WINS")
        await s.commit()
    assert [(r.employee_id, r.source) for r in await rows_of(c2.id)] == [(fx["emp"]["zorvak"], "TALLY")]
    assert (await audits_of(c2.id))[-1].action == "CHANGED"


async def test_prospect_outlet_without_a_tally_ledger_is_never_touched(fx):
    a = await admin_user(fx)
    async with AsyncSessionLocal() as s:
        c = Customer(name=f"Prospect {fx['tag']}", contact_number="9000000000", address="x", created_by=a.id)
        s.add(c)
        await s.flush()
        s.add(ECA(employee_id=fx["emp"]["zorvak"], customer_id=c.id, created_by=a.id))
        await s.commit()
        cid = c.id
    async with AsyncSessionLocal() as s:
        run, _ = await svc.run_sync(s, trigger="CLI", dry_run=False, customer_ids=[cid])
        await s.commit()
    assert [(r.employee_id, r.source) for r in await rows_of(cid)] == [(fx["emp"]["zorvak"], "APP")]
    async with AsyncSessionLocal() as s:
        assert (await s.get(Customer, cid)).fos_status == "NO_TALLY"
        await s.execute(delete(ECA).where(ECA.customer_id == cid))
        await s.execute(delete(Customer).where(Customer.id == cid))
        await s.commit()


async def test_dry_run_reports_without_writing_and_apply_needs_the_flag(fx, monkeypatch):
    await push(fx, led(fx, 1, fx["g"]["z"]))
    g = await group_row(fx["g"]["z"])
    c = await customer_of(fx, 1)
    monkeypatch.setattr(settings, "tally_fos_sync_enabled", False)
    r = await fx["c"].post("/api/v1/fos-assignments/sync", json={"dry_run": False}, headers=fx["admin_h"])
    assert r.status_code == 409
    # map while disabled: mapping is stored, no assignment written
    r = await fx["c"].put(f"/api/v1/fos-assignments/groups/{g.id}", json={"employee_id": str(fx["emp"]["zorvak"])}, headers=fx["admin_h"])
    assert r.status_code == 200
    assert await rows_of(c.id) == []
    rep = (await fx["c"].get("/api/v1/fos-assignments/reconciliation", headers=fx["admin_h"])).json()
    assert any(row["customer_id"] == str(c.id) for row in rep["rows"]["new_from_tally"])
    assert await rows_of(c.id) == []             # the report wrote nothing
    d = await fx["c"].post("/api/v1/fos-assignments/sync", json={"dry_run": True}, headers=fx["admin_h"])
    assert d.status_code == 200 and d.json()["dry_run"] is True and await rows_of(c.id) == []


async def test_reconciliation_proposes_mappings_from_existing_assignments(fx):
    await push(fx, led(fx, 1, fx["g"]["z"]), led(fx, 2, fx["g"]["z"]))
    a = await admin_user(fx)
    async with AsyncSessionLocal() as s:
        for n in (1, 2):
            s.add(ECA(employee_id=fx["emp"]["zorvak"], customer_id=(await customer_of(fx, n)).id, created_by=a.id, source="LEGACY"))
        await s.commit()
    rep = (await fx["c"].get("/api/v1/fos-assignments/reconciliation", headers=fx["admin_h"])).json()
    prop = [p for p in rep["proposed_mappings"] if p["group"] == fx["g"]["z"]]
    assert prop and prop[0]["employee_id"] == str(fx["emp"]["zorvak"]) and prop[0]["existing_assignments"] == 2
    assert fx["g"]["z"] in rep["unmatched_salesperson_groups"]


async def test_admin_api_lists_filters_and_only_put_edits_an_outlet(fx):
    await push(fx, led(fx, 1, fx["g"]["z"]), led(fx, 2, fx["g"]["new"]))
    await map_group(fx, fx["g"]["z"], employee="zorvak")
    c1, c2 = await customer_of(fx, 1), await customer_of(fx, 2)
    h, c = fx["admin_h"], fx["c"]
    mine = (await c.get("/api/v1/fos-assignments/outlets", params={"employee_id": str(fx["emp"]["zorvak"]), "limit": 200}, headers=h)).json()
    assert str(c1.id) in {i["id"] for i in mine["items"]} and str(c2.id) not in {i["id"] for i in mine["items"]}
    item = next(i for i in mine["items"] if i["id"] == str(c1.id))
    assert item["fos"][0]["name"] == f"Zorvak{fx['tag']}" and item["tally_group"] == fx["g"]["z"] and item["fos_synced_at"]
    un = (await c.get("/api/v1/fos-assignments/outlets", params={"assignment": "unassigned", "search": f"Fos Outlet {fx['tag']}"}, headers=h)).json()
    assert [i["id"] for i in un["items"]] == [str(c2.id)] and un["items"][0]["fos_status"] == "UNMAPPED_GROUP"
    st = (await c.get("/api/v1/fos-assignments/outlets", params={"status": "UNMAPPED_GROUP", "search": f"Fos Outlet {fx['tag']}"}, headers=h)).json()
    assert st["total"] == 1
    summary = (await c.get("/api/v1/fos-assignments/summary", headers=h)).json()
    assert summary["sync_enabled"] is True and summary["total_outlets"] >= 2
    assert (await c.get("/api/v1/fos-assignments/audit", params={"customer_id": str(c1.id)}, headers=h)).json()[0]["action"] == "ASSIGNED"
    # Release 3.3: the per-outlet FOS is set only by PUT (Change FOS, tested below); no other verb exists.
    for method, url in (("post", f"/api/v1/fos-assignments/outlets/{c1.id}"),
                        ("patch", f"/api/v1/fos-assignments/outlets/{c1.id}"), ("delete", f"/api/v1/fos-assignments/outlets/{c1.id}")):
        assert (await getattr(c, method)(url, headers=h)).status_code in (404, 405)


async def test_only_admins_can_use_the_fos_api(fx):
    tok = create_access_token(subject=str(fx["uids"][0]), role=Role.EMPLOYEE.value)
    h = {"Authorization": f"Bearer {tok}"}
    for url in ("/summary", "/outlets", "/groups", "/reconciliation", "/audit"):
        assert (await fx["c"].get(f"/api/v1/fos-assignments{url}", headers=h)).status_code == 403
    assert (await fx["c"].post("/api/v1/fos-assignments/sync", json={}, headers=h)).status_code == 403
    assert (await fx["c"].get("/api/v1/fos-assignments/summary")).status_code in (401, 403)


async def test_mapping_validation(fx):
    await push(fx, led(fx, 1, fx["g"]["z"]))
    g = await group_row(fx["g"]["z"])
    r = await fx["c"].put(f"/api/v1/fos-assignments/groups/{g.id}", json={"employee_id": str(fx["emp"]["zorvak"]), "not_fos": True}, headers=fx["admin_h"])
    assert r.status_code == 422
    r = await fx["c"].put(f"/api/v1/fos-assignments/groups/{g.id}", json={"employee_id": str(uuid.uuid4())}, headers=fx["admin_h"])
    assert r.status_code == 422
    r = await fx["c"].put(f"/api/v1/fos-assignments/groups/{uuid.uuid4()}", json={"not_fos": True}, headers=fx["admin_h"])
    assert r.status_code == 422
    # un-mapping returns to UNMAPPED and keeps whatever is assigned (nothing is silently dropped)
    await map_group(fx, fx["g"]["z"], employee="zorvak")
    r = await fx["c"].put(f"/api/v1/fos-assignments/groups/{g.id}", json={}, headers=fx["admin_h"])
    assert r.json()["status"] == "UNMAPPED"
    assert len(await rows_of((await customer_of(fx, 1)).id)) == 1


async def test_ledger_sync_still_succeeds_when_the_fos_step_fails(fx, monkeypatch):
    async def boom(*a, **k):
        raise RuntimeError("fos step exploded")
    monkeypatch.setattr(svc, "run_sync", boom)
    r = await _post(fx, "ledgers", {"ledgers": [led(fx, 7, fx["g"]["z"])]})
    assert r["failed_count"] == 0
    assert (await customer_of(fx, 7)).tally_is_debtor is True


async def test_employee_scope_follows_assignment_when_assigned_only(fx, monkeypatch):
    """Home territory used to expose every outlet of the territory; assigned-only scope limits it to assignments."""
    await push(fx, led(fx, 1, fx["g"]["z"]), led(fx, 2, fx["g"]["new"]))
    await map_group(fx, fx["g"]["z"], employee="zorvak")
    c1, c2 = await customer_of(fx, 1), await customer_of(fx, 2)
    async with AsyncSessionLocal() as s:  # put both outlets in one territory and make it the employee's home
        from app.models.territory import Territory
        t = Territory(name=f"FOS Terr {fx['tag']}")
        s.add(t)
        await s.flush()
        for cid in (c1.id, c2.id):
            (await s.get(Customer, cid)).territory_id = t.id
        (await s.get(Employee, fx["emp"]["zorvak"])).territory_id = t.id
        await s.commit()
        tid = t.id
    try:
        async def visible():
            async with AsyncSessionLocal() as s:
                items, _ = await CustomerRepository(s).list_accessible_by_employee(
                    fx["emp"]["zorvak"], home_territory_id=tid, limit=200)
                return {i.id for i in items}
        monkeypatch.setattr(settings, "fos_assigned_only_scope", False)
        assert {c1.id, c2.id} <= await visible()          # existing behaviour: whole home territory
        monkeypatch.setattr(settings, "fos_assigned_only_scope", True)
        seen = await visible()
        assert c1.id in seen and c2.id not in seen          # assigned only
        # the FOS changes in Tally: the old employee loses it, the new one gets it
        await push(fx, led(fx, 1, fx["g"]["q"]))
        await map_group(fx, fx["g"]["q"], employee="quillan")
        assert c1.id not in await visible()
        async with AsyncSessionLocal() as s:
            items, _ = await CustomerRepository(s).list_accessible_by_employee(fx["emp"]["quillan"], limit=200)
            assert c1.id in {i.id for i in items}
    finally:
        async with AsyncSessionLocal() as s:
            for cid in (c1.id, c2.id):
                (await s.get(Customer, cid)).territory_id = None
            (await s.get(Employee, fx["emp"]["zorvak"])).territory_id = None
            from app.models.territory import Territory
            await s.execute(delete(Territory).where(Territory.name == f"FOS Terr {fx['tag']}"))
            await s.commit()


# ---------------------------------------------------------------------------------------------------------------
# Release 3.3: admin per-outlet "Change FOS" and its interplay with the Tally sync
# ---------------------------------------------------------------------------------------------------------------
async def _change(fx, cid, employee, expected=None, key=None):
    body = {"employee_id": str(fx["emp"][employee])}
    if expected is not None:
        body["expected_employee_ids"] = [str(fx["emp"][e]) for e in expected]
    hdr = dict(fx["admin_h"], **({"Idempotency-Key": key} if key else {}))
    return await fx["c"].put(f"/api/v1/fos-assignments/outlets/{cid}", json=body, headers=hdr)


async def _move_of(cid):
    from app.models.tally_fos import FosLedgerMove
    async with AsyncSessionLocal() as s:
        return (await s.execute(select(FosLedgerMove).where(FosLedgerMove.customer_id == cid)
                                .order_by(FosLedgerMove.requested_at.desc()))).scalars().first()


async def test_admin_change_is_audited_held_until_tally_moves_the_ledger_then_confirmed(fx):
    await push(fx, led(fx, 1, fx["g"]["z"]), led(fx, 2, fx["g"]["q"]))
    await map_group(fx, fx["g"]["z"], employee="zorvak")
    await map_group(fx, fx["g"]["q"], employee="quillan")
    c1 = await customer_of(fx, 1)
    assert {r.employee_id for r in await rows_of(c1.id)} == {fx["emp"]["zorvak"]}

    r = await _change(fx, c1.id, "quillan", expected=["zorvak"], key=f"k-{fx['tag']}")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "PENDING_TALLY" and body["to_group"] == fx["g"]["q"] and body["from_group"] == fx["g"]["z"]
    assert body["writeback_status"] == "NOT_SENT", "write-back is off: the accountant moves the ledger"
    rows = await rows_of(c1.id)
    assert [(x.employee_id, x.source) for x in rows] == [(fx["emp"]["quillan"], "ADMIN")]
    a = [x for x in await audits_of(c1.id) if x.action == "ADMIN_CHANGE"]
    assert len(a) == 1 and a[0].previous_employee_id == fx["emp"]["zorvak"] and a[0].new_employee_id == fx["emp"]["quillan"]
    assert a[0].source == "ADMIN" and f"admin_v2_{fx['tag']}@fieldtrack.test" in a[0].detail and a[0].created_at

    # A retry with the same key changes nothing twice.
    again = await _change(fx, c1.id, "quillan", key=f"k-{fx['tag']}")
    assert again.status_code == 200 and again.json()["id"] == body["id"]
    assert len([x for x in await audits_of(c1.id) if x.action == "ADMIN_CHANGE"]) == 1

    # Tally still has the ledger in Zorvak's group: the sync keeps the admin's FOS (no loop, no silent revert).
    await push(fx, led(fx, 1, fx["g"]["z"]))
    assert [(x.employee_id, x.source) for x in await rows_of(c1.id)] == [(fx["emp"]["quillan"], "ADMIN")]
    assert (await customer_of(fx, 1)).fos_status == "ADMIN_PENDING"
    assert (await _move_of(c1.id)).status == "PENDING_TALLY"

    # The accountant moves the ledger to Quillan's group: confirmed, the sync owns the row again.
    await push(fx, led(fx, 1, fx["g"]["q"]))
    assert (await _move_of(c1.id)).status == "CONFIRMED"
    assert [(x.employee_id, x.source) for x in await rows_of(c1.id)] == [(fx["emp"]["quillan"], "TALLY")]
    assert any(x.action == "TALLY_CONFIRMED" for x in await audits_of(c1.id))
    # Outlet 2 (Quillan's own) was never touched.
    c2 = await customer_of(fx, 2)
    assert [(x.employee_id, x.source) for x in await rows_of(c2.id)] == [(fx["emp"]["quillan"], "TALLY")]


async def test_tally_moving_the_ledger_elsewhere_is_a_flagged_conflict_never_an_overwrite(fx):
    await push(fx, led(fx, 1, fx["g"]["z"]), led(fx, 2, fx["g"]["q"]), led(fx, 3, fx["g"]["new"]))
    await map_group(fx, fx["g"]["z"], employee="zorvak")
    await map_group(fx, fx["g"]["q"], employee="quillan")
    await map_group(fx, fx["g"]["new"], employee="zorvak")
    c1 = await customer_of(fx, 1)
    assert (await _change(fx, c1.id, "quillan")).status_code == 200
    # Meanwhile the accountant puts the ledger in another Zorvak group: Tally disagrees with the admin.
    await push(fx, led(fx, 1, fx["g"]["new"]))
    assert [(x.employee_id, x.source) for x in await rows_of(c1.id)] == [(fx["emp"]["quillan"], "ADMIN")]
    mv = await _move_of(c1.id)
    assert mv.status == "CONFLICT" and (await customer_of(fx, 1)).fos_status == "CONFLICT"
    flagged = [x for x in await audits_of(c1.id) if x.action == "CONFLICT" and x.result == "FLAGGED"]
    assert len(flagged) == 1
    await push(fx, led(fx, 1, fx["g"]["new"]))          # flagged once, not on every sync
    assert len([x for x in await audits_of(c1.id) if x.action == "CONFLICT"]) == 1
    # The admin decides for Tally: Tally's FOS applies, audited.
    r = await fx["c"].post(f"/api/v1/fos-assignments/moves/{mv.id}/resolve", json={"keep": "TALLY"}, headers=fx["admin_h"])
    assert r.status_code == 200 and r.json()["status"] == "CANCELLED"
    assert [(x.employee_id, x.source) for x in await rows_of(c1.id)] == [(fx["emp"]["zorvak"], "TALLY")]
    assert any(x.action == "CONFLICT_RESOLVED" for x in await audits_of(c1.id))


async def test_change_fos_guards_stale_unchanged_and_role(fx):
    await push(fx, led(fx, 1, fx["g"]["z"]))
    await map_group(fx, fx["g"]["z"], employee="zorvak")
    c1 = await customer_of(fx, 1)
    r = await _change(fx, c1.id, "quillan", expected=["quillan"])
    assert r.status_code == 409 and r.json()["error"]["code"] == "FOS_CHANGED_MEANWHILE"
    r = await _change(fx, c1.id, "zorvak")
    assert r.status_code == 409 and r.json()["error"]["code"] == "FOS_UNCHANGED"
    r = await fx["c"].put(f"/api/v1/fos-assignments/outlets/{c1.id}", json={"employee_id": str(uuid.uuid4())}, headers=fx["admin_h"])
    assert r.status_code == 422
    tok = create_access_token(subject=str(fx["uids"][0]), role=Role.EMPLOYEE.value)
    r = await fx["c"].put(f"/api/v1/fos-assignments/outlets/{c1.id}", json={"employee_id": str(fx["emp"]["quillan"])},
                          headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 403
    assert {x.employee_id for x in await rows_of(c1.id)} == {fx["emp"]["zorvak"]}, "nothing changed"
    # The agent write-back endpoint offers nothing while write-back is off.
    assert (await fx["c"].get("/api/v1/integrations/tally/fos-moves/pending", headers=fx["agent_h"])).json() == {"enabled": False, "moves": []}


def test_target_group_is_never_guessed():
    from app.services.fos_outlet_edit import pick_target_group
    assert pick_target_group(["Raunak Usha"], None) == "Raunak Usha"
    assert pick_target_group(["Raunak Usha", "Raunak ZBR", "Raunak VU"], "Zebronics") == "Raunak ZBR"
    assert pick_target_group(["Raunak Usha", "Raunak ZBR"], "Oppo") is None
    assert pick_target_group(["Raunak Usha", "Raunak ZBR"], None) is None
    assert pick_target_group([], "USHA") is None
