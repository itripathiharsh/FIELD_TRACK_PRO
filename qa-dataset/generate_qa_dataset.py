"""
FieldTrack Pro LOCAL QA dataset generator (fictional data, fieldtrackpro_dev only).

Run from the backend directory so the app settings load the local .env:
    cd "F:\\Field track pro v2 for test\\field track pro\\fieldtrackpro-backend"
    python -I "F:\\Field track pro v2 for test\\qa-dataset\\generate_qa_dataset.py"

Pathways (all existing application logic):
  areas            -> app.services.area_service.create_area
  outlets          -> Customer rows + EmployeeCustomerAssignment (same as the admin assignment model)
  Tally-style data -> a dedicated LOCAL test sync agent (tally_sync_service.register_agent) posting to the LOCAL
                      backend's agent API: /sync/ledgers (non-final snapshot chunk: can never retire other ledgers),
                      /sync/vouchers (sales + receipts), /sync/bills (Bills Receivable snapshot -> due dates)
  field collections-> employee API: POST /visits/ad-hoc, POST /payments; admin verify/reject via payment_service
  monthly plan     -> employee API (today/future) + admin visit_planning_service for past dates (=> missed)
Writes the created identifiers to qa_manifest.json for the cleanup script.
"""
import asyncio
import json
import os
import random
import sys
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import qa_common as qc  # noqa: E402

if os.path.abspath(os.getcwd()).lower() != qc.BACKEND_DIR.lower():
    qc.abort("run this from the backend directory (so the local .env is used)")
sys.path.insert(0, os.getcwd())

import asyncpg  # noqa: E402
from sqlalchemy import select  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402

from app.config import settings  # noqa: E402

_u = make_url(str(settings.database_url))
qc.check_url(qc.db_url())
if _u.host not in qc.EXPECTED_HOSTS or _u.port != qc.EXPECTED_PORT or _u.database != qc.EXPECTED_DB:
    qc.abort("backend settings do not point at the local dev database")
if str(getattr(settings, "environment", "")).lower() != "dev":
    qc.abort("ENVIRONMENT is not dev")
if getattr(settings, "tally_writeback_enabled", False):
    qc.abort("Tally writeback is enabled")

from app.database import AsyncSessionLocal  # noqa: E402
from app.models.area import Area  # noqa: E402
from app.models.customer import Customer  # noqa: E402
from app.models.employee_customer_assignment import EmployeeCustomerAssignment  # noqa: E402
from app.models.territory import Territory  # noqa: E402
from app.models.user import Role, User  # noqa: E402
from app.schemas.area import AreaCreate  # noqa: E402
from app.schemas.tally_sync import SyncAgentCreate  # noqa: E402
from app.schemas.visit_planning import PlannedVisitCreate  # noqa: E402
from app.services import area_service, payment_service, tally_sync_service, visit_planning_service  # noqa: E402

CENT = Decimal("0.01")
TODAY = date.today()
RNG = random.Random(20261123)
TERRITORY = "TEST - Local QA"
AREAS = ["TEST QA Lakeview", "TEST QA Hillside", "TEST QA Riverside", "TEST QA Market Yard"]
BRANDS = ["TEST-QA Mobiles", "TEST-QA Accessories"]
OUTLETS = [  # (name, area index) - fictional
    ("Alpha Electronics", 0), ("Bright Mobile Hub", 0), ("City Telecom", 0), ("Digital World", 0), ("Galaxy Distributors", 0),
    ("Metro Communications", 1), ("Nova Electronics", 1), ("Prime Mobile Store", 1), ("Orbit Gadgets", 1), ("Pixel Point", 1),
    ("Quantum Mobiles", 2), ("Signal Plus", 2), ("Smart Connect", 2), ("Tech Avenue", 2), ("Urban Phones", 2),
    ("Vertex Telecom", 3), ("Wave Electronics", 3), ("Zenith Mobile Care", 3), ("Bluebird Communications", 3),
    ("Crest Digital", 3), ("Harbor Electronics", 0), ("Lumen Mobile World", 2),
]
WITH_TALLY = 16          # first 16 outlets get ledgers / bills; the rest test empty states
DAYS_AGO = [5, 15, 25, 40, 50, 70, 85, 100, 130, 150]   # with 30-day credit -> not due ... >90 days past due
CREDIT_DAYS = 30
SNAP = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")


def q(v) -> Decimal:
    return Decimal(v).quantize(CENT, rounding=ROUND_HALF_UP)


def build_billing(outlet_codes):
    """Deterministic fictional invoices and Tally receipts per outlet."""
    invoices, receipts = [], []
    n_inv = 0
    n_rct = 0
    for i, code in enumerate(outlet_codes):
        k = 2 + (i % 3)  # 2-4 bills
        picks = sorted(RNG.sample(DAYS_AGO, k), reverse=True)
        for d in picks:
            n_inv += 1
            inv_no = f"TEST-QA-INV-{n_inv:04d}"
            inv_date = TODAY - timedelta(days=d)
            amount = q(RNG.choice([1850, 3200, 4750.5, 6400, 8925.75, 12500, 15300, 21875.25, 9800, 27450]))
            # payment pattern: 0 unpaid, 1 partial, 2 full
            pattern = 2 if i == 5 else (n_inv % 3 if d > 10 else 0)
            invoices.append(dict(no=inv_no, code=code, date=inv_date, due=inv_date + timedelta(days=CREDIT_DAYS),
                                 amount=amount, brand=BRANDS[n_inv % 2], pattern=pattern))
            if pattern:
                paid = amount if pattern == 2 else q(amount * Decimal(RNG.choice(["0.4", "0.5", "0.65"])))
                n_rct += 1
                rdate = min(inv_date + timedelta(days=RNG.randint(3, max(4, d - 2))), TODAY - timedelta(days=1))
                receipts.append(dict(no=f"TEST-QA-RCT-{n_rct:04d}", code=code, date=rdate, amount=paid, bill=inv_no,
                                     mode=RNG.choice(["CASH", "NEFT", "CHEQUE"])))
    return invoices, receipts


async def main():
    manifest = {"created_at": datetime.now(timezone.utc).isoformat(), "database": qc.EXPECTED_DB, "marker": "TEST-QA-"}
    qc.backend_is_local_and_up()
    con = await asyncpg.connect(qc.db_url())
    await qc.assert_local(con)
    emp = await con.fetchrow("select e.id, e.user_id, u.role from employees e join users u on u.id=e.user_id where e.id=$1", uuid.UUID(qc.TEST_EMPLOYEE_ID))
    if emp is None or emp["role"] != "EMPLOYEE":
        qc.abort("test employee not found or not EMPLOYEE")
    if await con.fetchval("select count(*) from customers where outlet_code like 'TEST-QA-OUT-0%' and outlet_code > 'TEST-QA-OUT-003'"):
        qc.abort("QA outlets already exist - run the cleanup script first")

    # ---------------------------------------------------------------- 1. areas + outlets
    async with AsyncSessionLocal() as s:
        terr = (await s.execute(select(Territory).where(Territory.name == TERRITORY))).scalar_one()
        actor = (await s.execute(select(User).where(User.role.in_([Role.SUPER_ADMIN, Role.ADMIN]), User.is_active.is_(True))
                                 .order_by(User.role.desc(), User.created_at))).scalars().first()
        if actor is None:
            qc.abort("no active admin to act as creator")
        areas = []
        for name in AREAS:
            await qc.assert_local(con)
            a = (await s.execute(select(Area).where(Area.name == name, Area.territory_id == terr.id))).scalar_one_or_none()
            if a is None:
                a = await area_service.create_area(AreaCreate(name=name, territory_id=terr.id), s)
            areas.append(a)
        manifest["area_ids"] = [str(a.id) for a in areas]
        outlets = []
        for i, (name, ai) in enumerate(OUTLETS, start=4):
            c = Customer(name=name, contact_number=f"0000000{i:03d}", contact_person=f"QA Contact {i}",
                         address=f"Shop {i}, TEST QA Plaza, {AREAS[ai].replace('TEST QA ', '')} (fictional)",
                         outlet_code=f"TEST-QA-OUT-{i:03d}", territory_id=terr.id, area_id=areas[ai].id,
                         created_by=emp["user_id"])
            s.add(c)
            outlets.append(c)
        await s.flush()
        for c in outlets:
            s.add(EmployeeCustomerAssignment(employee_id=uuid.UUID(qc.TEST_EMPLOYEE_ID), customer_id=c.id, created_by=actor.id))
        await qc.assert_local(con)
        await s.commit()
        out = [(c.id, c.name, c.outlet_code, AREAS[OUTLETS[i][1]]) for i, c in enumerate(outlets)]
        manifest["outlet_ids"] = [str(o[0]) for o in out]
        actor_id = actor.id

        # ------------------------------------------------------------ 2. local synthetic Tally agent
        await qc.assert_local(con)
        agent, raw_key = await tally_sync_service.register_agent(
            SyncAgentCreate(name="TEST-QA Local Synthetic Agent", tally_company_guid="TEST-QA-COMPANY",
                            tally_company_name="TEST-QA Fictional Distributors (local QA only)"), s)
        manifest["agent_id"] = str(agent.id)
        with open(os.path.join(qc.SECRETS_DIR, "qa-local-agent.txt"), "w", encoding="utf-8") as f:
            f.write(f"LOCAL QA synthetic Tally agent (fieldtrackpro_dev only)\nAgent: {agent.id}\nKey: {raw_key}\n")
    agent_headers = {"X-Agent-Id": manifest["agent_id"], "X-Agent-Key": raw_key}

    # ---------------------------------------------------------------- 3. billing plan
    tally_outlets = out[:WITH_TALLY]
    invoices, receipts = build_billing([o[2] for o in tally_outlets])
    paid_by_bill = {}
    for r in receipts:
        paid_by_bill[r["bill"]] = paid_by_bill.get(r["bill"], Decimal("0")) + r["amount"]
    for inv in invoices:
        inv["pending"] = inv["amount"] - paid_by_bill.get(inv["no"], Decimal("0"))
    by_code = {o[2]: o for o in tally_outlets}
    ledger_guid = {o[2]: f"TEST-QA-LEDGER-{o[2][-3:]}" for o in tally_outlets}

    # ---------------------------------------------------------------- 4. ledgers (non-final snapshot chunk)
    ledgers = []
    for code, o in by_code.items():
        pending = sum((i["pending"] for i in invoices if i["code"] == code), Decimal("0"))
        ledgers.append(dict(guid=ledger_guid[code], name=o[1], parent="Sundry Debtors", is_debtor=True, outlet_code=code,
                            brand=BRANDS[0], address=f"TEST QA Plaza, {o[3]} (fictional)", zone=TERRITORY, area=o[3],
                            is_bill_wise=True, credit_period=f"{CREDIT_DAYS} Days",
                            opening_balance="0.00", closing_balance=str(-pending), alter_id=1))
    await qc.assert_local(con)
    st, res, _ = qc.http("POST", "/integrations/tally/sync/ledgers", dict(
        batch_id=f"TEST-QA-LEDGERS-{SNAP}", company_guid="TEST-QA-COMPANY", snapshot_id=f"TEST-QA-LEDGERS-{SNAP}",
        is_final_chunk=False, as_of=datetime.now(timezone.utc).isoformat(), period_start="2026-04-01", ledgers=ledgers), agent_headers)
    print("ledgers:", st, res if st != 200 else {k: res[k] for k in ("created_count", "updated_count", "failed_count")})
    if st != 200 or res["failed_count"]:
        qc.abort(f"ledger sync failed: {res}")
    manifest["ledger_guids"] = list(ledger_guid.values())
    manifest["snapshot_ids"] = [f"TEST-QA-LEDGERS-{SNAP}"]

    # ---------------------------------------------------------------- 5. vouchers (sales + receipts)
    vouchers = []
    alter = 1000
    for inv in invoices:
        alter += 1
        name = by_code[inv["code"]][1]
        vouchers.append(dict(guid=f"TEST-QA-VCH-{inv['no']}", alter_id=alter, date=inv["date"].isoformat(), voucher_type="Sales",
                             voucher_parent="Sales", voucher_number=inv["no"], party_ledger=name, narration="TEST-QA fictional sales bill",
                             debtor_lines=[dict(ledger_name=name, ledger_guid=ledger_guid[inv["code"]], amount=str(-inv["amount"]), brand=inv["brand"],
                                                bill_allocations=[dict(name=inv["no"], bill_type="New Ref", amount=str(-inv["amount"]), credit_period=f"{CREDIT_DAYS} Days")])],
                             counter_lines=[dict(ledger_name="TEST-QA Sales", ledger_class="OTHER", amount=str(inv["amount"]))]))
    for r in receipts:
        alter += 1
        name = by_code[r["code"]][1]
        if r["mode"] == "CASH":
            counter = dict(ledger_name="TEST-QA Cash", ledger_class="CASH", amount=str(-r["amount"]),
                           bank_allocations=[dict(transaction_type="Cash", amount=str(-r["amount"]))])
        elif r["mode"] == "NEFT":
            counter = dict(ledger_name="TEST-QA Bank", ledger_class="BANK", amount=str(-r["amount"]),
                           bank_allocations=[dict(transaction_type="NEFT", instrument_number=f"TESTQAUTR{alter}", bank_name="TEST-QA Bank", amount=str(-r["amount"]))])
        else:
            counter = dict(ledger_name="TEST-QA Bank", ledger_class="BANK", amount=str(-r["amount"]),
                           bank_allocations=[dict(transaction_type="Cheque", instrument_number=f"{alter:06d}", bank_name="TEST-QA Bank", amount=str(-r["amount"]))])
        vouchers.append(dict(guid=f"TEST-QA-VCH-{r['no']}", alter_id=alter, date=r["date"].isoformat(), voucher_type="Receipt",
                             voucher_parent="Receipt", voucher_number=r["no"], party_ledger=name, narration="TEST-QA fictional receipt",
                             debtor_lines=[dict(ledger_name=name, ledger_guid=ledger_guid[r["code"]], amount=str(r["amount"]),
                                                bill_allocations=[dict(name=r["bill"], bill_type="Agst Ref", amount=str(r["amount"]))])],
                             counter_lines=[counter]))
    await qc.assert_local(con)
    st, res, _ = qc.http("POST", "/integrations/tally/sync/vouchers", dict(batch_id=f"TEST-QA-VOUCHERS-{SNAP}", company_guid="TEST-QA-COMPANY", vouchers=vouchers), agent_headers)
    print("vouchers:", st, res if st != 200 else {k: res[k] for k in ("created_count", "updated_count", "failed_count")}, (res or {}).get("errors", [])[:3] if st == 200 else "")
    if st != 200 or res["failed_count"]:
        qc.abort(f"voucher sync failed: {res}")
    manifest["voucher_guids"] = [v["guid"] for v in vouchers]

    # ---------------------------------------------------------------- 6. Bills Receivable snapshot (due dates)
    bills = [dict(ledger_name=by_code[i["code"]][1], ledger_guid=ledger_guid[i["code"]], bill_name=i["no"], bill_date=i["date"].isoformat(),
                  due_date=i["due"].isoformat(), pending_amount=str(-i["pending"]), overdue_days=max(0, (TODAY - i["due"]).days))
             for i in invoices if i["pending"] > 0]
    await qc.assert_local(con)
    st, res, _ = qc.http("POST", "/integrations/tally/sync/bills", dict(batch_id=f"TEST-QA-BILLS-{SNAP}", company_guid="TEST-QA-COMPANY",
                         snapshot_id=f"TEST-QA-BILLS-{SNAP}", as_of_date=TODAY.isoformat(), is_final_chunk=True, bills=bills), agent_headers)
    print("bills:", st, res if st != 200 else res.get("details"))
    if st != 200 or res["failed_count"]:
        qc.abort(f"bills sync failed: {res}")
    manifest["snapshot_ids"].append(f"TEST-QA-BILLS-{SNAP}")

    # ---------------------------------------------------------------- 7. employee session
    st, tok, _ = qc.http("POST", "/auth/login", dict(mobile_number=qc.TEST_MOBILE, password=qc.secret("local-test-employee.txt", "Password")))
    if st != 200:
        qc.abort(f"test employee login failed ({st})")
    auth = {"Authorization": "Bearer " + tok["access_token"]}

    # ---------------------------------------------------------------- 8. monthly plan
    planned_ids, cancelled_ids = [], []
    month_end = (TODAY.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
    future_days = [TODAY + timedelta(days=d) for d in range(0, (month_end - TODAY).days + 1)]
    objectives = ["Payment follow-up", "New scheme briefing", "Stock check", "Collect pending cheque", "Order booking", "Display audit"]
    prios = ["HIGH", "MEDIUM", "LOW"]
    for n in range(10):
        o = out[(n * 3) % len(out)]
        d = future_days[n % len(future_days)]
        await qc.assert_local(con)
        st, pv, _ = qc.http("POST", "/visit-planning/visits", dict(customer_id=str(o[0]), planned_date=d.isoformat(), priority=prios[n % 3],
                            visit_type="PLANNED", notes=f"TEST-QA: {objectives[n % len(objectives)]}"), auth)
        if st not in (200, 201):
            qc.abort(f"plan create failed: {st} {pv}")
        planned_ids.append(pv["id"])
    for pid in planned_ids[-2:]:
        await qc.assert_local(con)
        st, _, _ = qc.http("DELETE", f"/visit-planning/visits/{pid}", None, auth)
        if st not in (200, 204):
            qc.abort(f"plan cancel failed: {st}")
        cancelled_ids.append(pid)
    past_ids = []
    async with AsyncSessionLocal() as s:
        actor = await s.get(User, actor_id)
        for n, day in enumerate([3, 6, 9, 12, 16, 19, 21]):
            pd = TODAY.replace(day=day)
            if pd >= TODAY:
                continue
            o = out[(n * 5 + 1) % len(out)]
            await qc.assert_local(con)
            pv = await visit_planning_service.create_planned_visit(
                PlannedVisitCreate(customer_id=o[0], planned_date=pd, priority=prios[n % 3], visit_type="PLANNED",
                                   notes=f"TEST-QA: {objectives[(n + 2) % len(objectives)]} (back-dated by admin)",
                                   employee_id=uuid.UUID(qc.TEST_EMPLOYEE_ID)), actor, s)
            past_ids.append(str(pv.id))
    manifest["planned_visit_ids"] = planned_ids + past_ids
    manifest["cancelled_planned_visit_ids"] = cancelled_ids

    # ---------------------------------------------------------------- 9. field collections (employee workflow)
    open_inv = {}
    for i in invoices:
        if i["pending"] > 0 and i["code"] not in open_inv:
            open_inv[i["code"]] = i
    inv_ids = {r["source_reference"]: r["id"] for r in await con.fetch(
        "select id, source_reference from invoices where source='TALLY' and source_reference like 'TEST-QA-VCH-%'")}
    codes = list(open_inv)
    plan = [  # (outlet code, invoice?, amount, method, days ago, final status)
        (codes[0], True, "5000.00", "CASH", 1, "VERIFIED"),
        (codes[1], True, "2500.50", "ONLINE", 3, "VERIFIED"),
        (codes[2], True, "8000.00", "CHEQUE", 6, "VERIFIED"),
        (codes[0], True, "1200.00", "CASH", 0, "PENDING"),
        (codes[3], True, "3000.00", "ONLINE", 2, "REJECTED"),
        (out[WITH_TALLY][2], False, "1500.00", "CASH", 0, "PENDING"),   # outlet without bills: advance
    ]
    code_to_id = {o[2]: str(o[0]) for o in out}
    visit_by_code, payment_ids, payment_plan = {}, [], []
    for code, with_inv, amount, method, ago, final in plan:
        if code not in visit_by_code:
            await qc.assert_local(con)
            st, v, _ = qc.http("POST", "/visits/ad-hoc", dict(customer_id=code_to_id[code], adhoc_reason="Payment Follow-up", adhoc_notes="TEST-QA collection"), auth)
            if st not in (200, 201):
                qc.abort(f"ad-hoc visit failed: {st} {v}")
            visit_by_code[code] = v["id"]
        body = dict(visit_id=visit_by_code[code], amount=amount, payment_method=method, payment_date=(TODAY - timedelta(days=ago)).isoformat(),
                    notes="TEST-QA field collection", idempotency_key=f"TEST-QA-{uuid.uuid4()}")
        if with_inv:
            body["invoice_id"] = str(inv_ids[f"TEST-QA-VCH-{open_inv[code]['no']}"])
            # The backend caps a collection at the bill's open balance; stay well inside it.
            body["amount"] = str(min(Decimal(amount), q(open_inv[code]["pending"] * Decimal("0.45"))))
        if method == "CHEQUE":
            body.update(cheque_number=f"{RNG.randint(100000, 999999)}", cheque_bank_name="TEST-QA Bank")
        if method == "ONLINE":
            body["utr_reference"] = f"TESTQAUTR{RNG.randint(10**8, 10**9)}"
        await qc.assert_local(con)
        st, p, _ = qc.http("POST", "/payments", body, auth)
        if st not in (200, 201):
            qc.abort(f"payment failed: {st} {p}")
        payment_ids.append(p["id"])
        payment_plan.append(dict(id=p["id"], code=code, amount=body["amount"], method=method, final=final))
    manifest["visit_ids"] = list(visit_by_code.values())
    manifest["payment_ids"] = payment_ids
    async with AsyncSessionLocal() as s:
        actor = await s.get(User, actor_id)
        for pp in payment_plan:
            await qc.assert_local(con)
            if pp["final"] == "VERIFIED":
                await payment_service.verify_payment(uuid.UUID(pp["id"]), actor, s)
            elif pp["final"] == "REJECTED":
                await payment_service.reject_payment(uuid.UUID(pp["id"]), "TEST-QA: amount does not match the bank statement", actor, s)

    manifest["brands"] = BRANDS
    manifest["billing_plan"] = [{k: str(v) for k, v in i.items()} for i in invoices]
    manifest["receipt_plan"] = [{k: str(v) for k, v in r.items()} for r in receipts]
    manifest["payment_plan"] = payment_plan
    with open(qc.MANIFEST, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    await con.close()
    print(f"outlets={len(out)} areas={len(AREAS)} invoices={len(invoices)} tally_receipts={len(receipts)} "
          f"field_payments={len(payment_ids)} planned={len(planned_ids) + len(past_ids)} cancelled={len(cancelled_ids)}")
    print("manifest:", qc.MANIFEST)


asyncio.run(main())
