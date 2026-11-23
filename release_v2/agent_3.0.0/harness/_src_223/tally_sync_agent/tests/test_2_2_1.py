"""
Agent 2.2.1 regression tests: one or more per issue of release_v2/agent_2.2.1/RELEASE_PLAN_2.2.1.md and per item of
the 2.2.1 directive. Every test here is written to FAIL on the 2.2.0 code (proof: TEST_REPORT_2.2.1.md runs this file
against agent-source-2.2.0). New 2.2.1 symbols are imported inside the tests, so on 2.2.0 each test fails on its own.

Golden tests replay the client's real Tally answers recorded on 18-Nov-2026 by the two read-only probes:
  release_v2/agent_2.2.1/probe_results/lean_probe_20261118_074736_zip/probe        (lean vs wildcard, bills, GS)
  release_v2/agent_2.2.1/probe_results/day_scope_probe_20261118_120639_zip/...    (day vs FY scope, creditors)
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
import uuid
import xml.etree.ElementTree as ET
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from test_v2_agent import DEBTORS, GROUPS, LEDGERS, VTYPES, FakeSource, RecordingBackend, _engine, _masters, _vp
from test_regressions_2_2_0 import COMPANY, FY25, FY26, GUID, SC26, ScopedTally, _hist_engine, _live_engine_on
from tally_sync_agent.config import fiscal as F
from tally_sync_agent.config import settings as S
from tally_sync_agent.core.checkpoint_manager import CheckpointManager
from tally_sync_agent.core.tally_client import TallyClient, TallyConnectionError
from tally_sync_agent.engine import sync_engine_v2 as E
from tally_sync_agent.extractors import tally_xml as tx
from tally_sync_agent.extractors import v2_extractors as X

ROOT = Path(__file__).resolve().parents[2]
PROBE1 = Path(os.environ.get("PROBE1_DIR", ROOT / "release_v2/agent_2.2.1/probe_results/lean_probe_20261118_074736_zip/probe"))
PROBE2 = Path(os.environ.get("PROBE2_DIR", ROOT / "release_v2/agent_2.2.1/probe_results/day_scope_probe_20261118_120639_zip/"
                                                  "day_scope_probe_20261118_120639"))
needs_probes = pytest.mark.skipif(not (PROBE1.exists() and PROBE2.exists()), reason="18-Nov probe recordings not available")
TC = TallyClient()


def _root(folder: Path, name: str) -> ET.Element:
    return ET.fromstring(TC._clean_xml((folder / name).read_text(encoding="utf-8-sig")))


def _req(folder: Path, name: str) -> str:
    return (folder / name).read_text(encoding="utf-8-sig").strip()


def _probe_masters(folder: Path) -> X.Masters:
    return X.parse_masters(_root(folder, "m_groups.xml"), _root(folder, "m_ledgers.xml"),
                           _root(folder, "m_debtors_fy2026-27.xml"), _root(folder, "m_vtypes.xml"))


def _approve(eng):
    (eng.data_dir / f"approve_first_load_{eng.fy.label}.json").write_text("{}", encoding="utf-8")


class CompanyTally(ScopedTally):
    def execute_tdl(self, xml):
        if "<ID>Bills Receivable</ID>" in xml:  # a bill-wise debtor with a receivable has an open bill
            self.requests.append(xml)
            return ET.fromstring("<ENVELOPE><BILLFIXED><BILLDATE>1-Apr-26</BILLDATE><BILLREF>1</BILLREF><BILLPARTY>Shop A"
                                 "</BILLPARTY></BILLFIXED><BILLCL>-1500.00</BILLCL><BILLDUE>1-May-26</BILLDUE></ENVELOPE>")
        return super().execute_tdl(xml)

    def get_company_info(self):
        self.requests.append("COMPANY")
        return {"name": COMPANY, "guid": GUID, "companies": [COMPANY], "books_from": "20240401"}


class NoTally:
    """A Tally client that must never be called."""
    def __init__(self):
        self.calls = 0

    def get_company_info(self):
        self.calls += 1
        return {"name": COMPANY, "guid": GUID, "companies": [COMPANY], "books_from": "20240401"}

    def execute_tdl(self, xml):
        self.calls += 1
        raise AssertionError("no Tally request expected")


# ===================================================================== item 1-5 / B10: checkpoint safety

def test_B10_the_2_1_0_checkpoint_zero_request_cannot_be_built():
    """2.1.0/2.2.0 dropped the AlterID filter when the checkpoint was 0 and sent an unfiltered request."""
    for bad in (0, -1, None, "5", True, 5.0):
        with pytest.raises(ValueError):
            if bad is None:
                tx.voucher_request(tx.VOUCHER_FULL_FETCH, scope=SC26)               # no filter at all
            else:
                tx.voucher_request(tx.VOUCHER_FULL_FETCH, min_alter_id=bad, scope=SC26)
    with pytest.raises(tx.UnfilteredRequestRefused):
        tx.voucher_request(tx.VOUCHER_FULL_FETCH, min_alter_id=0, date_from=FY26.start, date_to=date(2026, 4, 30), scope=SC26)


@pytest.mark.parametrize("cp", [dict(alter_id=0, records_count=0), None])
def test_item1_zero_or_missing_checkpoint_stops_and_sends_nothing(tmp_path, cp):
    """Production's real state (AlterID 0, 0 records, completed) and a never-loaded FY: CHECKPOINT_ZERO, no request."""
    tally = NoTally()
    src = FakeSource({date(2026, 4, 1): [_vp("A", 10)]})
    eng = _engine(tmp_path, src, RecordingBackend())
    eng.tally = tally
    if cp:
        eng.checkpoints.update_checkpoint(E.CP_VOUCHERS, **cp)
    before = eng.checkpoints.get_checkpoint(E.CP_VOUCHERS)
    r = eng.run_sync()
    assert r["status"] == "CHECKPOINT_ZERO"
    assert src.calls == [] and not getattr(src, "incr_calls", []), "no voucher request at all"
    assert eng.checkpoints.get_checkpoint(E.CP_VOUCHERS) == before, "checkpoint not modified"


@pytest.mark.parametrize("raw,records", [(-5, 10), ("abc", 10), (0, 22989)])
def test_item1_invalid_checkpoint_stops_and_is_not_modified(tmp_path, raw, records):
    src = FakeSource({date(2026, 4, 1): [_vp("A", 10)]})
    eng = _engine(tmp_path, src, RecordingBackend())
    eng.tally = NoTally()
    eng.checkpoints.update_checkpoint(E.CP_VOUCHERS, alter_id=1, records_count=records)
    with eng.checkpoints._connection() as c:  # simulate a corrupt / foreign value in the store
        c.execute("UPDATE checkpoints SET last_alter_id = ? WHERE entity_type = ?", (raw, E.CP_VOUCHERS))
        c.commit()
    before = eng.checkpoints.get_checkpoint(E.CP_VOUCHERS)
    r = eng.run_sync()
    assert r["status"] == "CHECKPOINT_INVALID", r
    assert src.calls == [] and eng.checkpoints.get_checkpoint(E.CP_VOUCHERS) == before
    with pytest.raises(E.CheckpointInvalid):
        eng.incremental_vouchers(GUID)


def test_item1_incremental_at_checkpoint_zero_raises_before_any_request(tmp_path):
    tally = CompanyTally()
    eng, src = _live_engine_on(tmp_path, tally)
    eng.masters = _masters()
    eng.checkpoints.update_checkpoint(E.CP_VOUCHERS, alter_id=0, records_count=0)
    with pytest.raises(E.CheckpointZero):
        eng.incremental_vouchers(GUID)
    assert not [r for r in tally.requests if "<TYPE>Voucher</TYPE>" in r]


def test_item1_first_load_runs_only_after_explicit_approval_and_never_fy_wide(tmp_path):
    tally = CompanyTally()
    be = RecordingBackend()
    eng, src = _live_engine_on(tmp_path, tally, be, today=date(2026, 4, 3))
    eng.tally = tally
    eng.checkpoints.update_checkpoint(E.CP_VOUCHERS, alter_id=0, records_count=0)
    assert eng.run_sync()["status"] == "CHECKPOINT_ZERO"
    assert not [r for r in tally.requests if "<TYPE>Voucher</TYPE>" in r]
    _approve(eng)
    eng.run_sync()
    vreq = [r for r in tally.requests if "<TYPE>Voucher</TYPE>" in r]
    assert vreq, "the approved first load reads vouchers"
    assert not [r for r in vreq if '<SVFROMDATE TYPE="Date">1-Apr-2026</SVFROMDATE><SVTODATE TYPE="Date">31-Mar-2027' in r]


def test_item2_live_fy_keeps_the_production_state_names():
    ctx = F.build_contexts("2024-25,2025-26,2026-27", "2026-04-01", "", date(2026, 11, 18))
    live = ctx["live"]
    assert (live.cp_vouchers, live.cp_manifest, live.cp_balances, live.cp_debtors, live.state_file) == \
        ("vouchers_v2", "manifest_v2", "balances_v2", "debtors_v2", "initial_load_v2.json")


def test_item3_live_checkpoint_zero_never_touches_another_fy(tmp_path):
    db = tmp_path / "s.db"
    hist = _hist_engine(tmp_path, FakeSource({}), RecordingBackend(), db=db)
    hist.checkpoints.update_checkpoint("vouchers_v2@2025-26", alter_id=777, records_count=5)
    live = _engine(tmp_path, FakeSource({}), RecordingBackend())
    live.checkpoints = CheckpointManager(db)
    live.tally = NoTally()
    live.checkpoints.update_checkpoint(E.CP_VOUCHERS, alter_id=0, records_count=0)
    assert live.run_sync()["status"] == "CHECKPOINT_ZERO"
    assert hist.checkpoints.get_checkpoint("vouchers_v2@2025-26")["last_alter_id"] == 777
    assert hist.checkpoint_status() == "OK" and live.checkpoint_status() == "EMPTY_COMPLETION"


def test_item4_incremental_with_nothing_new_does_not_rewrite_the_checkpoint(tmp_path):
    src = FakeSource({date(2026, 4, 1): [_vp("A", 90)]})
    eng = _engine(tmp_path, src, RecordingBackend())
    eng.masters = _masters()
    eng.checkpoints.update_checkpoint(E.CP_VOUCHERS, alter_id=100, records_count=7)
    before = eng.checkpoints.get_checkpoint(E.CP_VOUCHERS)
    r = eng.incremental_vouchers(GUID)
    assert r["checkpoint"] == 100 and eng.checkpoints.get_checkpoint(E.CP_VOUCHERS) == before


def test_item4_rejected_bills_never_upload_and_report_the_status(tmp_path):
    class Src(FakeSource):
        def bills(self, m, as_of):
            raise E.BillsDateInvalid("Bills Receivable as of 2026-04-03 contains 1 bill(s) dated after that date")
    be = RecordingBackend()
    src = Src({date(2026, 4, 1): [_vp("A", 121241)]})
    eng = _engine(tmp_path, src, be)
    eng.tally = NoTally()
    eng.checkpoints.update_checkpoint(E.CP_VOUCHERS, alter_id=121240, records_count=1)
    r = eng.run_sync()
    assert r["status"] == "BILLS_DATE_INVALID" and not [c for c in be.calls if c[0] == "bills"]


# ===================================================================== B1 / B11 / B4: request form

def test_B1_the_lean_fetch_is_what_the_agent_sends():
    r = tx.voucher_request(tx.VOUCHER_FULL_FETCH, day=date(2026, 9, 29), scope=SC26)
    assert "AllLedgerEntries.LedgerName, AllLedgerEntries.Amount, AllLedgerEntries.BillAllocations.*, " \
           "AllLedgerEntries.BankAllocations.*" in r
    assert "AllLedgerEntries.*," not in r, "the wildcard fetch (36.7 KB per voucher) is not sent"


def test_B11_voucher_requests_are_scoped_to_their_day_or_month_never_the_fy():
    d = tx.voucher_request(tx.VOUCHER_FULL_FETCH, day=date(2026, 9, 29), scope=SC26)
    m = tx.voucher_request(tx.MANIFEST_FETCH, date_from=date(2026, 10, 1), date_to=date(2026, 10, 31), scope=SC26)
    i = tx.voucher_request(tx.MANIFEST_FETCH, date_from=date(2026, 10, 1), date_to=date(2026, 10, 31), min_alter_id=121558, scope=SC26)
    assert '<SVFROMDATE TYPE="Date">29-Sep-2026</SVFROMDATE><SVTODATE TYPE="Date">29-Sep-2026</SVTODATE>' in d
    for r in (m, i):
        assert '<SVFROMDATE TYPE="Date">1-Oct-2026</SVFROMDATE><SVTODATE TYPE="Date">31-Oct-2026</SVTODATE>' in r
    assert "$$Number:$AlterId &gt; 121558" in i and '$Date &gt;= $$Date:"1-Oct-2026"' in i


def test_B4_incremental_reads_month_headers_then_only_the_changed_days(tmp_path):
    days = {date(2026, 4, 1): [_vp("A", 101)], date(2026, 4, 2): [_vp("B", 50, "2026-04-02")],
            date(2026, 5, 20): [_vp("C", 130, "2026-05-20")]}
    src = FakeSource(days)
    eng = _engine(tmp_path, src, RecordingBackend(), today=date(2026, 6, 10))
    eng.masters = _masters()
    eng.checkpoints.update_checkpoint(E.CP_VOUCHERS, alter_id=100, records_count=1)
    r = eng.incremental_vouchers(GUID)
    heads = [c for c in src.incr_calls if c[0] == "headers"]
    dayreq = [c[1] for c in src.incr_calls if c[0] == "day"]
    assert [(c[1], c[2]) for c in heads] == [(date(2026, 4, 1), date(2026, 4, 30)), (date(2026, 5, 1), date(2026, 5, 31)),
                                             (date(2026, 6, 1), date(2026, 6, 10))]
    assert dayreq == [date(2026, 4, 1), date(2026, 5, 20)], "only the dates with changed vouchers"
    assert r["checkpoint"] == 130 and r["validated"] == 2


def test_B4_source_incremental_requests_carry_month_or_day_scope_and_alter_filter(tmp_path):
    tally = ScopedTally()
    eng, src = _live_engine_on(tmp_path, tally)
    eng.apply_scope()
    src.changed_headers(date(2026, 11, 1), date(2026, 11, 18), 121240)
    src.changed_vouchers_on(_masters(), date(2026, 11, 13), 121240)
    h, v = tally.requests[-2:]
    assert '<SVFROMDATE TYPE="Date">1-Nov-2026</SVFROMDATE><SVTODATE TYPE="Date">18-Nov-2026</SVTODATE>' in h
    assert '<SVFROMDATE TYPE="Date">13-Nov-2026</SVFROMDATE><SVTODATE TYPE="Date">13-Nov-2026</SVTODATE>' in v
    assert all("$$Number:$AlterId &gt; 121240" in r for r in (h, v))


def test_R14_a_voucher_returned_outside_the_fy_is_still_dropped(tmp_path):
    class Odd(FakeSource):  # a misbehaving answer: the day request also returns a voucher of another FY
        def changed_vouchers_on(self, m, day, min_alter):
            return [_vp("IN", 101, "2026-04-01"), _vp("OUT", 102, "2026-03-31")], []
    src = Odd({date(2026, 4, 1): [_vp("IN", 101, "2026-04-01")]})
    be = RecordingBackend()
    eng = _engine(tmp_path, src, be)
    eng.masters = _masters()
    eng.checkpoints.update_checkpoint(E.CP_VOUCHERS, alter_id=100, records_count=1)
    r = eng.incremental_vouchers(GUID)
    assert r["outside_fy"] == 1 and not [c for c in be.calls if c[0] == "vouchers" and "OUT" in c[1]]


# ===================================================================== A3 / A4 / A5: dates

def test_A3_bills_reports_use_the_typed_form_and_require_the_books_start():
    b = tx.bills_receivable_request(date(2025, 3, 31), COMPANY, date(2024, 4, 1))
    assert '<SVFROMDATE TYPE="Date">1-Apr-2024</SVFROMDATE><SVTODATE TYPE="Date">31-Mar-2025</SVTODATE>' in b
    assert "<SVTODATE>20250331</SVTODATE>" not in b
    with pytest.raises(ValueError):
        tx.bills_payable_request(date(2025, 3, 31), COMPANY)


def test_item15_a_bill_dated_after_the_as_of_date_rejects_the_report():
    ok = [{"bill_date": "2026-03-31", "bill_name": "1"}]
    late = ok + [{"bill_date": "2026-04-01", "bill_name": "SJ/1"}]
    E.check_bill_dates(ok, date(2026, 3, 31), "Bills Receivable")
    with pytest.raises(E.BillsDateInvalid):
        E.check_bill_dates(late, date(2026, 3, 31), "Bills Receivable")


def test_item15_source_bills_rejects_a_wrongly_dated_answer(tmp_path):
    class T:
        def execute_tdl(self, xml):
            return ET.fromstring("<ENVELOPE><BILLFIXED><BILLDATE>1-Apr-26</BILLDATE><BILLREF>X</BILLREF><BILLPARTY>Shop A"
                                 "</BILLPARTY></BILLFIXED><BILLCL>-5.00</BILLCL></ENVELOPE>")
    src = E.TallyV2Source(T(), 0, books_from=date(2024, 4, 1))
    src.set_scope(SC26)
    with pytest.raises(E.BillsDateInvalid):
        src.bills(_masters(), date(2026, 3, 31))


def test_A5_balances_and_group_summary_use_the_same_window_end_date(tmp_path):
    tally = ScopedTally()
    eng, src = _live_engine_on(tmp_path, tally, today=date(2026, 11, 18))
    eng.ledger_snapshot(GUID)
    debt = [r for r in tally.requests if "FtpDebtors" in r][-1]
    gs = [r for r in tally.requests if "<ID>Group Summary</ID>" in r]
    assert '<SVTODATE TYPE="Date">18-Nov-2026</SVTODATE>' in debt, "debtors read to the window end, not 31-Mar-2027"
    assert any('<SVTODATE TYPE="Date">18-Nov-2026</SVTODATE>' in g for g in gs)


def test_item23_bills_sanity_refuses_implausible_answers_and_reports_the_difference():
    with pytest.raises(E.BillsSanityFailed):
        E.bills_sanity([], Decimal("-100"), 3)
    dup = [{"ledger_name": "A", "bill_name": "1", "bill_date": "2026-04-01", "pending_amount": "-5"}] * 2
    with pytest.raises(E.BillsSanityFailed):
        E.bills_sanity(dup, Decimal("-10"), 1)
    r = E.bills_sanity(dup[:1], Decimal("-8"), 1)
    assert r["difference_bills_minus_balances"] == "3"
    assert E.bills_sanity([], Decimal("0"), 0)["bills"] == 0, "no bill-wise receivable: an empty answer is plausible"


# ===================================================================== item 19: opening + movements = closing

def test_item19_ledger_movements_reconcile_debtors_and_creditors():
    from tally_sync_agent.engine import fy_validation as V
    xml = """<ENVELOPE><VOUCHER><DATE>20260401</DATE><GUID>v1</GUID><VOUCHERTYPENAME>Sales</VOUCHERTYPENAME>
      <ALLLEDGERENTRIES.LIST><LEDGERNAME>Shop A</LEDGERNAME><AMOUNT>-500.00</AMOUNT></ALLLEDGERENTRIES.LIST>
      <ALLLEDGERENTRIES.LIST><LEDGERNAME>Supplier X</LEDGERNAME><AMOUNT>200.00</AMOUNT></ALLLEDGERENTRIES.LIST></VOUCHER>
      <VOUCHER><DATE>20260401</DATE><GUID>v2</GUID><VOUCHERTYPENAME>Sales</VOUCHERTYPENAME><ISCANCELLED>Yes</ISCANCELLED>
      <ALLLEDGERENTRIES.LIST><LEDGERNAME>Shop A</LEDGERNAME><AMOUNT>-999.00</AMOUNT></ALLLEDGERENTRIES.LIST></VOUCHER></ENVELOPE>"""
    m = _masters()
    mv = V.ledger_movements(ET.fromstring(xml), m, {"shop a", "supplier x"})
    assert mv == {"shop a": Decimal("-500.00"), "supplier x": Decimal("200.00")}, "cancelled voucher ignored"
    bal = {"shop a": {"name": "Shop A", "opening": Decimal("-1000"), "closing": Decimal("-1500")},
           "supplier x": {"name": "Supplier X", "opening": Decimal("100"), "closing": Decimal("250")}}
    bad = V._reconcile(bal, mv)
    assert [b["ledger"] for b in bad] == ["Supplier X"] and Decimal(bad[0]["difference"]) == Decimal("-50")


def test_item22_bills_vs_balances_is_reported_per_ledger_never_suppressed():
    from tally_sync_agent.engine import fy_validation as V
    bal = {"a": {"name": "A", "closing": Decimal("-100")}, "b": {"name": "B", "closing": Decimal("50")}}
    bills = [{"ledger_name": "A", "pending_amount": "-100"}]
    r = V.bills_vs_balances(bills, bal, {"b": Decimal("50")}, {})
    assert r["ledgers_with_difference"] == 1 and r["ledgers"][0]["ledger"] == "B"
    assert r["ledgers"][0]["on_account_allocations_in_fy"] == "50" and r["sum_difference"] == "-50"


# ===================================================================== items 10-12: pacing, breaker, lock

def _guard(tmp_path, **kw):
    from tally_sync_agent.core.tally_guard import TallyGuard
    kw.setdefault("mutex_name", f"Local\\FtTest_{uuid.uuid4().hex}")
    return TallyGuard(tmp_path, **kw)


def test_item10_duty_cycle_pause_after_each_request(tmp_path):
    slept = []
    g = _guard(tmp_path, duty_factor=1.0, min_pause=2.0, sleep=slept.append)
    g.request("a", lambda: time.sleep(0.05) or "x")
    g.request("b", lambda: "y")
    assert slept[0] >= 2.0 and slept[1] == 2.0
    g2 = _guard(tmp_path / "x", duty_factor=1.0, min_pause=0.0, sleep=slept.append)
    (tmp_path / "x").mkdir(exist_ok=True)
    g2.request("c", lambda: time.sleep(0.3))
    assert slept[-1] >= 0.25, "pause = duty factor x request duration (Windows timer resolution ~16 ms)"


def test_item10_timeout_opens_the_breaker_and_no_request_piles_up(tmp_path):
    from tally_sync_agent.core.tally_guard import TallyCoolingDown
    now = [1000.0]
    calls = []
    g = _guard(tmp_path, sleep=lambda s: None, clock=lambda: now[0], base_cooldown=180, max_cooldown=1800)

    def timeout():
        calls.append(1)
        raise TallyConnectionError("timed out")
    with pytest.raises(TallyConnectionError):
        g.request("day", timeout, connection_errors=(TallyConnectionError,))
    for _ in range(5):  # the next cycles: nothing is sent while cooling down
        with pytest.raises(TallyCoolingDown):
            g.request("day", lambda: calls.append(1), connection_errors=(TallyConnectionError,))
    assert len(calls) == 1
    now[0] += 181
    t = [0.0]
    g.request("probe", lambda: calls.append(1), connection_errors=(TallyConnectionError,))  # fast probe closes it
    assert not g.breaker.is_open() and g.breaker.state.consecutive_failures == 0


def test_item12_cooldown_doubles_survives_restart_and_a_slow_probe_reopens_it(tmp_path):
    now = [0.0]
    g = _guard(tmp_path, sleep=lambda s: None, clock=lambda: now[0], base_cooldown=180, max_cooldown=600)
    for i in range(4):
        with pytest.raises(TallyConnectionError):
            g.request("x", lambda: (_ for _ in ()).throw(TallyConnectionError("refused")),
                      connection_errors=(TallyConnectionError,))
        assert abs(g.breaker.remaining() - min(600, 180 * 2 ** i)) < 1e-6
        now[0] += g.breaker.remaining() + 1
    from tally_sync_agent.core.tally_guard import TallyGuard
    g2 = TallyGuard(tmp_path, sleep=lambda s: None, clock=lambda: now[0], mutex_name=f"Local\\FtTest_{uuid.uuid4().hex}")
    assert g2.breaker.state.consecutive_failures == 4, "persisted across a restart"
    g2.PROBE_MAX_SECONDS = 0.01
    g2.request("probe", lambda: time.sleep(0.05))  # answered, but slowly: Tally is still busy
    assert g2.breaker.is_open()


def test_item12_engine_in_cooldown_reports_and_does_not_touch_tally(tmp_path):
    g = _guard(tmp_path, sleep=lambda s: None)
    g.breaker.trip("test")
    tally = NoTally()
    src = E.TallyV2Source(tally, 0, guard=g)
    eng = _engine(tmp_path, src, RecordingBackend())
    eng.tally = tally
    r = eng.run_sync()
    assert r["status"] == "TALLY_COOLDOWN" and tally.calls == 0


def test_item11_requests_from_two_threads_never_overlap(tmp_path):
    name = f"Local\\FtTest_{uuid.uuid4().hex}"
    from tally_sync_agent.core.tally_guard import TallyGuard
    g1 = TallyGuard(tmp_path / "a", sleep=lambda s: None, mutex_name=name)
    g2 = TallyGuard(tmp_path / "b", sleep=lambda s: None, mutex_name=name)
    inside, peak, lock = [0], [0], threading.Lock()

    def work():
        with lock:
            inside[0] += 1
            peak[0] = max(peak[0], inside[0])
        time.sleep(0.02)
        with lock:
            inside[0] -= 1

    def run(g):
        for _ in range(10):
            g.request("w", work)
    (tmp_path / "a").mkdir(); (tmp_path / "b").mkdir()
    ts = [threading.Thread(target=run, args=(g,)) for g in (g1, g2)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert peak[0] == 1


@pytest.mark.skipif(sys.platform != "win32", reason="named mutex across processes is Windows-specific")
def test_item11_another_process_holding_the_tally_lock_blocks_our_request(tmp_path):
    from tally_sync_agent.core.tally_guard import TallyBusy
    name = f"Local\\FtTest_{uuid.uuid4().hex}"
    code = ("import ctypes,sys,time;k=ctypes.WinDLL('kernel32');h=k.CreateMutexW(None,True,sys.argv[1]);"
            "print('held',flush=True);time.sleep(4)")
    p = subprocess.Popen([sys.executable, "-c", code, name], stdout=subprocess.PIPE, text=True)
    assert p.stdout.readline().strip() == "held"
    g = _guard(tmp_path, sleep=lambda s: None, lock_wait=0.5, mutex_name=name)
    called = []
    with pytest.raises(TallyBusy):
        g.request("x", lambda: called.append(1))
    assert not called
    p.wait()
    g.request("x", lambda: called.append(1))  # released when the other process exits
    assert called == [1]


@pytest.mark.skipif(sys.platform != "win32", reason="named mutex across processes is Windows-specific")
def test_item11_a_second_validate_fy_refuses_to_start(tmp_path):
    from tally_sync_agent.core.tally_guard import ExclusiveJobLock
    name = f"Local\\FtTestJob_{uuid.uuid4().hex}"
    code = ("import ctypes,sys,time;k=ctypes.WinDLL('kernel32');h=k.CreateMutexW(None,True,sys.argv[1]);"
            "print('held',flush=True);time.sleep(3)")
    p = subprocess.Popen([sys.executable, "-c", code, name], stdout=subprocess.PIPE, text=True)
    assert p.stdout.readline().strip() == "held"
    j = ExclusiveJobLock(name)
    assert j.acquire() is False
    p.wait()
    assert j.acquire() is True
    j.release()


def test_item11_manual_sync_refuses_while_the_daemon_runs(tmp_path, monkeypatch, capsys):
    from tally_sync_agent import main
    monkeypatch.setattr(main, "_instance_or_exit", lambda: {"mutex": "x", "instance": "default"})

    class Held:
        def __init__(self, name): pass
        def acquire(self): return False
        def release(self): pass
    monkeypatch.setattr(main, "SingleInstanceLock", Held)
    ran = []
    monkeypatch.setattr(main, "MultiFySync", lambda *a, **k: ran.append(1))
    with pytest.raises(SystemExit):
        main.cmd_sync(type("A", (), {"initial": False})())
    assert not ran and "would overlap" in capsys.readouterr().out


# ===================================================================== approve-first-load

def test_approve_first_load_writes_only_its_marker(tmp_path, monkeypatch, capsys):
    from tally_sync_agent import main
    monkeypatch.setattr(main, "DATA_DIR", tmp_path)
    db = tmp_path / "s.db"
    cm = CheckpointManager(db)
    cm.update_checkpoint(E.CP_VOUCHERS, alter_id=0, records_count=0)
    before = cm.get_checkpoint(E.CP_VOUCHERS)
    orig = E.SyncEngineV2

    def eng(fy):
        return orig(tally_client=object(), backend_client=RecordingBackend(), checkpoint_manager=CheckpointManager(db),
                    data_dir=tmp_path, fy=fy, source=FakeSource({}))
    monkeypatch.setattr(main, "SyncEngineV2", eng)
    monkeypatch.setattr(S.settings, "financial_years", "2024-25,2025-26,2026-27")
    monkeypatch.setattr(S.settings, "sync_from_date", "2026-04-01")
    monkeypatch.setattr(S.settings, "history_upload", "")
    with pytest.raises(SystemExit):
        main.cmd_approve_first_load(type("A", (), {"fy": "2025-26"})())  # not the live FY
    main.cmd_approve_first_load(type("A", (), {"fy": "2026-27"})())
    rec = json.loads((tmp_path / "approve_first_load_2026-27.json").read_text(encoding="utf-8"))
    assert rec["checkpoint_status"] == "EMPTY_COMPLETION" and CheckpointManager(db).get_checkpoint(E.CP_VOUCHERS) == before
    CheckpointManager(db).update_checkpoint(E.CP_VOUCHERS, alter_id=5000, records_count=9)
    (tmp_path / "approve_first_load_2026-27.json").unlink()
    with pytest.raises(SystemExit):  # a valid checkpoint needs no first load
        main.cmd_approve_first_load(type("A", (), {"fy": "2026-27"})())
    assert not (tmp_path / "approve_first_load_2026-27.json").exists()


# ===================================================================== items 26-28: manifest floor, history

def test_item26_manifest_with_more_than_half_deleted_is_refused(tmp_path):
    be = RecordingBackend()
    eng = _engine(tmp_path, FakeSource({}), be)
    eng.checkpoints.update_checkpoint(eng.fy.cp_manifest_count, alter_id=1000)
    with pytest.raises(E.ManifestRejected):
        eng.upload_manifest(GUID, [f"g{i}" for i in range(499)])
    eng.upload_manifest(GUID, [f"g{i}" for i in range(500)])


def test_item27_historical_upload_is_disabled_by_default():
    assert S.SyncAgentSettings().history_upload == ""
    ctx = F.build_contexts("2024-25,2025-26,2026-27", "2026-04-01", "", date(2026, 11, 18))
    assert ctx["historical"] == []


def test_item28_history_needs_the_backend_history_safe_declaration(tmp_path, monkeypatch):
    from tally_sync_agent.engine import multi_fy as MF
    monkeypatch.setattr(S.settings, "history_upload", "2025-26")
    monkeypatch.setattr(MF.settings, "history_upload", "2025-26")

    class Be(RecordingBackend):
        def get_capabilities(self):
            return {"backend_release": "2.1.0"}  # no history_safe
    mf = MF.MultiFySync(tally_client=object(), backend_client=Be(), data_dir=tmp_path, today=lambda: date(2026, 11, 18),
                        source_factory=lambda: FakeSource({}))
    mf.live.run_sync = lambda: {"status": "COMPLETED"}
    called = []
    for h in mf.history:
        h.historical_step = lambda g: called.append(1)
    r = mf.run_cycle()
    assert "blocked" in r["history"] and not called


# ===================================================================== golden tests on the client's real answers

@needs_probes
@pytest.mark.parametrize("day", ["20260309", "20260325", "20260427", "20260929", "20261012"])
def test_G9_lean_fetch_parses_identically_to_the_wildcard_fetch(day):
    m = _probe_masters(PROBE1)
    cur, cb = X.parse_vouchers(_root(PROBE1, f"{day}_current.xml"), m)
    lean, lb = X.parse_vouchers(_root(PROBE1, f"{day}_lean.xml"), m)
    assert {v["guid"]: v for v in cur} == {v["guid"]: v for v in lean} and cb == lb == []


@needs_probes
@pytest.mark.parametrize("day", ["20240522", "20260309", "20260325", "20260427", "20260929", "20261012"])
def test_G10_day_scope_returns_exactly_the_fy_scope_vouchers(day):
    m = _probe_masters(PROBE2)
    fy, _ = X.parse_vouchers(_root(PROBE2, f"{day}_fyscope_lean.xml"), m)
    dl, _ = X.parse_vouchers(_root(PROBE2, f"{day}_dayscope_lean.xml"), m)
    assert fy and {v["guid"]: v for v in fy} == {v["guid"]: v for v in dl}


@needs_probes
def test_G11_all_bill_types_and_bank_details_survive_the_lean_parse():
    m = _probe_masters(PROBE1)
    types, banks = set(), []
    for day in ("20260309", "20260325", "20260929", "20261012"):
        vs, _ = X.parse_vouchers(_root(PROBE1, f"{day}_lean.xml"), m)
        for v in vs:
            for line in v["debtor_lines"]:
                types.update(b["bill_type"] for b in line["bill_allocations"])
            banks += [b for line in v["debtor_lines"] + v["counter_lines"] for b in line.get("bank_allocations") or []]
    assert {"On Account", "Advance", "New Ref", "Agst Ref"} <= types
    # exact counts of the real answers (09-Mar 65/65, 25-Mar 45/45, 29-Sep 35/9, 12-Oct 82/20)
    assert len(banks) == 227 and sum(1 for b in banks if b.get("instrument_number")) == 139
    assert all(b.get("unique_reference") for b in banks)


@needs_probes
def test_G12_agent_requests_are_byte_identical_to_the_requests_proven_on_18_nov():
    d = date(2026, 9, 29)
    assert tx.voucher_request(tx.VOUCHER_FULL_FETCH, day=d, scope=SC26) == _req(PROBE2, "20260929_dayscope_lean.request.xml")
    assert tx.voucher_request(tx.MANIFEST_FETCH, day=d, scope=SC26) == _req(PROBE2, "20260929_dayscope_headers.request.xml")
    assert tx.voucher_request(tx.MANIFEST_FETCH, date_from=date(2026, 10, 1), date_to=date(2026, 10, 31), scope=SC26) == \
        _req(PROBE2, "month202610_monthscope_headers.request.xml")
    assert tx.bills_receivable_request(date(2026, 3, 31), COMPANY, date(2024, 4, 1)) == _req(PROBE1, "bills_20260331_typed.request.xml")
    assert tx.bills_payable_request(date(2026, 3, 31), COMPANY, date(2024, 4, 1)) == _req(PROBE2, "billspay_20260331_typed.request.xml")
    assert tx.group_summary_request("Sundry Debtors", FY25.start, FY25.end, COMPANY) == _req(PROBE1, "gs_20260331_typed.request.xml")
    assert tx.group_summary_request("Sundry Creditors", FY25.start, FY25.end, COMPANY) == _req(PROBE2, "gscred_20260331_typed.request.xml")


@needs_probes
@pytest.mark.parametrize("folder,name,as_of", [
    ("1", "bills_20250331_untyped.xml", date(2025, 3, 31)), ("1", "bills_20260331_untyped.xml", date(2026, 3, 31)),
    ("2", "billspay_20250331_untyped.xml", date(2025, 3, 31)), ("2", "billspay_20260331_untyped.xml", date(2026, 3, 31))])
def test_G13_the_real_wrongly_dated_untyped_answers_are_rejected(folder, name, as_of):
    rows = X.parse_bills_any(_root(PROBE1 if folder == "1" else PROBE2, name))
    with pytest.raises(E.BillsDateInvalid):
        E.check_bill_dates(rows, as_of, name)


@needs_probes
@pytest.mark.parametrize("folder,name,as_of", [
    ("1", "bills_20260331_typed.xml", date(2026, 3, 31)), ("1", "bills_20261118_typed.xml", date(2026, 11, 18)),
    ("2", "billspay_20260331_typed.xml", date(2026, 3, 31)), ("2", "billspay_20261118_typed.xml", date(2026, 11, 18))])
def test_G13_the_real_typed_answers_pass_the_date_guard(folder, name, as_of):
    rows = X.parse_bills_any(_root(PROBE1 if folder == "1" else PROBE2, name))
    assert rows
    E.check_bill_dates(rows, as_of, name)


@needs_probes
def test_G14_same_date_group_summary_equals_the_balances_debtors_and_creditors():
    gs = X.parse_group_summary_net
    d_today = X.parse_ledger_balances(_root(PROBE1, "bal_debtors_fy2026-27_to_today.xml"))
    d_25 = X.parse_ledger_balances(_root(PROBE1, "bal_debtors_fy2025-26_to_fyend.xml"))
    c_today = X.parse_ledger_balances(_root(PROBE2, "bal_creditors_fy2026-27_to_today.xml"))
    c_25 = X.parse_ledger_balances(_root(PROBE2, "bal_creditors_fy2025-26_to_fyend.xml"))
    s = lambda b, k: sum((x[k] for x in b.values()), Decimal("0"))
    assert gs(_root(PROBE1, "gs_20261118_typed.xml")) == s(d_today, "closing")
    assert gs(_root(PROBE1, "gs_20260331_typed.xml")) == s(d_25, "closing") == s(d_today, "opening")
    assert gs(_root(PROBE2, "gscred_20261118_typed.xml")) == s(c_today, "closing")
    assert gs(_root(PROBE2, "gscred_20260331_typed.xml")) == s(c_25, "closing") == s(c_today, "opening")
    assert all(c_25[k]["closing"] == c_today[k]["opening"] for k in c_25), "creditor continuity per ledger"
    assert all(d_25[k]["closing"] == d_today[k]["opening"] for k in d_25), "debtor continuity per ledger"
    assert gs(_root(PROBE1, "gs_20250331_typed.xml")) == 0 == gs(_root(PROBE2, "gscred_20250331_typed.xml"))
