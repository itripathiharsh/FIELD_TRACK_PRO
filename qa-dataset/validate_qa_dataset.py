"""Validate the LOCAL QA dataset through the LOCAL backend APIs and cross-check against fieldtrackpro_dev.
Run:  python -I validate_qa_dataset.py   (read-only; prints no secrets)"""
import asyncio
import json
import os
import sys
import uuid
from collections import defaultdict
from datetime import date
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import qa_common as qc  # noqa: E402
import asyncpg  # noqa: E402

D = Decimal
TODAY = date.today()


def bucket(due, today=TODAY):
    if due is None:
        return "No due date"
    d = (today - due).days
    return "Not yet due" if d <= 0 else "1-30" if d <= 30 else "31-60" if d <= 60 else "61-90" if d <= 90 else ">90"


async def main():
    qc.check_url(qc.db_url())
    m = json.load(open(qc.MANIFEST, encoding="utf-8"))
    con = await asyncpg.connect(qc.db_url())
    await qc.assert_local(con)
    ok = True

    def check(label, cond, detail=""):
        nonlocal ok
        ok &= bool(cond)
        print(("PASS " if cond else "FAIL ") + label + (f"  [{detail}]" if detail else ""))

    st, tok, _ = qc.http("POST", "/auth/login", dict(mobile_number=qc.TEST_MOBILE, password=qc.secret("local-test-employee.txt", "Password")))
    check("1 login", st == 200, st)
    H = {"Authorization": "Bearer " + tok["access_token"]}
    st, me, _ = qc.http("GET", "/auth/me", headers=H)
    check("1 profile is EMPLOYEE TEST-QA-01", st == 200 and me["role"] == "EMPLOYEE" and me["employee_code"] == "TEST-QA-01")

    st, outlets, h = qc.http("GET", "/customers?skip=0&limit=1000", headers=H)
    qa = [c for c in outlets if (c.get("outlet_code") or "").startswith("TEST-QA-OUT-")]
    check("2 outlet list = 25 TEST-QA outlets (3 setup + 22 dataset)", st == 200 and len(qa) == 25, f"{len(qa)} of {len(outlets)}")
    by_area = defaultdict(int)
    for c in qa:
        by_area[c.get("area_name")] += 1
    print("   area distribution:", dict(by_area))
    for qtext, expect in [("alpha", "Alpha Electronics"), ("TEST-QA-OUT-010", None), ("lakeview", None), ("zzz-none", None)]:
        st, res, hh = qc.http("GET", f"/customers?skip=0&limit=50&search={qtext}", headers=H)
        names = [r["name"] for r in res] if st == 200 else res
        print(f"   search '{qtext}': {st} -> {len(names) if st == 200 else names} result(s) {names[:4] if st == 200 else ''}")
        if expect:
            check(f"2 search '{qtext}' finds {expect}", st == 200 and expect in names)

    y, mo = TODAY.year, TODAY.month
    st, plan, _ = qc.http("GET", f"/visit-planning/my-plan?year={y}&month={mo}", headers=H)
    st2, an, _ = qc.http("GET", f"/visit-planning/analytics/my-month?year={y}&month={mo}", headers=H)
    pv = plan["planned_visits"]
    statuses = defaultdict(int)
    for v in pv:
        statuses[v["status"]] += 1
    db_pv = await con.fetch("select status, count(*) n from planned_visits where id = any($1::uuid[]) group by 1", [uuid.UUID(x) for x in m["planned_visit_ids"]])
    print("   planned visits (API):", dict(statuses), " DB:", {r["status"]: r["n"] for r in db_pv})
    print("   analytics:", {k: an[k] for k in ("total_planned", "completed", "missed", "cancelled", "completion_rate", "behind_schedule")})
    check("3 monthly plan totals reconcile (active = planned+completed+missed)", an["total_planned"] == len([v for v in pv if v["status"] != "CANCELLED"]))

    st, visits, _ = qc.http("GET", "/visits?skip=0&limit=100", headers=H)
    mine = [v for v in visits if v["id"] in m["visit_ids"]]
    check("4 visit history lists the QA ad-hoc visits", st == 200 and len(mine) == len(m["visit_ids"]), f"{len(mine)}/{len(m['visit_ids'])}")

    # 5-7: balances, remaining, ageing - API vs DB
    tally_codes = sorted({b["code"] for b in m["billing_plan"]})
    api_out_total, api_buckets, db_buckets = D("0"), defaultdict(D), defaultdict(D)
    samples = {}
    id_by_code = {c["outlet_code"]: c["id"] for c in qa}
    for code in tally_codes:
        cid = id_by_code[code]
        st, acc, _ = qc.http("GET", f"/customers/{cid}/account", headers=H)
        st2, invs, _ = qc.http("GET", f"/customers/{cid}/invoices", headers=H)
        api_out_total += D(acc["total_outstanding"])
        db_open = await con.fetchval("select coalesce(sum(pending_amount),0) from tally_open_bills where customer_id=$1 and snapshot_id like 'TEST-QA-BILLS-%'", uuid.UUID(cid))
        db_closing = await con.fetchval("select -closing_balance from tally_debtor_ledgers where customer_id=$1 and tally_guid like 'TEST-QA-%'", uuid.UUID(cid))
        if D(acc["total_outstanding"]) != D(db_open) or D(db_open) != D(db_closing):
            check(f"5 {code} outstanding = open bills = ledger closing", False, f"{acc['total_outstanding']} / {db_open} / {db_closing}")
        for inv in invs:
            rem = D(inv["remaining_amount"])
            db_inv = await con.fetchrow("select amount, due_date from invoices where id=$1", uuid.UUID(inv["id"]))
            alloc = await con.fetchval("select coalesce(sum(allocated_amount),0) from payment_invoice_allocations a join payments p on p.id=a.payment_id where a.invoice_id=$1 and p.source='TALLY'", uuid.UUID(inv["id"]))
            if rem != D(db_inv["amount"]) - D(alloc):
                check(f"6 {inv['invoice_number']} remaining = amount - Tally receipts", False, f"{rem} vs {db_inv['amount']}-{alloc}")
            if rem > 0:
                api_buckets[bucket(date.fromisoformat(inv["due_date"]) if inv["due_date"] else None)] += rem
                db_buckets[bucket(db_inv["due_date"])] += rem
            kind = "unpaid" if rem == D(inv["amount"]) else ("paid" if rem == 0 else "partial")
            samples.setdefault(kind, (inv["invoice_number"], code, inv["amount"], inv["remaining_amount"], inv["due_date"], D(inv["amount"]) - rem))
        if D(acc["overdue_amount"]) > 0:
            samples.setdefault("overdue_outlet", (code, acc["total_outstanding"], acc["overdue_amount"]))
    check("5 every Tally outlet: API outstanding = open bills = ledger closing", True)
    db_total = await con.fetchval("select coalesce(sum(pending_amount),0) from tally_open_bills where snapshot_id like 'TEST-QA-BILLS-%'")
    check("5 portfolio outstanding API = DB open bills", api_out_total == D(db_total), f"{api_out_total} vs {db_total}")
    check("7 due-date ageing API = DB", dict(api_buckets) == dict(db_buckets), dict(api_buckets))
    inv_tot = await con.fetchval("select sum(amount) from invoices where source='TALLY' and source_reference like 'TEST-QA-VCH-%'")
    rct_tot = await con.fetchval("select sum(amount) from payments where source='TALLY' and source_reference like 'TEST-QA-VCH-%'")
    check("6 invoiced - Tally receipts = outstanding", D(inv_tot) - D(rct_tot) == D(db_total), f"{inv_tot} - {rct_tot} = {db_total}")

    # 8: employee collections (workday summary) vs DB payments by employee_id
    # The backend's daily summary uses UTC day boundaries, so compare on the UTC date of the payments.
    utc_day = await con.fetchval("select (max(created_at) at time zone 'UTC')::date from payments where id = any($1::uuid[])", [uuid.UUID(x) for x in m["payment_ids"]])
    st, wd, _ = qc.http("GET", f"/workday/today?work_date={utc_day.isoformat()}", headers=H)
    s = wd["summary"]
    db = await con.fetchrow("""select coalesce(sum(amount),0) total, coalesce(sum(amount) filter (where status='VERIFIED'),0) verified, count(*) n
                               from payments where employee_id=$1 and (created_at at time zone 'UTC')::date = $2""", uuid.UUID(qc.TEST_EMPLOYEE_ID), utc_day)
    check("8 employee collections today: API total/verified = DB (employee_id only)",
          D(str(s["collections_total_amount"])) == D(db["total"]) and D(str(s["collections_verified_amount"])) == D(db["verified"]),
          f"API {s['collections_total_amount']}/{s['collections_verified_amount']} DB {db['total']}/{db['verified']}")
    tally_with_emp = await con.fetchval("select count(*) from payments where source='TALLY' and source_reference like 'TEST-QA-VCH-%' and employee_id is not null")
    check("8 no Tally receipt is attributed to an employee", tally_with_emp == 0)
    pay = await con.fetch("select status, count(*) n, sum(amount) amt from payments where id = any($1::uuid[]) group by 1", [uuid.UUID(x) for x in m["payment_ids"]])
    print("   field collections by status:", {r["status"]: (r["n"], str(r["amt"])) for r in pay})
    first = await con.fetchrow("select p.amount, p.status, p.payment_method, p.payment_date, c.outlet_code from payments p join customers c on c.id=p.customer_id where p.id=$1", uuid.UUID(m["payment_ids"][0]))
    samples["employee_collection"] = (first["outlet_code"], str(first["amount"]), first["status"], first["payment_method"], str(first["payment_date"]))

    # 9: dashboard totals (same formulas as the app's EmployeeDashboardCalculator)
    print("   dashboard: portfolio outstanding", api_out_total, "| past due", sum((v for k, v in api_buckets.items() if k not in ("Not yet due", "No due date")), D("0")),
          "| verified today", s["collections_verified_amount"], "| recorded today", s["collections_total_amount"])
    print("SAMPLES:")
    for k, v in samples.items():
        print("  ", k, v)
    print("ALL CHECKS PASSED" if ok else "SOME CHECKS FAILED")
    await con.close()


asyncio.run(main())
