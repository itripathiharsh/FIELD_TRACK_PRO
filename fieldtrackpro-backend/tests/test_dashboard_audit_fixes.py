"""Admin dashboard audit fixes (3.2): multi-select BI filters, ageing-bucket filter, outstanding report from live
Tally invoices, brand reconciliation, role access and Asia/Kolkata month boundaries.

Synthetic data only: every ledger, outlet, brand and employee below is invented per test run (unique tag).
Run against a throwaway database (scripts/local_audit_db.py), never against a database holding real data.
The live-invoice assertions need a database WITHOUT outlet financial snapshots (production has none); the
module skips them when snapshots exist.
"""
from __future__ import annotations

import io
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal as D

import openpyxl
import pytest
import pytest_asyncio
from sqlalchemy import func, select

from app.core.security import create_access_token, hash_password
from app.database import AsyncSessionLocal
from app.models.customer import Customer
from app.models.employee import Employee
from app.models.employee_customer_assignment import EmployeeCustomerAssignment
from app.models.outlet_financial_snapshot import OutletFinancialSnapshot
from app.models.user import Role, User
from app.models.visit import Visit, VisitStatus
from app.services.brand_reconciliation import candidate_brand
from app.services.report_filters import IST, as_list, month_ranges
from app.services.report_service import age_bucket_of, ageing_bucket_index
from tests.conftest import requires_db
from tests.test_tally_v2_sync import _post, _snapshot, _vch, env  # noqa: F401  (fixture reuse)


# ------------------------------------------------------------------------------------------------ unit
def test_multi_value_parsing():
    assert as_list(None) is None and as_list("ALL") is None and as_list([]) is None
    assert as_list("Oppo,Samsung") == ["Oppo", "Samsung"]
    assert as_list(["Oppo", "Samsung,Oppo", "ALL", " "]) == ["Oppo", "Samsung"]
    assert month_ranges("2026-11,2026-10") == [(date(2026, 10, 1), date(2026, 10, 31)),
                                               (date(2026, 11, 1), date(2026, 11, 30))]
    with pytest.raises(Exception):
        month_ranges("2026-10,2026-13")


def test_age_bucket_boundaries_match_the_labels():
    # 0-15, 16-30, 31-45, 46-60, 61-75, 76-90, >90 days
    for days, idx in ((0, 0), (15, 0), (16, 1), (30, 1), (31, 2), (45, 2), (46, 3), (60, 3), (61, 4), (75, 4),
                      (76, 5), (90, 5), (91, 6), (400, 6)):
        assert age_bucket_of(days) == idx, days
    assert ageing_bucket_index(">90") == 6 and ageing_bucket_index("<15") == 0 and ageing_bucket_index("ALL") is None
    with pytest.raises(Exception):
        ageing_bucket_index("90+")


def test_candidate_brand_is_only_a_suggestion_from_known_tokens():
    assert candidate_brand("Dharmendra (RR)") == "RR"
    assert candidate_brand("Sandeep Jha", "RR Sales") == "RR"
    assert candidate_brand("Raunak Singer") == "Singer"
    assert candidate_brand("ZEBRONIC(SANDEEP)") == "Zebronics"   # a spelling the agent does not recognise
    assert candidate_brand("Sandeep Jha", "Sales") is None
    assert candidate_brand("Sundry Debtors") is None


# ------------------------------------------------------------------------------------------------ fixtures
async def _no_snapshots() -> bool:
    async with AsyncSessionLocal() as s:
        return (await s.execute(select(func.count()).select_from(OutletFinancialSnapshot))).scalar_one() == 0


def _today() -> date:
    return datetime.now(IST).date()


async def _employee(tag: str, name: str, role: Role = Role.EMPLOYEE) -> tuple[uuid.UUID, uuid.UUID]:
    async with AsyncSessionLocal() as s:
        u = User(email=f"{name.lower()}_{tag}@fieldtrack.test", password_hash=hash_password("Passw0rd!"),
                 role=role, is_active=True)
        s.add(u)
        await s.flush()
        e = Employee(user_id=u.id, full_name=f"{name} {tag}", employee_code=f"T{tag[:4]}{name[:2].upper()}")
        s.add(e)
        await s.commit()
        return u.id, e.id


async def _assign(customer_guid: str, employee_id: uuid.UUID, by: uuid.UUID) -> uuid.UUID:
    async with AsyncSessionLocal() as s:
        cid = (await s.execute(select(Customer.id).where(Customer.tally_guid == customer_guid))).scalar_one()
        s.add(EmployeeCustomerAssignment(customer_id=cid, employee_id=employee_id, created_by=by, source="TALLY"))
        await s.commit()
        return cid


def _sale(e, key, ledger, brand, amount, d):
    line = {"ledger_name": ledger, "amount": f"-{amount}",
            "bill_allocations": [{"name": f"{key}-{e['tag']}", "bill_type": "New Ref", "amount": f"-{amount}"}]}
    if brand:
        line["brand"] = brand
    return _vch(e, key, "Sales", "Sales", [line], number=f"{key}-{e['tag']}", d=d.isoformat())


def _receipt(e, key, ledger, brand, amount, d, bill_key):
    line = {"ledger_name": ledger, "amount": str(amount),
            "bill_allocations": [{"name": f"{bill_key}-{e['tag']}", "bill_type": "Agst Ref", "amount": str(amount)}]}
    if brand:
        line["brand"] = brand
    return _vch(e, key, "BANK RECEIPT", "Receipt", [line],
                counter=[{"ledger_name": "UCO BANK OD", "ledger_class": "BANK", "amount": f"-{amount}"}],
                d=d.isoformat())


@pytest_asyncio.fixture
async def world(env):
    """3 outlets, 2 synthetic brands + one unbranded RR-group ledger, 2 FOS, invoices in Oct/Nov and >90 days."""
    if not await _no_snapshots():
        pytest.skip("this database has outlet snapshots; the live-invoice path cannot be exercised")
    t = env["tag"]
    bA, bB = f"BrandA{t}", f"BrandB{t}"
    leds = [
        {"guid": f"AUD-{t}-1", "name": f"Audit Outlet {t} 1", "is_debtor": True, "parent": f"Xavier {bA}", "brand": bA},
        {"guid": f"AUD-{t}-2", "name": f"Audit Outlet {t} 2", "is_debtor": True, "parent": f"Yusuf {bB}", "brand": bB},
        {"guid": f"AUD-{t}-3", "name": f"Audit Outlet {t} 3", "is_debtor": True, "parent": f"Zed{t} (RR)"},
    ]
    res = await _snapshot(env, [{**l, "opening_balance": "0", "closing_balance": "0"} for l in leds])
    assert res["failed_count"] == 0, res
    n1, n2, n3 = (l["name"] for l in leds)
    today = _today()
    old = today - timedelta(days=100)          # > 90 days (still inside the live financial year)
    oct_d, nov_d = date(2026, 10, 10), date(2026, 11, 3)
    vouchers = [
        _sale(env, "S1", n1, bA, "1000", oct_d),
        _sale(env, "S2", n1, bA, "500", nov_d),
        _sale(env, "S3", n2, bB, "2000", nov_d),
        _sale(env, "S4", n2, bB, "700", old),
        _sale(env, "S5", n3, None, "300", nov_d),
        _receipt(env, "R1", n1, bA, "400", nov_d, "S1"),      # settles part of S1 (bill-wise)
    ]
    res = await _post(env, "vouchers", {"vouchers": vouchers})
    assert res["failed_count"] == 0, res
    async with AsyncSessionLocal() as s:
        admin_uid = (await s.execute(
            select(User.id).where(User.email == f"admin_v2_{t}@fieldtrack.test"))).scalar_one()
    x_uid, x = await _employee(t, "Xavier")
    _, y = await _employee(t, "Yusuf")
    c1 = await _assign(f"AUD-{t}-1", x, admin_uid)
    c2 = await _assign(f"AUD-{t}-2", y, admin_uid)
    c3 = await _assign(f"AUD-{t}-3", x, admin_uid)
    return {**env, "bA": bA, "bB": bB, "x": str(x), "y": str(y), "x_uid": x_uid, "c": env["c"],
            "cust": {"c1": c1, "c2": c2, "c3": c3}, "today": today, "admin_uid": admin_uid}


async def _dash(w, **params):
    r = await w["c"].get("/api/v1/dashboard/summary", params=params, headers=w["admin_h"])
    assert r.status_code == 200, r.text
    return r.json()


def _k(body, key):
    return D(str(body["kpis"][key]))


# ------------------------------------------------------------------------------------------------ dashboard
@requires_db
@pytest.mark.asyncio
async def test_multi_brand_multi_fos_multi_month_filters_combine(world):
    w = world
    a = await _dash(w, brand=w["bA"])
    b = await _dash(w, brand=w["bB"])
    ab = await _dash(w, brand=[w["bA"], w["bB"]])              # repeated parameter
    ab2 = await _dash(w, brand=f"{w['bA']},{w['bB']}")          # comma separated
    assert a["data_source"] == "LIVE_INVOICES"
    assert _k(a, "total_sales") == D("1500.00") and _k(b, "total_sales") == D("2700.00")
    for body in (ab, ab2):
        assert _k(body, "total_sales") == _k(a, "total_sales") + _k(b, "total_sales")
        assert _k(body, "total_market_outstanding") == _k(a, "total_market_outstanding") + _k(b, "total_market_outstanding")
        assert {r["brand"] for r in body["brand_breakdown"]} == {w["bA"], w["bB"]}
    assert ab["applied_brands"] == [w["bA"], w["bB"]]
    # outstanding: A = 1000-400 + 500 = 1100; B = 2000 + 700 = 2700
    assert _k(a, "total_market_outstanding") == D("1100.00") and _k(b, "total_market_outstanding") == D("2700.00")
    # collections follow the brand allocation of the receipt
    assert _k(a, "total_collection") == D("400.00") and _k(b, "total_collection") == D("0.00")

    # FOS: X has outlets 1 and 3, Y has outlet 2; X+Y = both. Combined with the brands A+B (AND across filters).
    x = await _dash(w, employee_id=w["x"], brand=[w["bA"], w["bB"]])
    y = await _dash(w, employee_id=w["y"], brand=[w["bA"], w["bB"]])
    xy = await _dash(w, employee_id=[w["x"], w["y"]], brand=[w["bA"], w["bB"]])
    assert _k(x, "total_sales") == D("1500.00") and _k(y, "total_sales") == D("2700.00")
    assert _k(xy, "total_sales") == D("4200.00") and xy["applied_employee_ids"] == [w["x"], w["y"]]
    assert {r["dimension_name"] for r in xy["fos_breakdown"]} == {f"Xavier {w['tag']}", f"Yusuf {w['tag']}"}

    # Months: Oct (S1 1000) + Nov (S2 500 + S3 2000) = Oct,Nov
    oct_ = await _dash(w, month="2026-10", brand=[w["bA"], w["bB"]])
    nov = await _dash(w, month="2026-11", brand=[w["bA"], w["bB"]])
    both = await _dash(w, month=["2026-10", "2026-11"], brand=[w["bA"], w["bB"]])
    assert _k(oct_, "total_sales") == D("1000.00") and _k(nov, "total_sales") == D("2500.00")
    assert _k(both, "total_sales") == D("3500.00") and both["applied_periods"] == ["2026-10", "2026-11"]
    assert both["is_historical"] is True and both["period"] == "2026-10,2026-11"
    # Reset (no filters) = Current Live Data
    live = await _dash(w)
    assert live["period"] == "LIVE" and live["applied_brands"] == [] and live["ageing_bucket"] is None


@requires_db
@pytest.mark.asyncio
async def test_ageing_bucket_filters_every_widget_and_toggles_off(world):
    w = world
    scope = {"brand": [w["bA"], w["bB"]]}
    full = await _dash(w, **scope)
    assert D(str(full["ageing_distribution"][">90"])) == D("700.00")
    gt90 = await _dash(w, ageing_bucket=">90", **scope)
    assert gt90["ageing_bucket"] == ">90"
    assert _k(gt90, "total_market_outstanding") == D("700.00") and _k(gt90, "total_overdue_gt_90") == D("700.00")
    assert {k: D(str(v)) for k, v in gt90["ageing_distribution"].items() if D(str(v))} == {">90": D("700.00")}
    assert gt90["kpis"]["total_outlets"] == 1, "only the outlet holding money in the bucket"
    assert {r["brand"] for r in gt90["brand_breakdown"]} == {w["bB"]}
    assert _k(gt90, "total_collection") == D("0.00"), "collections follow the outlets of the bucket"
    lt15 = await _dash(w, ageing_bucket="<15", **scope)
    assert _k(lt15, "total_market_outstanding") + _k(gt90, "total_market_outstanding") <= _k(full, "total_market_outstanding")
    # toggled off again = the full figures
    again = await _dash(w, **scope)
    assert _k(again, "total_market_outstanding") == _k(full, "total_market_outstanding")
    r = await w["c"].get("/api/v1/dashboard/summary", params={"ageing_bucket": "90+"}, headers=w["admin_h"])
    assert r.status_code == 422


@requires_db
@pytest.mark.asyncio
async def test_month_boundary_is_asia_kolkata(world):
    w = world
    # 31 Oct 20:00 UTC = 1 Nov 01:30 IST -> November, not October.
    async with AsyncSessionLocal() as s:
        s.add(Visit(customer_id=w["cust"]["c1"], employee_id=uuid.UUID(w["x"]), created_by=w["admin_uid"],
                    scheduled_at=datetime(2026, 10, 31, 20, 0, tzinfo=timezone.utc), status=VisitStatus.PENDING))
        await s.commit()
    oct_ = await _dash(w, month="2026-10", employee_id=w["x"])
    nov = await _dash(w, month="2026-11", employee_id=w["x"])
    assert oct_["kpis"]["total_visits"] == 0
    assert nov["kpis"]["total_visits"] == 1


# ------------------------------------------------------------------------------------------------ outstanding
@requires_db
@pytest.mark.asyncio
async def test_outstanding_report_is_live_and_reconciles_with_dashboard(world):
    w = world
    for params in ({"brand": [w["bA"], w["bB"]]},
                   {"brand": [w["bA"], w["bB"]], "employee_id": w["y"]},
                   {"brand": [w["bA"], w["bB"]], "ageing_bucket": ">90"},
                   {"brand": [w["bA"], w["bB"]], "month": ["2026-10", "2026-11"]}):
        dash = await _dash(w, **params)
        rs = await w["c"].get("/api/v1/reports/outstanding/summary", params=params, headers=w["admin_h"])
        rows = await w["c"].get("/api/v1/reports/outstanding", params=params, headers=w["admin_h"])
        assert rs.status_code == 200 and rows.status_code == 200, (rs.text, rows.text)
        summ, rows = rs.json(), rows.json()
        assert summ["data_source"] == "LIVE_INVOICES"
        assert D(str(summ["market_outstanding"])) == _k(dash, "total_market_outstanding"), params
        assert D(str(summ["bucket_gt_90"])) == D(str(dash["ageing_distribution"][">90"])), params
        assert summ["accounts"] == len(rows)
        assert sum(D(str(r["market_outstanding"])) for r in rows) == D(str(summ["market_outstanding"]))
        assert summ["zones"] == len({r["zone_name"] for r in rows}) and summ["areas"] == len({r["area_name"] for r in rows})
    base = {"brand": [w["bA"], w["bB"]]}
    full = (await w["c"].get("/api/v1/reports/outstanding", params=base, headers=w["admin_h"])).json()
    assert len(full) == 2 and full[0]["bucket_gt_90"] != "0.00", "most overdue first"
    p1 = (await w["c"].get("/api/v1/reports/outstanding", params={**base, "skip": 0, "limit": 1}, headers=w["admin_h"])).json()
    p2 = (await w["c"].get("/api/v1/reports/outstanding", params={**base, "skip": 1, "limit": 1}, headers=w["admin_h"])).json()
    assert [r["customer_id"] for r in p1 + p2] == [r["customer_id"] for r in full], "pages are stable and complete"
    # search
    found = (await w["c"].get("/api/v1/reports/outstanding", params={**base, "query": f"Outlet {w['tag']} 2"},
                              headers=w["admin_h"])).json()
    assert len(found) == 1 and found[0]["brand"] == w["bB"]
    # exports: every filtered row, xlsx and pdf
    x = await w["c"].get("/api/v1/reports/outstanding/export", params={**base, "format": "xlsx"}, headers=w["admin_h"])
    assert x.status_code == 200 and "spreadsheetml" in x.headers["content-type"]
    ws = openpyxl.load_workbook(io.BytesIO(x.content)).active
    names = {str(c.value) for row in ws.iter_rows() for c in row if c.value}
    assert f"Audit Outlet {w['tag']} 1" in names and f"Audit Outlet {w['tag']} 2" in names
    p = await w["c"].get("/api/v1/reports/outstanding/export", params={**base, "format": "pdf"}, headers=w["admin_h"])
    assert p.status_code == 200 and p.content[:4] == b"%PDF"


# ------------------------------------------------------------------------------------------------ brands
@requires_db
@pytest.mark.asyncio
async def test_unattributed_brand_filter_options_and_reconciliation(world):
    w = world
    # Release 3.3: a brand first seen in Tally is created INACTIVE and not offered until an admin activates it.
    opts = (await w["c"].get("/api/v1/brands/filter-options", headers=w["admin_h"])).json()
    names = [o["name"] for o in opts]
    assert w["bA"] not in names and names[-1] == "Unattributed"
    for b in (w["bA"], w["bB"]):
        bid = next(x["id"] for x in (await w["c"].get("/api/v1/brands", params={"active_only": "false"}, headers=w["admin_h"])).json()
                   if x["name"] == b)
        assert (await w["c"].patch(f"/api/v1/brands/{bid}", json={"is_active": True}, headers=w["admin_h"])).status_code == 200
    opts = (await w["c"].get("/api/v1/brands/filter-options", headers=w["admin_h"])).json()
    names = [o["name"] for o in opts]
    assert w["bA"] in names and w["bB"] in names and names[-1] == "Unattributed"
    # Unattributed + FOS X = the RR-group outlet's unbranded invoice only
    un = await _dash(w, brand="Unattributed", employee_id=w["x"])
    assert _k(un, "total_sales") == D("300.00")
    assert {r["brand"] for r in un["brand_breakdown"]} == {"Unattributed"}
    rec = (await w["c"].get("/api/v1/brands/reconciliation", headers=w["admin_h"])).json()
    grp = next(g for g in rec["unattributed_groups"] if g["group"] == f"Zed{w['tag']} (RR)")
    assert grp["possible_brand"] == "RR" and grp["status"] == "POSSIBLE_TALLY_BRAND_NEEDS_CONFIRMATION"
    assert grp["invoices"] == 1 and D(str(grp["invoice_amount"])) == D("300.00")
    statuses = {r["status"] for r in rec["rows"]}
    assert {"UNATTRIBUTED_NO_BRAND_IN_TALLY", "POSSIBLE_TALLY_BRAND_NEEDS_CONFIRMATION"} <= statuses
    row_a = next(r for r in rec["rows"] if r["tally_brand"] == w["bA"])
    assert row_a["invoices"] == 2 and row_a["ledgers"] == 1


# ------------------------------------------------------------------------------------------------ roles
@requires_db
@pytest.mark.asyncio
async def test_employee_is_scoped_and_cannot_read_finance_reports(world):
    w = world
    h = {"Authorization": f"Bearer {create_access_token(subject=str(w['x_uid']), role=Role.EMPLOYEE.value)}"}
    r = await w["c"].get("/api/v1/dashboard/summary", params={"employee_id": w["y"]}, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["applied_employee_ids"] == [w["x"]], "an employee only ever sees their own scope"
    for path in ("/api/v1/reports/outstanding", "/api/v1/reports/outstanding/summary",
                 "/api/v1/brands/reconciliation", "/api/v1/brands/filter-options"):
        assert (await w["c"].get(path, headers=h)).status_code == 403, path
    assert (await w["c"].get("/api/v1/reports/outstanding/summary")).status_code in (401, 403)
    # SUPER_ADMIN is a superset of ADMIN
    async with AsyncSessionLocal() as s:
        su = User(email=f"super_{w['tag']}@fieldtrack.test", password_hash=hash_password("Passw0rd!"),
                  role=Role.SUPER_ADMIN, is_active=True)
        s.add(su)
        await s.commit()
        su_id = su.id
    sh = {"Authorization": f"Bearer {create_access_token(subject=str(su_id), role=Role.SUPER_ADMIN.value)}"}
    assert (await w["c"].get("/api/v1/reports/outstanding/summary", headers=sh)).status_code == 200
    assert (await w["c"].get("/api/v1/brands/reconciliation", headers=sh)).status_code == 200
