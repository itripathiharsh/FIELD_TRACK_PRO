"""
Release 2.1.0: physical outlet <-> Tally ledgers, outlet-mapping API, agent health.
(CONTRACTS_2.1.0 C1-C5; tests M1, M3-M10 at backend level.)
"""
from __future__ import annotations

import io
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest
import pytest_asyncio
from openpyxl import Workbook
from sqlalchemy import select, text

from app.core.security import create_access_token, hash_password
from app.database import AsyncSessionLocal
from app.models.customer import Customer
from app.models.customer_brand import CustomerBrand
from app.models.employee import Employee
from app.models.employee_customer_assignment import EmployeeCustomerAssignment
from app.models.invoice import Invoice
from app.models.sync_agent import SyncAgent
from app.models.tally_debtor_ledger import TallyDebtorLedger
from app.models.user import Role, User
from app.services.tally_sync_service import compute_sync_state
from tests.conftest import requires_db
from tests.test_tally_v2_sync import _post, _snapshot, _vch, env  # noqa: F401  (env is a fixture)

D = Decimal
AS_OF = "2026-11-16"  # same as test_tally_v2_sync: never newer than the suite's other bills snapshots


async def _ledger(guid):
    async with AsyncSessionLocal() as s:
        return (await s.execute(select(TallyDebtorLedger).where(TallyDebtorLedger.tally_guid == guid))).scalar_one()


async def _super_headers(tag):
    async with AsyncSessionLocal() as s:
        u = User(email=f"super_v21_{tag}@fieldtrack.test", password_hash=hash_password("Admin123!"),
                 role=Role.SUPER_ADMIN, is_active=True)
        s.add(u)
        await s.commit()
        return u.id, {"Authorization": f"Bearer {create_access_token(subject=str(u.id), role=Role.SUPER_ADMIN.value)}"}


async def _deactivate(uid):
    """Never leave an extra administrator behind: the last-admin tests count active admins, and the
    Super Admin bootstrap refuses while ANY SUPER_ADMIN row exists (active or not), so the test
    Super Admin is demoted as well as deactivated."""
    async with AsyncSessionLocal() as s:
        u = await s.get(User, uid)
        u.is_active = False
        if u.role == Role.SUPER_ADMIN:
            u.role = Role.ADMIN
        await s.commit()


def _two(env, **kw):
    t = env["tag"]
    return [
        {"guid": f"A-{t}", "name": f"Advik {t} (Oppo)", "is_debtor": True, "parent": "Sundry Debtors", "brand": "Oppo",
         "opening_balance": "-1000.00", "closing_balance": "-6000.00", "gst_number": f"09AAA{t[:5]}", **kw},
        {"guid": f"B-{t}", "name": f"Advik {t} (Philips)", "is_debtor": True, "parent": "Sundry Debtors",
         "brand": "Philips", "opening_balance": "-500.00", "closing_balance": "-2500.00"},
    ]


async def _shop(env):
    """Two brand ledgers of one shop, each with an invoice and an open bill, then B linked to A."""
    t = env["tag"]
    led = _two(env)
    await _snapshot(env, led)
    await _post(env, "vouchers", {"vouchers": [
        _vch(env, "IA", "Oppo", "Sales", [{"ledger_name": led[0]["name"], "ledger_guid": led[0]["guid"],
              "amount": "-5000", "brand": "Oppo",
              "bill_allocations": [{"name": f"BA-{t}", "bill_type": "New Ref", "amount": "-5000"}]}], number=f"BA-{t}"),
        _vch(env, "IB", "Philips", "Sales", [{"ledger_name": led[1]["name"], "ledger_guid": led[1]["guid"],
              "amount": "-2000", "bill_allocations": [{"name": f"BB-{t}", "bill_type": "New Ref", "amount": "-2000"}]}],
             number=f"BB-{t}"),
    ]})
    await _post(env, "bills", {"snapshot_id": f"B-{uuid.uuid4().hex}", "as_of_date": AS_OF,
                               "is_final_chunk": True, "bills": [
        {"ledger_name": led[0]["name"], "ledger_guid": led[0]["guid"], "bill_name": f"BA-{t}",
         "bill_date": "2026-10-17", "pending_amount": "-5000"},
        {"ledger_name": led[1]["name"], "ledger_guid": led[1]["guid"], "bill_name": f"BB-{t}",
         "bill_date": "2026-11-16", "pending_amount": "-2000"},
    ]})
    a, b = await _ledger(f"A-{t}"), await _ledger(f"B-{t}")
    return led, a, b


# ---------------------------------------------------------------------------
# M1: migration head, backfill, downgrade guard
# ---------------------------------------------------------------------------

@requires_db
@pytest.mark.asyncio
async def test_migration_head_backfill_and_downgrade_guard():
    import importlib.util, pathlib
    path = next(pathlib.Path("alembic/versions").glob("h1b2c3d4e5f6_*.py"))
    spec = importlib.util.spec_from_file_location("mig_h1", path)
    mig = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mig)
    async with AsyncSessionLocal() as s:
        # h1b2c3d4e5f6 is applied; i2c3d4e5f6a7 (payments.tally_bill_allocations, additive) may follow it.
        assert (await s.execute(text("SELECT version_num FROM alembic_version"))).scalar() in ("h1b2c3d4e5f6", "i2c3d4e5f6a7")
        # The migration's 1:1 backfill gives every customer holding a Tally GUID its ledger (idempotent);
        # customers created later by the v1 sync get theirs lazily on the first v2 touch.
        await s.execute(text(mig.BACKFILL_LEDGERS_SQL))
        await s.execute(text(mig.BACKFILL_LEDGERS_SQL))  # idempotent
        missing = (await s.execute(text(
            "SELECT count(*) FROM customers c WHERE c.tally_guid IS NOT NULL AND NOT EXISTS "
            "(SELECT 1 FROM tally_debtor_ledgers l WHERE l.tally_guid = c.tally_guid)"))).scalar()
        assert missing == 0
        await s.rollback()
        two_primaries = (await s.execute(text(
            "SELECT count(*) FROM (SELECT customer_id FROM tally_debtor_ledgers WHERE is_primary "
            "GROUP BY 1 HAVING count(*) > 1) x"))).scalar()
        assert two_primaries == 0
    async with AsyncSessionLocal() as s:  # no merge present here -> guard passes (rolled back)
        tag = uuid.uuid4().hex[:6]
        uid = (await s.execute(select(User.id).limit(1))).scalar()
        a = Customer(name=f"guard A {tag}", address="", contact_number="", created_by=uid)
        b = Customer(name=f"guard B {tag}", address="", contact_number="", created_by=uid)
        s.add_all([a, b])
        await s.flush()
        b.merged_into_customer_id = a.id
        await s.flush()
        with pytest.raises(Exception) as ex:
            await s.execute(text(mig.DOWNGRADE_GUARD_SQL))
        assert "downgrade refused" in str(ex.value)
        await s.rollback()


# ---------------------------------------------------------------------------
# Sync, position, history, customers API with a linked shop (M3, M4, M5)
# ---------------------------------------------------------------------------

@requires_db
@pytest.mark.asyncio
async def test_linked_shop_sync_position_history_and_customers_api(env):
    t = env["tag"]
    led, a, b = await _shop(env)
    assert a.customer_id != b.customer_id and a.is_primary and b.is_primary
    async with AsyncSessionLocal() as s:
        inv_b = (await s.execute(select(Invoice).where(Invoice.source_reference == f"IB-{t}"))).scalar_one()
    assert inv_b.tally_debtor_ledger_id == b.id and inv_b.brand == "Philips"  # ledger brand used for a brandless line

    r = await env["c"].post("/api/v1/outlet-mapping/link", json={"ledger_id": str(b.id), "target_customer_id":
                                                                  str(a.customer_id)}, headers=env["admin_h"])
    assert r.status_code == 200, r.text
    assert r.json()["action"] == "LINK"
    b2 = await _ledger(f"B-{t}")
    assert b2.customer_id == a.customer_id and not b2.is_primary and b2.mapping_status == "CONFIRMED"
    async with AsyncSessionLocal() as s:
        old_b = await s.get(Customer, b.customer_id)
        assert old_b.merged_into_customer_id == a.customer_id  # kept, hidden
        assert (await s.get(Invoice, inv_b.id)).customer_id == a.customer_id

    # M5: a new voucher on the secondary ledger lands on the physical outlet
    await _post(env, "vouchers", {"vouchers": [
        _vch(env, "IB2", "Philips", "Sales", [{"ledger_name": led[1]["name"], "ledger_guid": led[1]["guid"],
              "amount": "-300"}], number=f"BB2-{t}")]})
    async with AsyncSessionLocal() as s:
        inv = (await s.execute(select(Invoice).where(Invoice.source_reference == f"IB2-{t}"))).scalar_one()
    assert inv.customer_id == a.customer_id and inv.tally_debtor_ledger_id == b.id

    # Ledger snapshot again (balances updated): secondary ledger never overwrites the outlet's name
    led2 = _two(env)
    led2[1]["closing_balance"] = "-2800.00"
    await _snapshot(env, led2)
    async with AsyncSessionLocal() as s:
        outlet = await s.get(Customer, a.customer_id)
        assert outlet.name == f"Advik {t} (Oppo)" and outlet.tally_closing_balance == D("-6000.00")

    acc = await env["c"].get(f"/api/v1/customers/{a.customer_id}/account", headers=env["admin_h"])
    assert acc.status_code == 200, acc.text
    j = acc.json()
    ls = {x["name"]: x for x in j["ledgers"]}
    assert set(ls) == {f"Advik {t} (Oppo)", f"Advik {t} (Philips)"}
    assert D(ls[f"Advik {t} (Oppo)"]["closing_balance"]) == D("6000.00")
    assert D(ls[f"Advik {t} (Philips)"]["closing_balance"]) == D("2800.00")
    assert D(j["tally_closing_balance"]) == D("8800.00")
    assert D(j["total_outstanding"]) == sum(D(x["outstanding"]) for x in j["ledgers"])
    brands = {x["brand"] for x in j["brand_summary"]}
    assert {"Oppo", "Philips"} <= brands
    assert D(j["tally_difference"]) == sum(D(x["tally_difference"]) for x in j["ledgers"])

    h = await env["c"].get(f"/api/v1/customers/{a.customer_id}/history", headers=env["admin_h"])
    assert h.status_code == 200, h.text
    items = h.json()["items"]
    assert h.json()["total"] == 3 and {i["ledger_name"] for i in items} == set(ls)
    assert all(i["kind"] == "INVOICE" for i in items)

    # Customers API: one outlet per shop; found by the secondary ledger name; merged hidden; merged detail redirects
    r = await env["c"].get("/api/v1/customers", params={"search": f"Advik {t} (Philips)"}, headers=env["admin_h"])
    assert [i["id"] for i in r.json()] == [str(a.customer_id)]
    item = r.json()[0]
    assert item["ledger_count"] == 2 and {"Oppo", "Philips"} <= set(item["brands"])
    for key in ("id", "name", "outlet_code", "brands", "location_status", "assigned_fos_names", "created_at"):
        assert key in item  # pre-2.1.0 fields kept
    r = await env["c"].get("/api/v1/customers", params={"search": t, "include_merged": "true"}, headers=env["admin_h"])
    assert str(b.customer_id) in [i["id"] for i in r.json()]
    d = await env["c"].get(f"/api/v1/customers/{b.customer_id}", headers=env["admin_h"])
    assert d.status_code == 200 and d.json()["merged_into_customer_id"] == str(a.customer_id)
    d = await env["c"].get(f"/api/v1/customers/{a.customer_id}", headers=env["admin_h"])
    assert len(d.json()["ledgers"]) == 2 and d.json()["ledgers"][0]["is_primary"] is True

    # Reconciliation stays per ledger (both reconcile) with an outlet roll-up
    rec = await env["c"].get("/api/v1/integrations/tally/reconciliation", params={"limit": 5000}, headers=env["admin_h"])
    assert rec.status_code == 200, rec.text
    assert "outlets" in rec.json()
    shop_rows = [d for d in rec.json()["differences"]
                 if d["customer_id"] in (str(a.customer_id), str(b.customer_id))]
    # The merged customer must never re-appear as a phantom "legacy" debtor (its money moved to the
    # outlet; its stale balance fields are history), and the shop's own ledgers carry no difference
    # beyond the deliberate test voucher above.
    assert not [d for d in shop_rows if d["customer_id"] == str(b.customer_id)], shop_rows
    assert not [d for d in shop_rows if d.get("ledger_id") is None], shop_rows


# ---------------------------------------------------------------------------
# M6: new ledger review; REVIEW decision
# ---------------------------------------------------------------------------

@requires_db
@pytest.mark.asyncio
async def test_new_ledger_waits_for_review_and_keep_separate(env):
    t = env["tag"]
    await _snapshot(env, [{"guid": f"N-{t}", "name": f"Brand New {t}", "is_debtor": True, "parent": "Sundry Debtors"}])
    n = await _ledger(f"N-{t}")
    assert n.mapping_status == "NEW_UNREVIEWED" and n.is_primary
    q = await env["c"].get("/api/v1/outlet-mapping/queues", headers=env["admin_h"])
    assert str(n.id) in [x["id"] for x in q.json()["new_unreviewed"]]
    r = await env["c"].post("/api/v1/outlet-mapping/review", json={"ledger_id": str(n.id), "decision": "KEEP_SEPARATE"},
                            headers=env["admin_h"])
    assert r.status_code == 200 and r.json()["action"] == "REVIEW", r.text
    assert (await _ledger(f"N-{t}")).mapping_status == "CONFIRMED"
    q = await env["c"].get("/api/v1/outlet-mapping/queues", headers=env["admin_h"])
    assert str(n.id) not in [x["id"] for x in q.json()["new_unreviewed"]]
    r = await env["c"].post("/api/v1/outlet-mapping/review", json={"ledger_id": str(n.id), "decision": "KEEP_SEPARATE"},
                            headers=env["admin_h"])
    assert r.status_code == 409


# ---------------------------------------------------------------------------
# M8: operational rows and unique clashes on merge; UNLINK restores them
# ---------------------------------------------------------------------------

@requires_db
@pytest.mark.asyncio
async def test_link_moves_operational_rows_supersedes_clashes_and_unlink_restores(env):
    t = env["tag"]
    await _snapshot(env, _two(env))
    a, b = await _ledger(f"A-{t}"), await _ledger(f"B-{t}")
    async with AsyncSessionLocal() as s:
        uid = (await s.execute(select(User.id).where(User.email == f"admin_v2_{t}@fieldtrack.test"))).scalar_one()
        emps = []
        for i in range(2):
            u = User(email=f"emp_v21_{t}_{i}@fieldtrack.test", password_hash=hash_password("x"), role=Role.EMPLOYEE,
                     is_active=True)
            s.add(u)
            await s.flush()
            e = Employee(user_id=u.id, full_name=f"Emp {t} {i}")
            s.add(e)
            await s.flush()
            emps.append(e)
        s.add_all([
            EmployeeCustomerAssignment(employee_id=emps[0].id, customer_id=a.customer_id, created_by=uid),
            EmployeeCustomerAssignment(employee_id=emps[0].id, customer_id=b.customer_id, created_by=uid),  # clash
            EmployeeCustomerAssignment(employee_id=emps[1].id, customer_id=b.customer_id, created_by=uid),  # moves
            CustomerBrand(customer_id=b.customer_id, brand="Oppo", is_active=True),  # clash (A has Oppo)
        ])
        b_cust = await s.get(Customer, b.customer_id)
        b_cust.outlet_code = f"UPDDB{t}"
        await s.commit()
    r = await env["c"].post("/api/v1/outlet-mapping/link", json={"ledger_id": str(b.id),
                            "target_customer_id": str(a.customer_id)}, headers=env["admin_h"])
    assert r.status_code == 200, r.text
    async with AsyncSessionLocal() as s:
        rows = (await s.execute(select(EmployeeCustomerAssignment).where(
            EmployeeCustomerAssignment.employee_id.in_([e.id for e in emps])))).scalars().all()
        on = {(x.employee_id, x.customer_id) for x in rows}
        assert (emps[1].id, a.customer_id) in on, "non-clashing assignment moved to the outlet"
        assert (emps[0].id, b.customer_id) in on, "clashing assignment kept on the merged customer"
        brands = (await s.execute(select(CustomerBrand.customer_id, CustomerBrand.brand).where(
            CustomerBrand.customer_id.in_([a.customer_id, b.customer_id])))).all()
        assert (a.customer_id, "Philips") in brands and (b.customer_id, "Oppo") in brands
        outlet = await s.get(Customer, a.customer_id)
        assert outlet.outlet_code == f"UPDDB{t}", "code copied because the outlet had none"
    r = await env["c"].post("/api/v1/outlet-mapping/unlink", json={"ledger_id": str(b.id)}, headers=env["admin_h"])
    assert r.status_code == 200, r.text
    async with AsyncSessionLocal() as s:
        rows = (await s.execute(select(EmployeeCustomerAssignment).where(
            EmployeeCustomerAssignment.employee_id == emps[1].id))).scalars().all()
        assert [x.customer_id for x in rows] == [b.customer_id]
        restored = await s.get(Customer, b.customer_id)
        assert restored.merged_into_customer_id is None and restored.outlet_code == f"UPDDB{t}"
        assert (await s.get(Customer, a.customer_id)).outlet_code is None
    b3 = await _ledger(f"B-{t}")
    assert b3.customer_id == b.customer_id and b3.is_primary
    # roles: an employee cannot link
    from tests.conftest import employee_headers
    r = await env["c"].post("/api/v1/outlet-mapping/link", json={"ledger_id": str(b.id),
                            "target_customer_id": str(a.customer_id)}, headers=employee_headers())
    assert r.status_code in (401, 403)


# ---------------------------------------------------------------------------
# M2, M7, M9: client workbook preview / apply / revert
# ---------------------------------------------------------------------------

HEADERS = ["Outlet ID", "Status", "Suggested shop", "Check together with", "Why", "Tally ledger name", "Brand",
           "Outlet code", "GST number", "Mobile", "Pincode", "Address", "Tally group",
           "Same GST/mobile used by (other names)", "Balance Rs (receivable)", "Same shop? (Y/N)",
           "Belongs to Outlet ID (if different)", "Brand (if blank)", "Outlet / DMS code (if known)", "Notes",
           "Tally ID (do not change)", "Status code"]


def _wb(rows):
    wb = Workbook()
    ws = wb.active
    ws.title = "Ledgers"
    ws.append(HEADERS)
    for r in rows:
        line = [None] * len(HEADERS)
        for k, v in r.items():
            line[HEADERS.index(k)] = v
        ws.append(line)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


@requires_db
@pytest.mark.asyncio
async def test_workbook_preview_apply_only_y_rows_and_revert(env):
    t = env["tag"]
    leds = _two(env) + [
        {"guid": f"C-{t}", "name": f"Advik {t} (USHA)", "is_debtor": True, "parent": "Sundry Debtors",
         "opening_balance": "0", "closing_balance": "-100.00"},
        {"guid": f"R-{t}", "name": f"Advik {t}", "is_debtor": True, "parent": "Sundry Debtors",
         "opening_balance": "0", "closing_balance": "-50.00"},
    ]
    await _snapshot(env, leds)
    await _post(env, "bills", {"snapshot_id": f"B-{uuid.uuid4().hex}", "as_of_date": AS_OF,
                               "is_final_chunk": True, "bills": []})
    a, b, c, rv = [await _ledger(f"{x}-{t}") for x in "ABCR"]
    data = _wb([
        {"Outlet ID": "P0001", "Tally ledger name": leds[0]["name"], "Same shop? (Y/N)": "Y",
         "Tally ID (do not change)": a.tally_guid, "Status code": "PROPOSED_STRONG"},
        {"Outlet ID": "P0001", "Tally ledger name": leds[1]["name"], "Same shop? (Y/N)": "Y",
         "Brand (if blank)": "Philips", "Tally ID (do not change)": b.tally_guid, "Status code": "PROPOSED_STRONG"},
        {"Outlet ID": "P0001", "Tally ledger name": leds[2]["name"],  # no answer: never applied
         "Tally ID (do not change)": c.tally_guid, "Status code": "PROPOSED_STRONG"},
        {"Outlet ID": "O0001", "Tally ledger name": leds[3]["name"], "Suggested shop": "P0001",
         "Same shop? (Y/N)": "N", "Brand (if blank)": "USHA",
         "Tally ID (do not change)": rv.tally_guid, "Status code": "REVIEW_NAME_ONLY"},
    ])
    files = {"file": ("m.xlsx", data, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    r = await env["c"].post("/api/v1/outlet-mapping/import/preview", files=files, headers=env["admin_h"])
    assert r.status_code == 200, r.text
    p = r.json()
    assert p["errors"] == [] and p["confirmed_rows"] == 2 and p["ignored_rows"] == 2
    assert [l["ledger_id"] for l in p["links"]] == [str(b.id)]
    assert p["links"][0]["to_customer_id"] == str(a.customer_id)
    assert len(p["brand_updates"]) == 2 and p["invariants_ok"] is True
    assert p["outlets_after"] == p["outlets_before"] - 1
    assert D(str(p["totals_before"]["outstanding"])) == D(str(p["totals_after"]["outstanding"]))

    r = await env["c"].post("/api/v1/outlet-mapping/import/apply", json={"preview_id": p["preview_id"]},
                            headers=env["admin_h"])
    assert r.status_code == 403, "bulk apply is Super Admin only"
    super_id, sh = await _super_headers(t)
    try:
        await _apply_and_revert(env, t, p, sh, a, b, c, rv)
    finally:
        await _deactivate(super_id)


async def _apply_and_revert(env, t, p, sh, a, b, c, rv):
    r = await env["c"].post("/api/v1/outlet-mapping/import/apply", json={"preview_id": p["preview_id"]}, headers=sh)
    assert r.status_code == 200, r.text
    batch = r.json()["batch_id"]
    assert r.json()["applied"] == 1
    assert (await _ledger(f"B-{t}")).customer_id == a.customer_id
    assert (await _ledger(f"C-{t}")).customer_id == c.customer_id, "unanswered row never linked"
    assert (await _ledger(f"R-{t}")).customer_id == rv.customer_id, "N row never linked"
    assert (await _ledger(f"R-{t}")).brand_override == "USHA"
    ev = await env["c"].get("/api/v1/outlet-mapping/events", params={"batch_id": batch}, headers=env["admin_h"])
    assert {e["action"] for e in ev.json()} >= {"LINK", "BRAND_OVERRIDE", "BULK_APPLY"}

    r = await env["c"].post("/api/v1/outlet-mapping/import/revert", json={"batch_id": batch}, headers=sh)
    assert r.status_code == 200, r.text
    assert (await _ledger(f"B-{t}")).customer_id == b.customer_id
    assert (await _ledger(f"R-{t}")).brand_override is None
    async with AsyncSessionLocal() as s:
        assert (await s.get(Customer, b.customer_id)).merged_into_customer_id is None
    r = await env["c"].post("/api/v1/outlet-mapping/import/revert", json={"batch_id": batch}, headers=sh)
    assert r.status_code == 409

    bad = _wb([{"Outlet ID": "P0009", "Tally ledger name": "x", "Same shop? (Y/N)": "Y",
                "Tally ID (do not change)": f"unknown-{t}", "Status code": "PROPOSED_STRONG"}])
    r = await env["c"].post("/api/v1/outlet-mapping/import/preview",
                            files={"file": ("b.xlsx", bad, "application/octet-stream")}, headers=env["admin_h"])
    assert r.status_code == 200 and r.json()["errors"] and r.json()["invariants_ok"] is False
    r = await env["c"].post("/api/v1/outlet-mapping/import/apply", json={"preview_id": r.json()["preview_id"]},
                            headers=sh)
    assert r.status_code == 409


# ---------------------------------------------------------------------------
# C2 / C3: heartbeat health and sync_state
# ---------------------------------------------------------------------------

def _health(**kw):
    h = {"instance": "default", "agent_version": "2.1.0", "phase": "IDLE",
         "last_cycle_completed_at": datetime.now(timezone.utc).isoformat(), "last_cycle_status": "COMPLETED",
         "retry_queue": {"pending": 0, "oldest_age_seconds": None, "rejected_4xx": 0},
         "quarantine": {"unresolved": 0}, "interval_seconds": 300}
    h.update(kw)
    return h


@requires_db
@pytest.mark.asyncio
async def test_heartbeat_health_storage_size_cap_and_legacy(env):
    c, ah = env["c"], env["agent_h"]
    r = await c.post("/api/v1/integrations/tally/heartbeat", headers=ah, json={
        "agent_version": "2.1.0", "tally_status": "ONLINE", "checkpoints": {"vouchers_v2": {"last_alter_id": 9},
                                                                            "_health": _health()}})
    assert r.status_code == 200, r.text
    st = (await c.get("/api/v1/integrations/tally/status", headers=env["admin_h"])).json()
    assert st["sync_state"] == "OK" and st["health"]["agent_version"] == "2.1.0" and st["health_reported_at"]
    async with AsyncSessionLocal() as s:
        ag = await s.get(SyncAgent, uuid.UUID(ah["X-Agent-Id"]))
        assert ag.last_checkpoints == {"vouchers_v2": {"last_alter_id": 9}}
    # 1.2.1-style heartbeat (no _health): stored health unchanged
    await c.post("/api/v1/integrations/tally/heartbeat", headers=ah,
                 json={"agent_version": "1.2.1", "tally_status": "ONLINE", "checkpoints": {}})
    async with AsyncSessionLocal() as s:
        assert (await s.get(SyncAgent, uuid.UUID(ah["X-Agent-Id"]))).health["agent_version"] == "2.1.0"
    # over 32 KB
    await c.post("/api/v1/integrations/tally/heartbeat", headers=ah, json={
        "agent_version": "2.1.0", "tally_status": "ONLINE",
        "checkpoints": {"_health": _health(phase_detail="x" * 40000)}})
    async with AsyncSessionLocal() as s:
        assert (await s.get(SyncAgent, uuid.UUID(ah["X-Agent-Id"]))).health == {"error": "health too large"}


def test_sync_state_rules():
    now = datetime.now(timezone.utc)
    ok = SimpleNamespace(last_heartbeat_at=now, tally_status="ONLINE", health=_health())

    def ag(**kw):
        return SimpleNamespace(**{**vars(ok), **kw})
    old = (now - timedelta(hours=1)).isoformat()
    assert compute_sync_state(None, now) == "NOT_CONFIGURED"
    assert compute_sync_state(ag(last_heartbeat_at=now - timedelta(seconds=181)), now) == "OFFLINE"
    assert compute_sync_state(ag(health=_health(last_cycle_status="TALLY_UNAVAILABLE")), now) == "TALLY_UNAVAILABLE"
    assert compute_sync_state(ag(health=_health(phase="INITIAL_LOAD", last_cycle_completed_at=None)), now) == "SYNCING"
    assert compute_sync_state(ag(health=_health(last_cycle_completed_at=old)), now) == "STALLED"
    assert compute_sync_state(ag(health=_health(retry_queue={"rejected_4xx": 1})), now) == "DEGRADED"
    assert compute_sync_state(ag(health=_health(retry_queue={"oldest_age_seconds": 3601})), now) == "DEGRADED"
    assert compute_sync_state(ag(health=_health(quarantine={"unresolved": 2})), now) == "DEGRADED"
    assert compute_sync_state(ag(health=_health(last_cycle_status="BACKEND_ERROR")), now) == "DEGRADED"
    assert compute_sync_state(ok, now) == "OK"
    assert compute_sync_state(ag(health=None), now) == "OK"
    assert compute_sync_state(ag(health=None, tally_status="OFFLINE"), now) == "TALLY_UNAVAILABLE"


# ---------------------------------------------------------------------------
# Replay idempotency (T9)
# ---------------------------------------------------------------------------

@requires_db
@pytest.mark.asyncio
async def test_same_voucher_batch_twice_changes_nothing(env):
    t = env["tag"]
    led = _two(env)
    await _snapshot(env, led)
    batch = {"vouchers": [
        _vch(env, "RP1", "Oppo", "Sales", [{"ledger_name": led[0]["name"], "ledger_guid": led[0]["guid"],
              "amount": "-700", "brand": "Oppo"}], number=f"RP1-{t}"),
        _vch(env, "RP2", "BANK RECEIPT", "Receipt", [{"ledger_name": led[0]["name"], "ledger_guid": led[0]["guid"],
              "amount": "300"}], counter=[{"ledger_name": "HDFC", "ledger_class": "BANK", "amount": "-300"}]),
        _vch(env, "RP3", "Credit Note", "Credit Note", [{"ledger_name": led[1]["name"], "amount": "50"}]),
    ]}

    async def state():
        async with AsyncSessionLocal() as s:
            return (await s.execute(text(
                "SELECT 'i', source_reference, amount::text, customer_id::text, tally_debtor_ledger_id::text, source::text "
                "FROM invoices WHERE source_reference LIKE :p UNION ALL "
                "SELECT 'p', source_reference, amount::text, customer_id::text, tally_debtor_ledger_id::text, source::text "
                "FROM payments WHERE source_reference LIKE :p UNION ALL "
                "SELECT 'a', source_reference, amount::text, customer_id::text, tally_debtor_ledger_id::text, state "
                "FROM tally_ledger_adjustments WHERE source_reference LIKE :p ORDER BY 1, 2"), {"p": f"RP%-{t}%"})).all()
    first = await _post(env, "vouchers", batch)
    s1 = await state()
    second = await _post(env, "vouchers", batch)
    s2 = await state()
    assert first["created_count"] == 3 and second["created_count"] == 0 and second["failed_count"] == 0
    assert s1 == s2 and len(s1) == 3
