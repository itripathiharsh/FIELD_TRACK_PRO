"""Dashboard History (read-only past financial years), 19-Nov-2026.

History = a period before the reporting floor (1-Apr-2026): 'FY2025-26' (whole year) or one of its months.
It must show that period's Tally sales and collections, and must NOT:
  * change Current Live Data (live totals keep excluding history),
  * create a monthly reporting period / enter the close workflow,
  * move the reporting floor.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal as D

import pytest
from sqlalchemy import func, select

from app.database import AsyncSessionLocal
from app.models.monthly_reporting_period import MonthlyReportingPeriod
from app.services.report_filters import parse_month
from app.services.reporting_floor import reporting_floor
from tests.conftest import requires_db
from tests.test_tally_v2_sync import _post, _setup_debtors, _vch, env  # noqa: F401  (fixture reuse)


def test_parse_month_accepts_a_financial_year():
    assert parse_month("FY2025-26") == (date(2025, 4, 1), date(2026, 3, 31))
    assert parse_month("2025-07") == (date(2025, 7, 1), date(2025, 7, 31))
    assert parse_month("ALL") is None
    for bad in ("FY2025-27", "FY25-26", "2025-13"):
        with pytest.raises(Exception):
            parse_month(bad)


def _sale(e, key, ledger, brand, amount, d):
    return _vch(e, key, "Oppo", "Sales", [{"ledger_name": ledger, "amount": f"-{amount}", "brand": brand,
                "bill_allocations": [{"name": f"{key}-{e['tag']}", "bill_type": "New Ref", "amount": f"-{amount}"}]}],
                number=f"{key}-{e['tag']}", d=d)


def _receipt(e, key, ledger, brand, amount, d):
    return _vch(e, key, "BANK RECEIPT", "Receipt", [{"ledger_name": ledger, "amount": str(amount), "brand": brand}],
                counter=[{"ledger_name": "UCO BANK OD", "ledger_class": "BANK", "amount": f"-{amount}"}], d=d)


async def _summary(e, month, brand):
    r = await e["c"].get("/api/v1/dashboard/summary", params={"month": month, "brand": brand}, headers=e["admin_h"])
    assert r.status_code == 200, r.text
    return r.json()


@requires_db
@pytest.mark.asyncio
async def test_history_period_shows_past_year_and_stays_apart_from_live(env):
    t = env["tag"]
    brand = f"HistBrand{t}"
    (a,) = await _setup_debtors(env, 1)
    assert reporting_floor() == date(2026, 4, 1), "the reporting floor itself is not moved"
    async with AsyncSessionLocal() as s:
        periods_before = (await s.execute(select(func.count()).select_from(MonthlyReportingPeriod))).scalar_one()
        past_before = (await s.execute(select(func.count()).select_from(MonthlyReportingPeriod).where(
            MonthlyReportingPeriod.period_year == 2025))).scalar_one()
    res = await _post(env, "vouchers", {"vouchers": [
        _sale(env, "H1", a, brand, "1000", "2025-07-10"),      # FY 2025-26 (history)
        _sale(env, "H2", a, brand, "300", "2026-03-31"),       # last day of FY 2025-26
        _receipt(env, "HR", a, brand, "500", "2025-08-05"),    # FY 2025-26 receipt
        _sale(env, "L1", a, brand, "2000", "2026-06-15"),      # FY 2026-27 (live)
        _receipt(env, "LR", a, brand, "700", "2026-07-01"),    # FY 2026-27 receipt
    ]})
    assert res["failed_count"] == 0, res

    fy = await _summary(env, "FY2025-26", brand)
    assert fy["is_history"] is True and fy["period"] == "FY2025-26"
    assert D(str(fy["kpis"]["total_sales"])) == D("1300.00")
    assert D(str(fy["kpis"]["total_collection"])) == D("500.00")

    jul = await _summary(env, "2025-07", brand)
    assert jul["is_history"] is True and D(str(jul["kpis"]["total_sales"])) == D("1000.00")
    aug = await _summary(env, "2025-08", brand)
    assert D(str(aug["kpis"]["total_sales"])) == D("0.00") and D(str(aug["kpis"]["total_collection"])) == D("500.00")

    live = await _summary(env, "ALL", brand)
    assert live["is_history"] is False and live["period"] == "LIVE"
    # Live sales come from outlet snapshots when any exist (test database) or from live Tally invoices (production):
    # either way the FY 2025-26 sales (1,300) are never part of Current Live Data.
    assert D(str(live["kpis"]["total_sales"])) in (D("0.00"), D("2000.00")), "Current Live Data excludes history"
    assert D(str(live["kpis"]["total_collection"])) == D("700.00"), "live collections exclude history"

    jun = await _summary(env, "2026-06", brand)
    assert jun["is_history"] is False and D(str(jun["kpis"]["total_sales"])) == D("2000.00")

    async with AsyncSessionLocal() as s:
        periods_after = (await s.execute(select(func.count()).select_from(MonthlyReportingPeriod))).scalar_one()
        past = (await s.execute(select(func.count()).select_from(MonthlyReportingPeriod).where(
            MonthlyReportingPeriod.period_year == 2025))).scalar_one()
    assert periods_after == periods_before, "viewing history creates no reporting period"
    assert past == past_before, "no 2025 period is created (no close workflow for history)"

    r = await env["c"].get("/api/v1/dashboard/history-periods", headers=env["admin_h"])
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["reporting_floor"] == "2026-04-01"
    fy25 = next(p for p in body["periods"] if p["value"] == "FY2025-26")
    assert fy25["start"] == "2025-04-01" and fy25["end"] == "2026-03-31"
    months = {m["value"]: m for m in fy25["months"]}
    assert months["2025-07"]["invoices"] >= 1 and months["2025-08"]["payments"] >= 1 and "2026-03" in months
    assert list(months) == [f"2025-{m:02d}" for m in range(4, 13)] + ["2026-01", "2026-02", "2026-03"],         "all twelve months of the financial year, April to March"
    assert all(m["value"] < "2026-04" for m in fy25["months"]), "only months before the floor"
    assert all(p["value"] != "FY2026-27" for p in body["periods"]), "the live year is not history"


@requires_db
@pytest.mark.asyncio
async def test_history_periods_endpoint_is_admin_only(env):
    r = await env["c"].get("/api/v1/dashboard/history-periods")
    assert r.status_code in (401, 403)
