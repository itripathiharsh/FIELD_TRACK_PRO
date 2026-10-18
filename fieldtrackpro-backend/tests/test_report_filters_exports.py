"""
Reports & Collections: filter semantics (IST dates, snapshot flow-vs-stock, fan-out
dedupe, live-invoice fallback) and Excel / PDF exports - proven against INDEPENDENT
SQL ground truth on multi-month synthetic data.

Requires a THROWAWAY migrated database (the DB name must contain "_rf", e.g.
``fieldtrackpro_rf``): the module seeds and then deletes its own ``RFX`` rows.

Run (one file at a time):
    DATABASE_URL=postgresql+asyncpg://.../fieldtrackpro_rf pytest tests/test_report_filters_exports.py
"""
from __future__ import annotations

import io
import os
import re
import uuid
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import openpyxl
import psycopg2
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.core.security import create_access_token, hash_password
from app.main import app
from app.services.report_exports import fmt_inr, pdf_fonts
from app.services.report_filters import (
    IST,
    SnapshotWindow,
    ist_window,
    parse_month,
    resolve_snapshot_window,
)

DSN = os.environ.get("DATABASE_URL", "").replace("postgresql+asyncpg://", "postgresql://")
_DB_NAME = DSN.rsplit("/", 1)[-1] if DSN else ""
pytestmark = pytest.mark.skipif(
    "_rf" not in _DB_NAME, reason="requires the throwaway database fieldtrackpro_rf"
)

API = "/api/v1"
D = Decimal
BRANDS = ("USHA", "VU")
SNAP_DATES = (date(2026, 7, 31), date(2026, 8, 31), date(2026, 9, 30))
BULK = 1100


# =============================================================================== seed
class World:
    pass


def _cur():
    conn = psycopg2.connect(DSN)
    conn.autocommit = True
    return conn, conn.cursor()


def _purge(cur):
    cur.execute("select id from customers where name like 'RFX%'")
    ids = [r[0] for r in cur.fetchall()]
    if ids:
        for sql in (
            "delete from geo_verification_logs where visit_id in (select id from visits where customer_id = any(%s::uuid[]))",
            "delete from payment_brand_allocations where payment_id in (select id from payments where customer_id = any(%s::uuid[]))",
            "delete from payments where customer_id = any(%s::uuid[])",
            "delete from invoices where customer_id = any(%s::uuid[])",
            "delete from visits where customer_id = any(%s::uuid[])",
            "delete from outlet_financial_snapshots where customer_id = any(%s::uuid[])",
            "delete from employee_customer_assignments where customer_id = any(%s::uuid[])",
            "delete from customers where id = any(%s::uuid[])",
        ):
            cur.execute(sql, (ids,))
    cur.execute("delete from employee_area_assignments where employee_id in (select id from employees where employee_code like 'RFX%')")
    cur.execute("delete from employees where employee_code like 'RFX%'")
    cur.execute("delete from users where email like 'rfx-%'")
    cur.execute("delete from areas where name like 'RFX%'")
    cur.execute("delete from territories where name like 'RFX%'")


@pytest.fixture(scope="module")
def world():
    conn, cur = _cur()
    _purge(cur)
    w = World()
    w.pw = hash_password("Rfx!Test2026")
    w.admin_id = str(uuid.uuid4())
    cur.execute(
        "insert into users (id,email,password_hash,role,is_active,created_at,updated_at) values (%s,%s,%s,'ADMIN',true,now(),now())",
        (w.admin_id, "rfx-admin@fieldtrack.test", w.pw),
    )
    w.emp_user_id = str(uuid.uuid4())
    cur.execute(
        "insert into users (id,email,password_hash,role,is_active,created_at,updated_at) values (%s,%s,%s,'EMPLOYEE',true,now(),now())",
        (w.emp_user_id, "rfx-emp-login@fieldtrack.test", w.pw),
    )
    w.zones, w.areas, w.emps, w.cust = {}, {}, {}, {}
    for z in ("North", "South"):
        w.zones[z] = str(uuid.uuid4())
        cur.execute("insert into territories (id,name,created_at) values (%s,%s,now())", (w.zones[z], f"RFX Zone {z}"))
    for a, z in (("A1", "North"), ("A2", "North"), ("A3", "South")):
        w.areas[a] = str(uuid.uuid4())
        cur.execute("insert into areas (id,name,territory_id,created_at,updated_at) values (%s,%s,%s,now(),now())",
                    (w.areas[a], f"RFX Area {a}", w.zones[z]))
    for k, name, code, zone in (("E1", "RFX Emp Alpha", "RFX01", "North"), ("E2", "RFX Emp Beta", "RFX02", "South"),
                                ("E3", "RFX Emp Gamma", "RFX03", "North")):
        uid = str(uuid.uuid4())
        cur.execute("insert into users (id,email,password_hash,role,is_active,created_at,updated_at) values (%s,%s,%s,'EMPLOYEE',true,now(),now())",
                    (uid, f"rfx-{k.lower()}@fieldtrack.test", w.pw))
        w.emps[k] = str(uuid.uuid4())
        cur.execute("insert into employees (id,user_id,full_name,employee_code,territory_id,created_at) values (%s,%s,%s,%s,%s,now())",
                    (w.emps[k], uid, name, code, w.zones[zone]))
    for e, a in (("E1", "A1"), ("E1", "A2"), ("E3", "A1"), ("E2", "A3")):
        cur.execute("insert into employee_area_assignments (id,employee_id,area_id,created_by,created_at) values (gen_random_uuid(),%s,%s,%s,now())",
                    (w.emps[e], w.areas[a], w.admin_id))

    spec = [("O1", "RFX Outlet One", "RFXO1", "North", "A1", ("E1", "E3")),
            ("O2", "RFX Outlet Two", "RFXO2", "North", "A2", ("E1",)),
            ("O3", "RFX Outlet Three", "RFXO3", "South", "A3", ("E2",)),
            ("O4", "RFX Outlet Four", "RFXO4", "South", "A3", ("E2",))]
    for k, name, code, zone, area, emps in spec:
        cid = str(uuid.uuid4())
        w.cust[k] = cid
        cur.execute(
            "insert into customers (id,name,outlet_code,contact_number,address,geofence_radius_m,territory_id,area_id,created_by,created_at,updated_at) "
            "values (%s,%s,%s,'+919999900001','RFX address',75,%s,%s,%s,now(),now())",
            (cid, name, code, w.zones[zone], w.areas[area], w.admin_id),
        )
        for e in emps:
            cur.execute("insert into employee_customer_assignments (id,employee_id,customer_id,created_by,created_at) values (gen_random_uuid(),%s,%s,%s,now())",
                        (w.emps[e], cid, w.admin_id))
    # snapshots: 4 outlets x 2 brands x 3 months, deliberately different each month
    for oi, k in enumerate(("O1", "O2", "O3", "O4"), 1):
        for bi, br in enumerate(BRANDS):
            for mi, sd in enumerate(SNAP_DATES):
                sales = D(1000 * (oi * 100 + bi * 10 + mi + 1))
                coll = (sales * D("0.4")).quantize(D("0.01"))
                osv = sales - coll
                b = [D(0)] * 7
                if mi == 0:
                    b[6] = osv
                elif mi == 1:
                    b[4], b[5] = osv / 2, osv - osv / 2
                else:
                    b[3] = osv if oi == 4 else D(0)
                    if oi != 4:
                        b[0], b[1] = osv / 2, osv - osv / 2
                cur.execute(
                    "insert into outlet_financial_snapshots (id,customer_id,brand,snapshot_date,sales,collection,market_outstanding,"
                    "bucket_lt_15,bucket_15_30,bucket_30_45,bucket_45_60,bucket_60_75,bucket_75_90,bucket_gt_90,created_at,updated_at) "
                    "values (gen_random_uuid(),%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,now(),now())",
                    (w.cust[k], br, sd, sales, coll, osv, *b),
                )
    # bulk outlets (>1000 rows), one snapshot each
    cur.execute(
        "insert into customers (id,name,outlet_code,contact_number,address,geofence_radius_m,territory_id,area_id,created_by,created_at,updated_at) "
        "select gen_random_uuid(), 'RFX Bulk '||lpad(g::text,4,'0'), 'RFXB'||lpad(g::text,4,'0'), '+919999900002','RFX bulk',75,%s,%s,%s,now(),now() "
        "from generate_series(1,%s) g",
        (w.zones["South"], w.areas["A3"], w.admin_id, BULK),
    )
    cur.execute(
        "insert into outlet_financial_snapshots (id,customer_id,brand,snapshot_date,sales,collection,market_outstanding,bucket_lt_15,bucket_gt_90,created_at,updated_at) "
        "select gen_random_uuid(), id, 'USHA', %s, 100, 40, 60, 60, 0, now(), now() from customers where name like 'RFX Bulk%%'",
        (date(2026, 9, 30),),
    )
    # live invoices / payments in May 2026 (no snapshot that month -> LIVE_INVOICES fallback) + Oct 2026
    inv = [("O1", "2026-05-10", 5000, "USHA"), ("O1", "2026-05-20", 700, "VU"), ("O2", "2026-05-15", 3000, "USHA"),
           ("O3", "2026-05-05", 1200, "VU"), ("O1", "2026-10-03", 900, "USHA"), ("O2", "2026-10-05", 400, "VU")]
    w.inv = []
    for k, d, amt, br in inv:
        num = f"RFX-INV-{k}-{d}-{br}"
        cur.execute("insert into invoices (id,customer_id,invoice_number,invoice_date,amount,brand,source,created_by,created_at,updated_at) "
                    "values (gen_random_uuid(),%s,%s,%s,%s,%s,'TALLY',%s,now(),now())", (w.cust[k], num, d, amt, br, w.admin_id))
        w.inv.append((k, date.fromisoformat(d), D(amt), br))
    pay = [("O1", "2026-05-12", 2000, "USHA", "VERIFIED"), ("O2", "2026-05-18", 500, "USHA", "VERIFIED"),
           ("O1", "2026-05-25", 300, "VU", "PENDING_VERIFICATION"), ("O3", "2026-10-02", 250, "VU", "VERIFIED"),
           ("O1", "2026-10-09", 175, "USHA", "VERIFIED")]
    w.pay = []
    for k, d, amt, br, st in pay:
        pid = str(uuid.uuid4())
        cur.execute("insert into payments (id,customer_id,employee_id,amount,payment_method,payment_date,status,source,created_by,created_at,updated_at) "
                    "values (%s,%s,%s,%s,'CASH',%s,%s,'TALLY',%s,now(),now())", (pid, w.cust[k], w.emps["E1"], amt, d, st, w.admin_id))
        cur.execute("insert into payment_brand_allocations (id,payment_id,brand,allocated_amount,created_at,updated_at) values (gen_random_uuid(),%s,%s,%s,now(),now())", (pid, br, amt))
        w.pay.append((k, date.fromisoformat(d), D(amt), br, st))
    # visits (UTC instants) - the 20:03Z one is 01:33 IST on 1 Oct
    vis = [("O1", "E1", "2026-09-29T10:00:00+00:00", "COMPLETED"), ("O1", "E1", "2026-09-30T18:29:00+00:00", "COMPLETED"),
           ("O2", "E1", "2026-09-30T18:30:00+00:00", "PENDING"), ("O2", "E3", "2026-09-30T20:03:00+00:00", "COMPLETED"),
           ("O3", "E2", "2026-10-01T05:00:00+00:00", "MISSED"), ("O3", "E2", "2026-10-01T18:29:59+00:00", "COMPLETED"),
           ("O4", "E2", "2026-10-01T18:30:00+00:00", "FLAGGED"), ("O4", "E2", "2026-08-15T09:00:00+00:00", "COMPLETED")]
    w.vis, w.visit_ids = [], {}
    for k, e, t, st in vis:
        vid = str(uuid.uuid4())
        dt = datetime.fromisoformat(t)
        ci = dt if st in ("COMPLETED", "FLAGGED") else None
        co = dt + timedelta(minutes=17) if st == "COMPLETED" else None
        cur.execute("insert into visits (id,customer_id,employee_id,scheduled_at,status,check_in_at,check_out_at,synced,created_by,created_at,updated_at,visit_type) "
                    "values (%s,%s,%s,%s,%s,%s,%s,false,%s,now(),now(),'PLANNED')", (vid, w.cust[k], w.emps[e], dt, st, ci, co, w.admin_id))
        w.vis.append((vid, k, e, dt, st))
        w.visit_ids[t] = vid
    # geo logs on two visits (UTC instants 20:03Z and 18:29Z)
    for t in ("2026-09-30T20:03:00+00:00", "2026-09-30T18:29:00+00:00"):
        cur.execute(
            "insert into geo_verification_logs (id,visit_id,device_location,distance_from_customer_m,is_valid,verification_type,attempted_at) "
            "values (gen_random_uuid(),%s,ST_SetSRID(ST_MakePoint(77.5,12.9),4326)::geography,12.5,true,'CHECK_IN',%s)",
            (w.visit_ids[t], datetime.fromisoformat(t)),
        )
    yield w
    _purge(cur)
    conn.close()


@pytest_asyncio.fixture
async def client(world):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://rf") as c:
        yield c
    from app.database import engine
    await engine.dispose()


@pytest.fixture
def H(world):
    return {"Authorization": f"Bearer {create_access_token(world.admin_id, 'ADMIN')}"}


# =============================================================================== ground truth (independent SQL)
@pytest.fixture
def q(world):
    conn, cur = _cur()
    yield cur
    conn.close()


def _scope_customers(cur, w, zone=None, area=None, emp=None):
    cur.execute("select id, territory_id, area_id from customers where name like 'RFX%'")
    out = {}
    for cid, t, a in cur.fetchall():
        cid = str(cid)
        if zone and str(t) != w.zones[zone]:
            continue
        if area and str(a) != w.areas[area]:
            continue
        out[cid] = (str(t), str(a))
    if emp:
        cur.execute("select customer_id from employee_customer_assignments where employee_id=%s", (w.emps[emp],))
        mine = {str(r[0]) for r in cur.fetchall()}
        out = {k: v for k, v in out.items() if k in mine}
    return out


def gt_snapshots(cur, w, start=None, end=None, brand=None, zone=None, area=None, emp=None):
    """flows summed, stock = latest snapshot per (customer, brand) in window."""
    scope = _scope_customers(cur, w, zone, area, emp)
    cur.execute("select customer_id, brand, snapshot_date, sales, collection, market_outstanding, bucket_gt_90, bucket_lt_15, bucket_15_30, "
                "bucket_30_45, bucket_45_60, bucket_60_75, bucket_75_90 from outlet_financial_snapshots")
    groups = defaultdict(list)
    for r in cur.fetchall():
        cid = str(r[0])
        if cid not in scope:
            continue
        if start and r[2] < start:
            continue
        if end and r[2] > end:
            continue
        if brand and r[1].lower() != brand.lower():
            continue
        groups[(cid, r[1])].append(r)
    rows = {}
    for key, lst in groups.items():
        lst.sort(key=lambda r: r[2])
        last = lst[-1]
        rows[key] = dict(
            sales=sum(r[3] for r in lst), collection=sum(r[4] for r in lst), os=last[5], gt90=last[6],
            buckets=[last[7], last[8], last[9], last[10], last[11], last[12], last[6]], as_of=last[2], n=len(lst),
        )
    return rows


def totals_of(rows):
    return dict(
        sales=sum((r["sales"] for r in rows.values()), D(0)), collection=sum((r["collection"] for r in rows.values()), D(0)),
        os=sum((r["os"] for r in rows.values()), D(0)), gt90=sum((r["gt90"] for r in rows.values()), D(0)),
        outlets=len({k[0] for k in rows}),
    )


def dec(x):
    return D(str(x))


async def get(client, H, path, **params):
    params = {k: v for k, v in params.items() if v is not None}
    r = await client.get(f"{API}{path}", params=params, headers=H)
    return r


WINDOWS = {
    "all": dict(),
    "month_aug": dict(month="2026-08"),
    "day_sep30": dict(start_date="2026-09-30", end_date="2026-09-30"),
    "span_jul_aug": dict(start_date="2026-07-01", end_date="2026-08-31"),
    "span_aug_sep": dict(start_date="2026-08-15", end_date="2026-10-15"),
    "from_aug": dict(start_date="2026-08-01"),
    "until_aug": dict(end_date="2026-08-31"),
}


def _win_dates(p):
    if "start_date" in p or "end_date" in p:
        return (date.fromisoformat(p["start_date"]) if "start_date" in p else None,
                date.fromisoformat(p["end_date"]) if "end_date" in p else None)
    if "month" in p:
        s, e = parse_month(p["month"])
        return s, e
    return None, None


# =============================================================================== pure helpers
def test_ist_window_boundaries():
    lo, hi = ist_window(date(2026, 10, 1), date(2026, 10, 1))
    assert lo == datetime(2026, 9, 30, 18, 30, tzinfo=timezone.utc)
    assert hi == datetime(2026, 10, 1, 18, 30, tzinfo=timezone.utc)
    t = datetime(2026, 9, 30, 20, 3, tzinfo=timezone.utc)  # 01:33 IST on 1 Oct
    assert lo <= t < hi
    assert ist_window(None, None) == (None, None)


def test_month_and_window_resolution():
    assert parse_month("2026-02") == (date(2026, 2, 1), date(2026, 2, 28))
    assert parse_month(None) is None and parse_month("ALL") is None
    w = resolve_snapshot_window("2026-07", date(2026, 9, 1), date(2026, 9, 30))
    assert (w.start, w.end, w.source, w.month_ignored) == (date(2026, 9, 1), date(2026, 9, 30), "DATES", True)
    assert resolve_snapshot_window("2026-07", None, None).source == "MONTH"
    assert resolve_snapshot_window(None, None, None).is_all


@pytest.mark.asyncio
async def test_invalid_inputs_422(client, H):
    for path, params in (
        ("/reports/business-summary", dict(start_date="2026-09-30", end_date="2026-09-01")),
        ("/reports/outstanding", dict(month="2026-13")),
        ("/reports/outstanding", dict(month="bogus")),
        ("/reports/outstanding", dict(ageing_bucket="nope")),
        ("/reports/visits-detailed", dict(start_date="2026-10-02", end_date="2026-10-01")),
        ("/reports/outstanding/export", dict(format="csv")),
        ("/collections/overview/export", dict(start_date="2026-10-02", end_date="2026-10-01")),
    ):
        r = await get(client, H, path, **params)
        assert r.status_code == 422, (path, params, r.status_code, r.text[:200])


@pytest.mark.asyncio
async def test_exports_require_admin(client, world):
    r = await client.get(f"{API}/reports/outstanding/export")
    assert r.status_code == 401
    emp = {"Authorization": f"Bearer {create_access_token(world.emp_user_id, 'EMPLOYEE')}"}
    for p in ("/reports/outstanding/export", "/reports/employees/export", "/collections/overview/export",
              "/reports/geo-verification/export", "/reports/monthly-periods/export"):
        assert (await client.get(f"{API}{p}", headers=emp)).status_code == 403, p


# =============================================================================== BI
@pytest.mark.asyncio
@pytest.mark.parametrize("name", [n for n in WINDOWS if n != "span_aug_sep"] + ["span_aug_sep"])
async def test_bi_window_matches_ground_truth_flow_vs_stock(client, H, q, world, name):
    p = WINDOWS[name]
    r = await get(client, H, "/reports/business-summary", **p)
    assert r.status_code == 200, r.text
    d = r.json()
    s, e = _win_dates(p)
    gt = gt_snapshots(q, world, s, e)
    t = totals_of(gt)
    assert d["data_source"] == "SNAPSHOT"
    assert dec(d["total_sales"]) == t["sales"]
    assert dec(d["total_collection"]) == t["collection"]
    assert dec(d["total_market_outstanding"]) == t["os"]
    assert dec(d["total_overdue_gt_90"]) == t["gt90"]
    assert d["total_outlets"] == t["outlets"]
    assert d["as_of_date"] == max(r_["as_of"] for r_ in gt.values()).isoformat()
    # per-brand summary rows
    by_brand = defaultdict(lambda: D(0))
    for (cid, br), row in gt.items():
        by_brand[br] += row["os"]
    for row in d["brand_summaries"]:
        assert dec(row["market_outstanding"]) == by_brand[row["brand"]]


@pytest.mark.asyncio
async def test_bi_stock_not_summed_across_snapshots(client, H, q, world):
    all_ = (await get(client, H, "/reports/business-summary")).json()
    latest = gt_snapshots(q, world, None, date(2026, 9, 30))
    naive = sum((dec(x) for x in [r_[0] for r_ in _all_os(q)]), D(0))
    assert dec(all_["total_market_outstanding"]) == totals_of(latest)["os"]
    assert dec(all_["total_market_outstanding"]) != naive  # the old behaviour summed every snapshot
    sep = (await get(client, H, "/reports/business-summary", month="2026-09")).json()
    assert dec(sep["total_market_outstanding"]) == dec(all_["total_market_outstanding"])  # latest month == latest snapshot
    assert dec(all_["total_sales"]) > dec(sep["total_sales"])  # flows DO accumulate over the period


def _all_os(cur):
    cur.execute("select market_outstanding from outlet_financial_snapshots where customer_id in (select id from customers where name like 'RFX%')")
    return cur.fetchall()


@pytest.mark.asyncio
async def test_bi_date_range_wins_over_month_and_empty_range_falls_back_explicitly(client, H, q, world):
    d = (await get(client, H, "/reports/business-summary", month="2026-07", start_date="2026-09-01", end_date="2026-09-30")).json()
    sep = (await get(client, H, "/reports/business-summary", month="2026-09")).json()
    assert d["month_ignored"] is True and d["period_source"] == "DATES" and d["month_period"] is None
    assert dec(d["total_sales"]) == dec(sep["total_sales"]) and dec(d["total_market_outstanding"]) == dec(sep["total_market_outstanding"])
    # a range with NO snapshots anywhere -> explicit LIVE_INVOICES source with a note, filtered by the window
    live = (await get(client, H, "/reports/business-summary", start_date="2026-05-01", end_date="2026-05-31")).json()
    assert live["data_source"] == "LIVE_INVOICES" and "live Tally invoices" in live["data_source_note"]
    exp_sales = sum((a for k, d_, a, b in world.inv if date(2026, 5, 1) <= d_ <= date(2026, 5, 31)), D(0))
    exp_coll = sum((a for k, d_, a, b, st in world.pay if date(2026, 5, 1) <= d_ <= date(2026, 5, 31) and st == "VERIFIED"), D(0))
    assert dec(live["total_sales"]) == exp_sales == D(9900)
    assert dec(live["total_collection"]) == exp_coll == D(2500)
    # month param also respected on the fallback, and brand filter respected by the fallback
    live_m = (await get(client, H, "/reports/business-summary", month="2026-05", brand="VU")).json()
    assert live_m["data_source"] == "LIVE_INVOICES"
    assert dec(live_m["total_sales"]) == D(700 + 1200)
    assert dec(live_m["total_collection"]) == D(0)  # the only VU payment in May is PENDING
    assert [b["brand"] for b in live_m["brand_summaries"]] == ["VU"]
    # a filter that matches nothing inside a period that HAS snapshots stays SNAPSHOT (no silent source mix)
    none = (await get(client, H, "/reports/business-summary", month="2026-09", brand="Nonexistent")).json()
    assert none["data_source"] == "SNAPSHOT" and none["total_outlets"] == 0 and dec(none["total_sales"]) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("flt", [
    dict(brand="USHA"), dict(brand="vu"), dict(zone="North"), dict(area="A3"), dict(emp="E1"), dict(emp="E3"),
    dict(brand="USHA", zone="South"), dict(brand="VU", emp="E2", area="A3"),
])
async def test_bi_each_filter_alone_and_combined(client, H, q, world, flt):
    params = {}
    if "brand" in flt:
        params["brand"] = flt["brand"]
    if "zone" in flt:
        params["zone_id"] = world.zones[flt["zone"]]
    if "area" in flt:
        params["area_id"] = world.areas[flt["area"]]
    if "emp" in flt:
        params["employee_id"] = world.emps[flt["emp"]]
    for win in ("all", "day_sep30", "span_jul_aug"):
        d = (await get(client, H, "/reports/business-summary", **params, **WINDOWS[win])).json()
        s, e = _win_dates(WINDOWS[win])
        gt = totals_of(gt_snapshots(q, world, s, e, brand=flt.get("brand"), zone=flt.get("zone"), area=flt.get("area"), emp=flt.get("emp")))
        assert (dec(d["total_sales"]), dec(d["total_collection"]), dec(d["total_market_outstanding"]), d["total_outlets"]) == \
               (gt["sales"], gt["collection"], gt["os"], gt["outlets"]), (flt, win)


# =============================================================================== outstanding / outlets / collections report
def _out_rows(gt):
    return {k: v for k, v in gt.items() if v["os"] > 0}


@pytest.mark.asyncio
@pytest.mark.parametrize("name", list(WINDOWS))
async def test_outstanding_is_latest_snapshot_per_outlet_brand(client, H, q, world, name):
    p = WINDOWS[name]
    rows = []
    skip = 0
    while True:
        r = await get(client, H, "/reports/outstanding", **p, skip=skip, limit=200)
        assert r.status_code == 200, r.text
        chunk = r.json()
        rows += chunk
        if len(chunk) < 200:
            break
        skip += 200
    s, e = _win_dates(p)
    gt = _out_rows(gt_snapshots(q, world, s, e))
    assert len(rows) == len(gt)
    got = {(r_["customer_id"], r_["brand"]): r_ for r_ in rows}
    for (cid, br), row in gt.items():
        g = got[(cid, br)]
        assert dec(g["market_outstanding"]) == row["os"] and dec(g["bucket_gt_90"]) == row["gt90"]
        assert g["as_of_date"] == row["as_of"].isoformat()


@pytest.mark.asyncio
async def test_outstanding_each_filter_and_ageing_bucket_and_search(client, H, q, world):
    base = dict(month="2026-08")
    gt = _out_rows(gt_snapshots(q, world, *_win_dates(base)))
    # ageing bucket (Aug has 60-75 + 75-90 only)
    r = (await get(client, H, "/reports/outstanding", **base, ageing_bucket="75-90")).json()
    assert len(r) == len(gt) > 0
    assert (await get(client, H, "/reports/outstanding", **base, ageing_bucket=">90")).json() == []
    # employee, zone, brand, area
    for k, params, kw in (
        ("emp", dict(employee_id=world.emps["E3"]), dict(emp="E3")),
        ("zone", dict(zone_id=world.zones["South"]), dict(zone="South")),
        ("brand", dict(brand="VU"), dict(brand="VU")),
        ("area", dict(area_id=world.areas["A2"]), dict(area="A2")),
    ):
        got = (await get(client, H, "/reports/outstanding", **base, **params)).json()
        exp = _out_rows(gt_snapshots(q, world, *_win_dates(base), **kw))
        assert len(got) == len(exp) > 0, k
    # search by outlet name, DMS code, zone, employee name; each changes the result
    for text, expect in (("Outlet Three", {"O3"}), ("RFXO2", {"O2"}), ("Zone North", {"O1", "O2"}), ("Gamma", {"O1"})):
        got = (await get(client, H, "/reports/outstanding", **base, query=text)).json()
        assert {r_["customer_id"] for r_ in got} == {world.cust[k] for k in expect}, text
    # unknown search -> empty
    assert (await get(client, H, "/reports/outstanding", query="zzz-no-such")).json() == []


@pytest.mark.asyncio
async def test_outlets_report_dedupes_multi_employee_outlet(client, H, q, world):
    rows = []
    for skip in range(0, 2000, 200):
        chunk = (await get(client, H, "/reports/outlets", skip=skip, limit=200)).json()
        rows += chunk
        if len(chunk) < 200:
            break
    ids = [r_["customer_id"] for r_ in rows]
    assert len(ids) == len(set(ids)) == 4 + BULK  # exactly one row per outlet
    o1 = next(r_ for r_ in rows if r_["customer_id"] == world.cust["O1"])
    assert o1["fos_name"] == "RFX Emp Alpha, RFX Emp Gamma"
    # financials follow the window semantics
    gt = totals_of({k: v for k, v in gt_snapshots(q, world).items() if k[0] == world.cust["O1"]})
    assert dec(o1["sales"]) == gt["sales"] and dec(o1["market_outstanding"]) == gt["os"]
    # employee filter on a shared outlet: returns it once
    mine = (await get(client, H, "/reports/outlets", employee_id=world.emps["E3"])).json()
    assert [r_["customer_id"] for r_ in mine] == [world.cust["O1"]]
    # window changes the figures but not the outlet list
    aug = {r_["customer_id"]: r_ for r_ in (await get(client, H, "/reports/outlets", month="2026-08", query="RFXO", limit=200)).json()}
    gt_aug = gt_snapshots(q, world, *_win_dates(dict(month="2026-08")))
    o1_aug = totals_of({k: v for k, v in gt_aug.items() if k[0] == world.cust["O1"]})
    assert dec(aug[world.cust["O1"]]["sales"]) == o1_aug["sales"] != gt["sales"]


@pytest.mark.asyncio
@pytest.mark.parametrize("name", ["all", "month_aug", "day_sep30", "span_jul_aug"])
async def test_collections_report_flows_summed(client, H, q, world, name):
    p = WINDOWS[name]
    rows, skip = [], 0
    while True:
        chunk = (await get(client, H, "/reports/collections", **p, skip=skip, limit=200)).json()
        rows += chunk
        if len(chunk) < 200:
            break
        skip += 200
    s, e = _win_dates(p)
    gt = {k: v for k, v in gt_snapshots(q, world, s, e).items() if v["collection"] > 0}
    assert len(rows) == len(gt)
    assert sum((dec(r_["collection_amount"]) for r_ in rows), D(0)) == sum((v["collection"] for v in gt.values()), D(0))
    assert sum((dec(r_["sales_amount"]) for r_ in rows), D(0)) == sum((v["sales"] for v in gt.values()), D(0))


# =============================================================================== visits / geo / staff (IST)
def _ist_date(dt):
    return dt.astimezone(IST).date()


@pytest.mark.asyncio
@pytest.mark.parametrize("start,end", [
    ("2026-10-01", "2026-10-01"), ("2026-09-30", "2026-09-30"), ("2026-09-29", "2026-09-30"),
    ("2026-09-01", "2026-10-31"), ("2026-12-01", "2026-12-31"), ("2026-10-02", None), (None, "2026-08-31"),
])
async def test_visits_staff_geo_use_ist_day_windows(client, H, world, start, end):
    sd = date.fromisoformat(start) if start else None
    ed = date.fromisoformat(end) if end else None
    exp = [v for v in world.vis if (not sd or _ist_date(v[3]) >= sd) and (not ed or _ist_date(v[3]) <= ed)]
    r = await get(client, H, "/reports/visits-detailed", start_date=start, end_date=end, limit=200)
    assert r.status_code == 200
    assert {x["visit_id"] for x in r.json()} == {v[0] for v in exp}
    staff = (await get(client, H, "/reports/employees", start_date=start, end_date=end)).json()
    for k in ("E1", "E2", "E3"):
        row = next(x for x in staff if x["employee_id"] == world.emps[k])
        assert row["total_visits"] == sum(1 for v in exp if v[2] == k), (k, start, end)
    geo = (await get(client, H, "/reports/geo-verification", start_date=start, end_date=end)).json()
    geo_exp = {world.visit_ids[t] for t in ("2026-09-30T20:03:00+00:00", "2026-09-30T18:29:00+00:00")
               if (not sd or _ist_date(datetime.fromisoformat(t)) >= sd) and (not ed or _ist_date(datetime.fromisoformat(t)) <= ed)}
    assert {x["visit_id"] for x in geo} == geo_exp


@pytest.mark.asyncio
async def test_ist_boundary_visit_2003utc_counts_on_next_ist_day(client, H, world):
    vid = world.visit_ids["2026-09-30T20:03:00+00:00"]
    on_30 = {x["visit_id"] for x in (await get(client, H, "/reports/visits-detailed", start_date="2026-09-30", end_date="2026-09-30")).json()}
    on_01 = {x["visit_id"] for x in (await get(client, H, "/reports/visits-detailed", start_date="2026-10-01", end_date="2026-10-01")).json()}
    assert vid not in on_30 and vid in on_01
    geo_30 = (await get(client, H, "/reports/geo-verification", start_date="2026-09-30", end_date="2026-09-30")).json()
    geo_01 = (await get(client, H, "/reports/geo-verification", start_date="2026-10-01", end_date="2026-10-01")).json()
    assert vid not in {x["visit_id"] for x in geo_30} and vid in {x["visit_id"] for x in geo_01}


@pytest.mark.asyncio
async def test_visit_staff_geo_filters_alone_and_combined(client, H, world):
    allv = world.vis
    def ids(r): return {x["visit_id"] for x in r.json()}
    r = await get(client, H, "/reports/visits-detailed", employee_id=world.emps["E3"]); assert ids(r) == {v[0] for v in allv if v[2] == "E3"}
    r = await get(client, H, "/reports/visits-detailed", zone_id=world.zones["South"]); assert ids(r) == {v[0] for v in allv if v[1] in ("O3", "O4")}
    r = await get(client, H, "/reports/visits-detailed", area_id=world.areas["A1"]); assert ids(r) == {v[0] for v in allv if v[1] == "O1"}
    r = await get(client, H, "/reports/visits-detailed", status="COMPLETED"); assert ids(r) == {v[0] for v in allv if v[4] == "COMPLETED"}
    r = await get(client, H, "/reports/visits-detailed", query="outlet four"); assert ids(r) == {v[0] for v in allv if v[1] == "O4"}
    r = await get(client, H, "/reports/visits-detailed", query="rfx02", status="COMPLETED", start_date="2026-10-01", end_date="2026-10-01")
    assert ids(r) == {v[0] for v in allv if v[2] == "E2" and v[4] == "COMPLETED" and _ist_date(v[3]) == date(2026, 10, 1)}
    # Field Staff table: search / employee / zone / area are applied
    staff = lambda **kw: get(client, H, "/reports/employees", **kw)
    assert [x["employee_code"] for x in (await staff(query="gamma")).json()] == ["RFX03"]
    assert [x["employee_code"] for x in (await staff(employee_id=world.emps["E2"])).json()] == ["RFX02"]
    assert {x["employee_code"] for x in (await staff(zone_id=world.zones["North"])).json()} >= {"RFX01", "RFX03"}
    assert "RFX02" not in {x["employee_code"] for x in (await staff(zone_id=world.zones["North"])).json()}
    assert {x["employee_code"] for x in (await staff(area_id=world.areas["A1"])).json()} == {"RFX01", "RFX03"}
    # geo: employee/zone/search
    geo = lambda **kw: get(client, H, "/reports/geo-verification", **kw)
    assert len((await geo(employee_id=world.emps["E3"])).json()) == 1
    assert len((await geo(employee_id=world.emps["E2"])).json()) == 0
    assert len((await geo(query="outlet two")).json()) == 1


# =============================================================================== collections overview (live)
@pytest.mark.asyncio
async def test_collections_overview_period_columns_and_stock_semantics(client, H, q, world):
    base = (await get(client, H, "/collections/overview", search="RFXO", limit=200)).json()
    assert base["totals"]["invoiced_in_period"] is None
    rows = {r_["customer_id"]: r_ for r_ in base["outlets"]}
    # D2: outstanding = LATEST snapshot os + live invoices (no allocations), never summed over snapshots
    gt = gt_snapshots(q, world)
    for k in ("O1", "O2", "O3", "O4"):
        os_snap = sum((v["os"] for (cid, br), v in gt.items() if cid == world.cust[k]), D(0))
        live = sum((a for kk, d_, a, b in world.inv if kk == k), D(0))
        assert dec(rows[world.cust[k]]["total_outstanding"]) == os_snap + live, k
    # period columns
    p = dict(start_date="2026-05-01", end_date="2026-05-31")
    r = (await get(client, H, "/collections/overview", search="RFXO", limit=200, **p)).json()
    assert r["period_start"] == "2026-05-01" and r["as_of_date"] is not None
    for k in ("O1", "O2", "O3", "O4"):
        row = next(x for x in r["outlets"] if x["customer_id"] == world.cust[k])
        inv_exp = sum((a for kk, d_, a, b in world.inv if kk == k and date(2026, 5, 1) <= d_ <= date(2026, 5, 31)), D(0))
        col_exp = sum((a for kk, d_, a, b, st in world.pay if kk == k and st == "VERIFIED" and date(2026, 5, 1) <= d_ <= date(2026, 5, 31)), D(0))
        assert dec(row["invoiced_in_period"]) == inv_exp and dec(row["collected_in_period"]) == col_exp, k
        # outstanding stays as-of-today regardless of the range
        assert row["total_outstanding"] == rows[world.cust[k]]["total_outstanding"]
    assert dec(r["totals"]["invoiced_in_period"]) == D(9900) and dec(r["totals"]["collected_in_period"]) == D(2500)
    # single-day range & empty range
    one = (await get(client, H, "/collections/overview", search="RFXO", start_date="2026-05-10", end_date="2026-05-10")).json()
    assert dec(one["totals"]["invoiced_in_period"]) == D(5000) and dec(one["totals"]["collected_in_period"]) == D(0)
    empty = (await get(client, H, "/collections/overview", search="RFXO", start_date="2027-01-01", end_date="2027-01-02")).json()
    assert dec(empty["totals"]["invoiced_in_period"]) == D(0)
    # existing filters keep working together with the range
    z = (await get(client, H, "/collections/overview", search="RFXO", territory_id=world.zones["South"], **p)).json()
    assert {x["customer_id"] for x in z["outlets"]} == {world.cust["O3"], world.cust["O4"]}
    assert dec(z["totals"]["invoiced_in_period"]) == D(1200)
    e = (await get(client, H, "/collections/overview", search="RFXO", employee_id=world.emps["E3"])).json()
    assert {x["customer_id"] for x in e["outlets"]} >= {world.cust["O1"]}


# =============================================================================== exports
def _xlsx(content: bytes):
    wb = openpyxl.load_workbook(io.BytesIO(content))
    return wb


def _table(ws):
    """-> meta(list of A1..A4), headers, data rows, totals row (or None)"""
    meta = [ws.cell(row=r, column=1).value for r in range(1, 5)]
    headers = [c.value for c in ws[6] if c.value is not None]
    rows, totals = [], None
    for row in ws.iter_rows(min_row=7, max_col=len(headers), values_only=True):
        if all(v is None for v in row):
            continue
        if row[0] == "TOTAL":
            totals = row
        else:
            rows.append(row)
    return meta, headers, rows, totals


def ws_rows(ws):
    return _table(ws)[2]


def _pdf_pages(content: bytes):
    pypdf = pytest.importorskip("pypdf")
    reader = pypdf.PdfReader(io.BytesIO(content))
    return [p.extract_text() or "" for p in reader.pages]


EXPORT_CASES = [
    # (name, path, params(world)->dict, filters that must be echoed (labels))
    ("outstanding", "/reports/outstanding/export", ["Date range", "Month", "Brand", "Zone", "Area", "Employee", "Ageing bucket", "Search"]),
    ("outlets", "/reports/outlets/export", ["Date range", "Month", "Brand", "Zone", "Area", "Employee", "Location status", "Search"]),
    ("collections_report", "/reports/collections/export", ["Date range", "Month", "Brand", "Zone", "Area", "Employee", "Search"]),
    ("visits", "/reports/visits-detailed/export", ["Date range", "Zone", "Area", "Employee", "Status", "Search"]),
    ("geo", "/reports/geo-verification/export", ["Date range", "Zone", "Area", "Employee", "Search"]),
    ("staff", "/reports/employees/export", ["Date range", "Zone", "Area", "Employee", "Search"]),
    ("bi", "/reports/business-summary/export", ["Date range", "Month", "Brand", "Zone", "Area", "Employee"]),
    ("overview", "/reports/overview/export", ["Date range", "Month", "Brand", "Zone", "Area", "Employee"]),
    ("collections_overview", "/collections/overview/export", ["Date range", "Zone", "Area", "Employee", "Status", "Search"]),
    ("monthly", "/reports/monthly-periods/export", ["Periods"]),
    ("employees_master", "/reports/employees-master/export", ["Working profile", "Role", "Active", "Search"]),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("name,path,labels", EXPORT_CASES)
async def test_excel_and_pdf_export_with_and_without_filters(client, H, world, name, path, labels):
    plain_x = await get(client, H, path)
    assert plain_x.status_code == 200, plain_x.text[:300]
    assert "spreadsheetml" in plain_x.headers["content-type"]
    cd = plain_x.headers["content-disposition"]
    assert re.search(r'filename="[A-Za-z_]+_\d{8}_\d{4}\.xlsx"', cd), cd
    assert "_filtered" not in cd
    wb = _xlsx(plain_x.content)
    ws = wb.worksheets[0]
    meta, headers, rows, totals = _table(ws)
    assert meta[0].startswith("FieldTrack Pro - ")
    assert "Generated (IST):" in meta[1] and f"Rows: {len(ws_rows(ws))}" in meta[1]
    assert ws.freeze_panes == "A7" and ws.auto_filter.ref.startswith("A6")
    # every supported filter is echoed even when not set (as "All..."/"None")
    filt_line = ws.cell(row=3, column=1).value
    for lab in labels:
        assert f"{lab}:" in filt_line, (lab, filt_line)
    # PDF
    pdf = await get(client, H, path, format="pdf")
    assert pdf.status_code == 200 and pdf.headers["content-type"] == "application/pdf"
    assert re.search(r'filename="[A-Za-z_]+_\d{8}_\d{4}\.pdf"', pdf.headers["content-disposition"])
    assert pdf.content.startswith(b"%PDF") and pdf.content.rstrip().endswith(b"%%EOF")
    pages = _pdf_pages(pdf.content)
    assert len(pages) >= 1 and "Filters applied:" in pages[0] and f"Page 1 of {len(pages)}" in pages[0]


FILTERED = {
    "outstanding": lambda w: dict(month="2026-08", brand="VU", zone_id=w.zones["North"], area_id=w.areas["A1"],
                                  employee_id=w.emps["E3"], ageing_bucket="75-90", query="outlet"),
    "outlets": lambda w: dict(start_date="2026-08-01", end_date="2026-09-30", brand="USHA", zone_id=w.zones["North"],
                              area_id=w.areas["A1"], employee_id=w.emps["E1"], location_status="MISSING", query="one"),
    "collections_report": lambda w: dict(month="2026-09", brand="USHA", zone_id=w.zones["South"], area_id=w.areas["A3"],
                                         employee_id=w.emps["E2"], query="three"),
    "visits": lambda w: dict(start_date="2026-09-30", end_date="2026-10-01", zone_id=w.zones["North"], area_id=w.areas["A2"],
                             employee_id=w.emps["E3"], status="COMPLETED", query="two"),
    "geo": lambda w: dict(start_date="2026-09-30", end_date="2026-10-01", zone_id=w.zones["North"], area_id=w.areas["A2"],
                          employee_id=w.emps["E3"], query="two"),
    "staff": lambda w: dict(start_date="2026-09-01", end_date="2026-10-31", zone_id=w.zones["North"], area_id=w.areas["A1"],
                            employee_id=w.emps["E3"], query="gamma"),
    "bi": lambda w: dict(month="2026-07", start_date="2026-08-01", end_date="2026-09-30", brand="USHA",
                         zone_id=w.zones["North"], area_id=w.areas["A1"], employee_id=w.emps["E1"]),
    "overview": lambda w: dict(month="2026-09", brand="VU", zone_id=w.zones["South"], area_id=w.areas["A3"], employee_id=w.emps["E2"]),
    "collections_overview": lambda w: dict(start_date="2026-05-01", end_date="2026-05-31", territory_id=w.zones["North"],
                                           area_id=w.areas["A1"], employee_id=w.emps["E1"], collection_status="OVERDUE", search="one"),
}
ECHO = {  # param -> (label, expected substring in the echo)
    "month": ("Month", "2026"), "brand": ("Brand", None), "zone_id": ("Zone", "RFX Zone"), "area_id": ("Area", "RFX Area"),
    "employee_id": ("Employee", "RFX Emp"), "ageing_bucket": ("Ageing bucket", None), "query": ("Search", None),
    "start_date": ("Date range", "2026"), "end_date": ("Date range", "2026"), "status": ("Status", None), "location_status": ("Location status", None),
    "territory_id": ("Zone", "RFX Zone"), "search": ("Search", None), "collection_status": ("Status", None),
}


@pytest.mark.asyncio
@pytest.mark.parametrize("name", list(FILTERED))
async def test_filtered_export_echoes_all_filters_and_matches_json(client, H, world, name):
    path = dict((n, p) for n, p, _ in EXPORT_CASES)[name]
    params = FILTERED[name](world)
    plain = await get(client, H, path)
    filt = await get(client, H, path, **params)
    assert filt.status_code == 200, filt.text[:300]
    assert "_filtered.xlsx" in filt.headers["content-disposition"]
    ws = _xlsx(filt.content).worksheets[0]
    meta, headers, rows, totals = _table(ws)
    line = ws.cell(row=3, column=1).value
    for pkey, val in params.items():
        label, sub = ECHO[pkey]
        assert f"{label}:" in line, (pkey, line)
        shown = line.split(f"{label}:")[1].split("|")[0]
        assert not re.search(r"\bAll\b|None", shown.replace("(ignored", "")) or pkey == "month", (pkey, shown)
        if sub:
            assert sub in shown, (pkey, shown)
        elif isinstance(val, str):
            assert val.lower() in shown.lower(), (pkey, shown)
    if name == "bi":
        assert "ignored - date range applied" in line
    plain_rows = _table(_xlsx(plain.content).worksheets[0])[2]
    assert len(rows) != len(plain_rows) or rows != plain_rows  # filtered export differs from unfiltered
    # PDF echo
    pages = _pdf_pages((await get(client, H, path, format="pdf", **params)).content)
    assert "Filters applied:" in pages[0]


@pytest.mark.asyncio
async def test_outstanding_excel_rows_and_totals_equal_ground_truth(client, H, q, world):
    params = dict(month="2026-08")
    resp = await get(client, H, "/reports/outstanding/export", **params)
    ws = _xlsx(resp.content).worksheets[0]
    meta, headers, rows, totals = _table(ws)
    gt = _out_rows(gt_snapshots(q, world, *_win_dates(params)))
    assert len(rows) == len(gt) == 8
    assert headers[0] == "Brand" and headers[6].startswith("Market OS (")
    os_idx = 6
    assert all(isinstance(r_[os_idx], (int, float)) for r_ in rows)  # numeric cells, not strings
    assert D(str(round(totals[os_idx], 2))) == sum((v["os"] for v in gt.values()), D(0))
    assert D(str(round(sum(r_[os_idx] for r_ in rows), 2))) == D(str(round(totals[os_idx], 2)))
    as_of = headers.index("As of")
    assert all(isinstance(r_[as_of], (datetime, date)) for r_ in rows)  # real date cells
    assert ws.cell(row=7, column=as_of + 1).number_format == "dd-mmm-yyyy"
    assert "##\\,##\\,##" in ws.cell(row=7, column=os_idx + 1).number_format  # Indian grouping
    top = max(gt.values(), key=lambda v: (v["gt90"], v["os"]))
    assert ws.cell(row=7, column=os_idx + 1).value == float(top["os"])  # sorted by >90d then OS, first data row


@pytest.mark.asyncio
async def test_visits_excel_has_real_ist_dates_and_staff_pdf_shows_code_not_uuid(client, H, world):
    resp = await get(client, H, "/reports/visits-detailed/export", start_date="2026-09-30", end_date="2026-10-01")
    ws = _xlsx(resp.content).worksheets[0]
    meta, headers, rows, totals = _table(ws)
    assert headers[0] == "Scheduled Date (IST)"
    assert all(isinstance(r_[0], (datetime, date)) for r_ in rows) and not any(isinstance(r_[0], str) for r_ in rows)
    first_row_fmt = ws.cell(row=7, column=1).number_format
    assert first_row_fmt == "dd-mmm-yyyy"
    # the 20:03Z visit is on 01-Oct (IST) and its check-in is 01:33 IST
    target = next(r_ for r_ in rows if r_[2] == "RFX Outlet Two" and r_[6] == "COMPLETED")
    assert (target[0].year, target[0].month, target[0].day) == (2026, 10, 1)
    assert (target[7].hour, target[7].minute) == (1, 33)
    assert ws.cell(row=7, column=8).number_format == "dd-mmm-yyyy hh:mm"
    pdf = await get(client, H, "/reports/employees/export", format="pdf")
    text = "\n".join(_pdf_pages(pdf.content))
    assert "RFX01" in text and "RFX Emp Alpha" in text
    assert not re.search(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", text)


@pytest.mark.asyncio
async def test_bi_excel_has_all_sheets_and_pdf_view(client, H, q, world):
    resp = await get(client, H, "/reports/business-summary/export", month="2026-08")
    wb = _xlsx(resp.content)
    assert wb.sheetnames == ["Brand Summary", "Zone Summary", "Area Summary", "FOS Summary", "Outlet Data"]
    gt = totals_of(gt_snapshots(q, world, *_win_dates(dict(month="2026-08"))))
    _, hdr, rows, tot = _table(wb["Outlet Data"])
    assert len(rows) == 8 and D(str(round(tot[hdr.index("Sales (₹)")], 2))) == gt["sales"]
    _, hb, rb, tb = _table(wb["Brand Summary"])
    assert D(str(round(tb[hb.index("Market OS (₹)")], 2))) == gt["os"]
    _, hf, rf, tf = _table(wb["FOS Summary"])
    assert tf is None  # fan-out view has no grand total
    note = wb["Brand Summary"].cell(row=2, column=1).value
    assert "latest snapshot" in note and "SNAPSHOT" not in note.upper().replace("SNAPSHOT", "")  # readable note present
    for view in ("brand", "zone", "area", "fos", "raw"):
        pdf = await get(client, H, "/reports/business-summary/export", format="pdf", view=view, month="2026-08")
        assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")


@pytest.mark.asyncio
async def test_empty_export_is_a_valid_file_with_headers_only(client, H, world):
    for path, params in (("/reports/outstanding/export", dict(query="zzz-no-such-thing")),
                         ("/reports/visits-detailed/export", dict(start_date="2030-01-01", end_date="2030-01-02")),
                         ("/collections/overview/export", dict(search="zzz-no-such-thing")),
                         ("/reports/employees/export", dict(query="zzz-no-such-thing"))):
        x = await get(client, H, path, **params)
        assert x.status_code == 200
        ws = _xlsx(x.content).worksheets[0]
        meta, headers, rows, totals = _table(ws)
        assert len(headers) >= 6 and rows == [] and totals is None and "Rows: 0" in meta[1]
        pdf = await get(client, H, path, format="pdf", **params)
        pages = _pdf_pages(pdf.content)
        assert pdf.content.startswith(b"%PDF") and "No rows match" in "\n".join(pages)


@pytest.mark.asyncio
async def test_large_export_not_truncated_xlsx_and_pdf(client, H, q, world):
    # 1,104 outlets: far above any JSON page (200) and above 1000
    x = await get(client, H, "/reports/outlets/export")
    ws = _xlsx(x.content).worksheets[0]
    meta, headers, rows, totals = _table(ws)
    assert len(rows) == 4 + BULK == 1104
    assert any(r_[1] == f"RFX Bulk {BULK:04d}" for r_ in rows)
    assert D(str(round(totals[headers.index("Sales (₹)")], 2))) == totals_of(gt_snapshots(q, world))["sales"]
    pdf = await get(client, H, "/reports/outlets/export", format="pdf")
    pages = _pdf_pages(pdf.content)
    assert len(pages) > 20
    joined = "\n".join(pages)
    assert f"RFX Bulk {BULK:04d}" in joined and "RFX Bulk 0001" in joined
    assert "TOTAL" in pages[-1] and f"Page {len(pages)} of {len(pages)}" in pages[-1]
    # header row repeats on every page
    assert all("Outlet Name" in pg for pg in pages)
    # outstanding report > 1000 rows too
    o = _table(_xlsx((await get(client, H, "/reports/outstanding/export")).content).worksheets[0])
    assert len(o[2]) == len(_out_rows(gt_snapshots(q, world))) > 1000


@pytest.mark.asyncio
async def test_pdf_currency_and_indian_grouping(client, H, world):
    _, _, sym = pdf_fonts()
    pdf = await get(client, H, "/reports/outstanding/export", format="pdf", month="2026-08")
    text = "\n".join(_pdf_pages(pdf.content))
    assert f"({sym})" in text  # money header, e.g. "Market OS (₹)" or "(Rs.)"
    assert f"{sym}" in text
    assert fmt_inr(1234567.5) == "12,34,567.50" and fmt_inr(999) == "999.00" and fmt_inr(100000) == "1,00,000.00"
    assert fmt_inr(-123456.789) == "-1,23,456.79" and fmt_inr(12345678901) == "12,34,56,78,901.00"
    assert fmt_inr(0) == "0.00" and fmt_inr(1000, 0) == "1,000"


@pytest.mark.asyncio
async def test_collections_overview_export_matches_json_with_period_columns(client, H, world):
    p = dict(start_date="2026-05-01", end_date="2026-05-31", search="RFXO")
    js = (await get(client, H, "/collections/overview", limit=200, **p)).json()
    x = await get(client, H, "/collections/overview/export", **p)
    assert "_filtered.xlsx" in x.headers["content-disposition"]
    ws = _xlsx(x.content).worksheets[0]
    meta, headers, rows, totals = _table(ws)
    assert "Invoiced in period (₹)" in headers and "Collected in period (₹)" in headers
    assert len(rows) == js["total_count"] == 4
    i = headers.index("Invoiced in period (₹)")
    assert round(totals[i], 2) == float(js["totals"]["invoiced_in_period"]) == 9900.0
    assert "as of today" in meta[1]
    # exports are NOT paginated even though the JSON endpoint is
    big = _table(_xlsx((await get(client, H, "/collections/overview/export")).content).worksheets[0])
    assert len(big[2]) == 4 + BULK


@pytest.mark.asyncio
async def test_monthly_periods_export_and_filename_uniqueness(client, H, world):
    x = await get(client, H, "/reports/monthly-periods/export")
    assert x.status_code == 200 and x.headers["content-disposition"].startswith('attachment; filename="Monthly_Snapshots_')
    names = set()
    for path in ("/reports/outstanding/export", "/reports/outlets/export", "/reports/visits-detailed/export",
                 "/reports/business-summary/export", "/collections/overview/export"):
        cd = (await get(client, H, path)).headers["content-disposition"]
        names.add(re.search(r'filename="([A-Za-z_]+)_', cd).group(1))
    assert len(names) == 5  # a distinct file name prefix per report
