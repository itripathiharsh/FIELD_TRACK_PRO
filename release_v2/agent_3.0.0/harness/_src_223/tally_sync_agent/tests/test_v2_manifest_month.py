"""
Agent 2.0.1: month-range voucher manifest.

* request bytes: the one-day request is unchanged from 2.0.0; the range request is
  byte-for-byte the one proven on the client's TallyPrime (17 Nov 2026: 1-7 Apr range
  == union of 7 one-day requests, 472/472 GUIDs; full April 2,781 GUIDs in 18 s);
* month boundaries and the partial current month;
* a range answer is only used if it validates, otherwise that month is re-read one day
  per request; Tally down aborts the scan and nothing is uploaded;
* range and day modes give the identical manifest payload (contract unchanged);
* the pre-scan resumes month by month, including from a 2.0.0 state file;
* replay of the real probe responses (FTP_PROBE_DIR) when the folder is available.
"""
from __future__ import annotations

import json
import os
import xml.etree.ElementTree as ET
from datetime import date, timedelta
from pathlib import Path

import pytest

from tally_sync_agent.core.checkpoint_manager import CheckpointManager
from tally_sync_agent.core.quarantine_store import QuarantineStore
from tally_sync_agent.core.retry_queue import RetryQueue
from tally_sync_agent.core.tally_client import TallyClient
from tally_sync_agent.engine import sync_engine_v2 as E
from tally_sync_agent.extractors import tally_xml as tx
from tally_sync_agent.extractors import v2_extractors as X
from incremental_adapter import IncrementalFromChanged  # 2.2.1 month/day incremental for 2.2.0 fakes

ENV_HEAD = ('<ENVELOPE><HEADER><VERSION>1</VERSION><TALLYREQUEST>Export</TALLYREQUEST><TYPE>Collection</TYPE><ID>FtpVch</ID>'
            '</HEADER><BODY><DESC><STATICVARIABLES><SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT></STATICVARIABLES><TDL>'
            '<TDLMESSAGE><COLLECTION NAME="FtpVch"><TYPE>Voucher</TYPE><FETCH>Date, Guid, VoucherTypeName, IsCancelled, '
            'IsOptional, AlterId</FETCH><FILTER>FtpOneDay</FILTER></COLLECTION><SYSTEM TYPE="Formulae" NAME="FtpOneDay">')
ENV_TAIL = '</SYSTEM></TDLMESSAGE></TDL></DESC></BODY></ENVELOPE>'
# Exactly what agent 2.0.0 sends for 1-Apr-2026 (captured from the frozen source).
DAY_2_0_0 = ENV_HEAD + '$Date = $$Date:"1-Apr-2026"' + ENV_TAIL
# Exactly what manifest_range_equivalence.ps1 sent to the client's Tally on 17 Nov 2026.
RANGE_PROVEN = ENV_HEAD + '$Date &gt;= $$Date:"1-Apr-2026" AND $Date &lt;= $$Date:"7-Apr-2026"' + ENV_TAIL


# ---------------------------------------------------------------------------
# Request bytes
# ---------------------------------------------------------------------------

# 2.2.0: the same bytes with the proven typed FY scope inserted after SVEXPORTFORMAT (Phase 0).
SCOPE = tx.Scope(date(2026, 4, 1), date(2027, 3, 31), "SGRG SERVICES (OPC) PRIVATE LIMITED")
SCOPE_VARS = ('<SVFROMDATE TYPE="Date">1-Apr-2026</SVFROMDATE><SVTODATE TYPE="Date">31-Mar-2027</SVTODATE>'
              '<SVCURRENTCOMPANY>SGRG SERVICES (OPC) PRIVATE LIMITED</SVCURRENTCOMPANY>')


def _scoped(proven: str, a: date = date(2026, 4, 1), b: date = date(2027, 3, 31)) -> str:
    """2.2.1 (B11): the proven 2.0.x body, scoped to the requested day / range (not the FY), with the filter
    names of the 18-Nov day-scope probe (FtpDay for one day, FtpRange for a range)."""
    sv = (f'<SVFROMDATE TYPE="Date">{tx.tally_day(a)}</SVFROMDATE><SVTODATE TYPE="Date">{tx.tally_day(b)}</SVTODATE>'
          '<SVCURRENTCOMPANY>SGRG SERVICES (OPC) PRIVATE LIMITED</SVCURRENTCOMPANY>')
    name = "FtpDay" if a == b else "FtpRange"
    return proven.replace("<SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT>",
                          "<SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT>" + sv).replace("FtpOneDay", name)


def test_day_request_bytes_are_2_0_0_plus_the_typed_day_scope():
    d = date(2026, 4, 1)
    assert tx.voucher_request(tx.MANIFEST_FETCH, day=d, scope=SCOPE) == _scoped(DAY_2_0_0, d, d)


def test_range_request_bytes_are_the_proven_request_plus_the_typed_scope():
    r = tx.voucher_request(tx.MANIFEST_FETCH, date_from=date(2026, 4, 1), date_to=date(2026, 4, 7), scope=SCOPE)
    assert r == _scoped(RANGE_PROVEN, date(2026, 4, 1), date(2026, 4, 7))
    low = r.lower()
    assert "<TALLYREQUEST>Export</TALLYREQUEST>" in r and "import" not in low and "action=" not in low


def test_unscoped_voucher_request_is_refused():
    """R1: never rely on Tally's session context."""
    with pytest.raises(ValueError):
        tx.voucher_request(tx.MANIFEST_FETCH, day=date(2026, 4, 1))


def test_range_request_argument_rules():
    with pytest.raises(ValueError):
        tx.voucher_request(tx.MANIFEST_FETCH, date_from=date(2026, 4, 1), scope=SCOPE)
    with pytest.raises(ValueError):
        tx.voucher_request(tx.MANIFEST_FETCH, day=date(2026, 4, 1), date_from=date(2026, 4, 1), date_to=date(2026, 4, 2), scope=SCOPE)
    with pytest.raises(ValueError):
        tx.voucher_request(tx.MANIFEST_FETCH, date_from=date(2026, 4, 2), date_to=date(2026, 4, 1), scope=SCOPE)
    with pytest.raises(ValueError):  # a date outside the scope's FY can never be requested
        tx.voucher_request(tx.MANIFEST_FETCH, day=date(2026, 3, 31), scope=SCOPE)
    # 2.2.1 B10: an AlterID filter alone (no date) is refused; with a date range it is AND-ed
    with pytest.raises(tx.UnfilteredRequestRefused):
        tx.voucher_request(tx.VOUCHER_FULL_FETCH, min_alter_id=5, scope=SCOPE)
    r = tx.voucher_request(tx.VOUCHER_FULL_FETCH, min_alter_id=5, date_from=date(2026, 4, 1), date_to=date(2026, 4, 30), scope=SCOPE)
    assert r.count("FtpAlter<") == 1 and r.count('NAME="FtpAlter"') == 1 and r.count("FtpRange") == 2


# ---------------------------------------------------------------------------
# Month boundaries
# ---------------------------------------------------------------------------

D = date


@pytest.mark.parametrize("start,end,expected", [
    (D(2026, 4, 1), D(2026, 11, 17),  # the real window on 17 Nov: 7 full months + partial November
     [(D(2026, 4, 1), D(2026, 4, 30)), (D(2026, 5, 1), D(2026, 5, 31)), (D(2026, 6, 1), D(2026, 6, 30)),
      (D(2026, 7, 1), D(2026, 7, 31)), (D(2026, 8, 1), D(2026, 8, 31)), (D(2026, 9, 1), D(2026, 9, 30)),
      (D(2026, 10, 1), D(2026, 10, 31)), (D(2026, 11, 1), D(2026, 11, 17))]),
    (D(2026, 4, 15), D(2026, 5, 3), [(D(2026, 4, 15), D(2026, 4, 30)), (D(2026, 5, 1), D(2026, 5, 3))]),
    (D(2026, 4, 1), D(2026, 4, 30), [(D(2026, 4, 1), D(2026, 4, 30))]),              # today = month end
    (D(2026, 4, 1), D(2026, 5, 1), [(D(2026, 4, 1), D(2026, 4, 30)), (D(2026, 5, 1), D(2026, 5, 1))]),  # 1st
    (D(2026, 12, 20), D(2027, 1, 5), [(D(2026, 12, 20), D(2026, 12, 31)), (D(2027, 1, 1), D(2027, 1, 5))]),
    (D(2028, 2, 1), D(2028, 3, 1), [(D(2028, 2, 1), D(2028, 2, 29)), (D(2028, 3, 1), D(2028, 3, 1))]),  # leap
    (D(2027, 2, 1), D(2027, 2, 28), [(D(2027, 2, 1), D(2027, 2, 28))]),
    (D(2026, 4, 1), D(2026, 4, 1), [(D(2026, 4, 1), D(2026, 4, 1))]),
    (D(2026, 4, 2), D(2026, 4, 1), []),
])
def test_month_chunks(start, end, expected):
    got = E.month_chunks(start, end)
    assert got == expected
    days = [a + timedelta(days=i) for a, b in got for i in range((b - a).days + 1)]
    assert days == [start + timedelta(days=i) for i in range((end - start).days + 1)], "every day exactly once"


def test_full_fy_window_is_twelve_requests_instead_of_365():
    assert len(E.month_chunks(D(2026, 4, 1), D(2027, 3, 31))) == 12


# ---------------------------------------------------------------------------
# Parsing (Tally quirks) and LINEERROR
# ---------------------------------------------------------------------------

QUIRKY = ('<ENVELOPE>\x04<VOUCHER REMOTEID="r1" VCHTYPE="Sales" ACTION="Create"><DATE>20260401</DATE><GUID>g-1</GUID>'
          '<UDF:EXTRA.LIST><VOUCHER>0</VOUCHER></UDF:EXTRA.LIST><VOUCHERTYPENAME>Sales</VOUCHERTYPENAME>'
          '<ALTERID> 120</ALTERID></VOUCHER>'
          '<VOUCHER ACTION="Create"><DATE>20260402</DATE><GUID>g-2</GUID><ALTERID>99</ALTERID></VOUCHER>'
          '<VOUCHER ACTION="Create"><DATE>20260402</DATE><GUID></GUID><ALTERID>130</ALTERID></VOUCHER></ENVELOPE>')


def _root(raw: str) -> ET.Element:
    return ET.fromstring(TallyClient()._clean_xml(raw))  # the agent's own clean-up


def test_entries_agree_with_parse_manifest_on_tally_quirks():
    root = _root(QUIRKY)
    entries = X.parse_manifest_entries(root)
    guids, max_alter = X.parse_manifest(root)
    assert entries == [("g-1", "20260401", 120), ("g-2", "20260402", 99)]
    assert guids == [e[0] for e in entries], "same GUIDs, scalar <VOUCHER>0</VOUCHER> and GUID-less ignored"
    assert max_alter == 130, "parse_manifest (unchanged) still counts a GUID-less voucher's AlterID"


class _Client:
    def __init__(self, raw):
        self.raw, self.sent = raw, []

    def execute_tdl(self, xml):
        self.sent.append(xml)
        return _root(self.raw)


def test_source_range_manifest_sends_the_proven_request_and_rejects_lineerror():
    c = _Client(QUIRKY)
    src = E.TallyV2Source(c, pause_seconds=0)
    src.set_scope(SCOPE)
    assert src.range_manifest(D(2026, 4, 1), D(2026, 4, 7)) == [("g-1", "20260401", 120), ("g-2", "20260402", 99)]
    assert c.sent == [_scoped(RANGE_PROVEN, D(2026, 4, 1), D(2026, 4, 7))]
    bad = E.TallyV2Source(_Client("<ENVELOPE><LINEERROR>Could not find Formula</LINEERROR></ENVELOPE>"), 0)
    bad.set_scope(SCOPE)
    with pytest.raises(E.ManifestRangeUntrusted):
        bad.range_manifest(D(2026, 4, 1), D(2026, 4, 7))


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

def _vp(guid, alter, d):
    return {"guid": guid, "alter_id": alter, "date": d.isoformat(), "voucher_type": "Sales", "voucher_parent": "Sales",
            "debtor_lines": [], "counter_lines": []}


class Src(IncrementalFromChanged):
    """In-memory Tally: day and range answers come from the same data, like the real one."""

    def __init__(self, data, alter=500):
        self.data = data  # date -> [guid]
        self.alter = alter
        self.calls = []
        self.range_hook = None  # (a, b) -> entries | raises
        self.day_hook = None

    def masters(self, cached=None, debtor_min_alter=0, full_debtors=False):
        from test_v2_agent import _masters  # same folder (rootdir-style test modules)
        return _masters()

    def day_manifest(self, d):
        self.calls.append(("day", d))
        if self.day_hook:
            self.day_hook(d)
        return list(self.data.get(d, [])), self.alter if self.data.get(d) else 0

    def range_manifest(self, a, b):
        self.calls.append(("range", a, b))
        if self.range_hook:
            r = self.range_hook(a, b)
            if r is not None:
                return r
        return [(g, d.strftime("%Y%m%d"), self.alter) for d, gs in sorted(self.data.items()) if a <= d <= b for g in gs]

    def day_vouchers(self, m, d):
        self.calls.append(("vday", d))
        return [_vp(g, self.alter, d) for g in self.data.get(d, [])], []

    def changed_vouchers(self, m, min_alter):
        return [], []

    def bills(self, m, as_of):  # 2.2.1: a bill-wise debtor with a receivable has an open bill (sanity rule)
        return [{"ledger_name": "Shop A", "ledger_guid": "G-A", "bill_name": "1", "bill_date": "2026-04-01",
                 "pending_amount": "-5"}]


class Backend:
    def __init__(self):
        self.calls = []

    def heartbeat(self, **kw):
        self.calls.append(("heartbeat", kw))

    def sync_ledgers(self, batch_id, company_guid, ledgers, **kw):
        self.calls.append(("ledgers", len(ledgers), kw))
        return {"details": {}}

    def sync_bills(self, batch_id, company_guid, bills, **kw):
        self.calls.append(("bills", len(bills), kw))
        return {"details": {}}

    def sync_manifest(self, batch_id, company_guid, guids, **kw):
        kw = {k: v for k, v in kw.items() if k != "snapshot_id"}
        self.calls.append(("manifest", sorted(guids), kw))
        return {"details": {}}

    def sync_vouchers(self, batch_id, company_guid, vouchers):
        self.calls.append(("vouchers", [v["guid"] for v in vouchers]))
        return {"created_count": len(vouchers), "updated_count": 0, "retired_count": 0, "errors": []}

    def manifests(self):
        return [c for c in self.calls if c[0] == "manifest"]


class Tally:
    def get_company_info(self):
        return {"name": "SGRG", "guid": "CMP"}


def _eng(tmp_path, src, be, today=D(2026, 11, 17)):
    db = tmp_path / "s.db"
    e = E.SyncEngineV2(tally_client=Tally(), backend_client=be, checkpoint_manager=CheckpointManager(db),
                       retry_queue=RetryQueue(db), quarantine_store=QuarantineStore(db), data_dir=tmp_path,
                       source=src, today=lambda: today)
    e.period_start = D(2026, 4, 1)
    return e


def _data():
    # Vouchers on month edges, a leap-free Feb is irrelevant here; November is the partial month.
    return {D(2026, 4, 1): ["a1"], D(2026, 4, 30): ["a30"], D(2026, 5, 1): ["m1"], D(2026, 5, 31): ["m31"],
            D(2026, 6, 15): ["j15", "j15b"], D(2026, 7, 31): ["jl31"], D(2026, 8, 1): ["au1"], D(2026, 9, 30): ["s30"],
            D(2026, 10, 1): ["o1"], D(2026, 10, 31): ["o31"], D(2026, 11, 17): ["n17"]}


def _all(data):
    return sorted(g for gs in data.values() for g in gs)


def test_month_scan_is_eight_requests_on_17_nov_and_equals_the_day_scan(tmp_path, monkeypatch):
    data = _data()
    src = Src(data)
    eng = _eng(tmp_path, src, Backend())
    guids, mx = eng.scan_manifest()
    assert guids == _all(data) and mx == 500
    assert [c for c in src.calls] == [("range", a, b) for a, b in E.month_chunks(D(2026, 4, 1), D(2026, 11, 17))]
    assert src.calls[-1] == ("range", D(2026, 11, 1), D(2026, 11, 17)), "partial current month ends today"
    monkeypatch.setattr(E.settings, "manifest_scan_mode", "day")
    src2 = Src(data)
    eng2 = _eng(tmp_path / "d", src2, Backend())
    (tmp_path / "d").mkdir(exist_ok=True)
    assert eng2.scan_manifest() == (guids, mx)
    assert len(src2.calls) == (D(2026, 11, 17) - D(2026, 4, 1)).days + 1 == 231, "day mode = the 2.0.0 requests"
    assert all(c[0] == "day" for c in src2.calls)


def test_manifest_payload_identical_in_month_and_day_mode(tmp_path, monkeypatch):
    payloads = {}
    for mode in ("month", "day"):
        monkeypatch.setattr(E.settings, "manifest_scan_mode", mode)
        d = tmp_path / mode
        d.mkdir()
        be = Backend()
        eng = _eng(d, Src(_data()), be)
        eng.initial_load("CMP")
        payloads[mode] = be.manifests()
        assert eng.checkpoints.get_checkpoint(E.CP_VOUCHERS)["last_alter_id"] == 500
    assert payloads["month"] == payloads["day"]
    (_, guids, kw), = payloads["month"]
    assert guids == _all(_data())
    assert kw == {"window_from": "2026-04-01", "window_to": "2026-11-17", "is_final_chunk": True}


@pytest.mark.parametrize("kind", ["tally_error", "outside_window", "missing_date", "empty"])
def test_untrusted_month_is_reread_one_day_per_request_only_for_that_month(tmp_path, kind):
    data = _data()
    src = Src(data)

    def hook(a, b):
        if a.month != 6:
            return None
        if kind == "tally_error":
            raise E.ManifestRangeUntrusted("Tally error: x")
        if kind == "connection":
            raise E.TallyConnectionError("timed out")
        if kind == "outside_window":
            return [("j15", "20260615", 500), ("stray", "20260701", 500)]
        if kind == "missing_date":
            return [("j15", "", 500)]
        return []
    if kind == "empty":
        data.pop(D(2026, 6, 15))
    src.range_hook = hook
    eng = _eng(tmp_path, src, Backend())
    guids, _ = eng.scan_manifest()
    assert guids == _all(data), "the fallback result is the true set; no stray GUID gets in"
    june_days = [c for c in src.calls if c[0] == "day"]
    assert june_days == [("day", D(2026, 6, 1) + timedelta(days=i)) for i in range(30)]
    assert len([c for c in src.calls if c[0] == "range"]) == 8
    assert eng.last_scan_stats["day_fallbacks"] == 1


def test_B5_a_failed_month_request_is_not_followed_by_day_requests(tmp_path):
    """2.2.1 B5: 2.2.0 answered a timed-out month with up to 31 immediate day requests. Now the failure propagates
    (the breaker opens) and no day request is sent."""
    src = Src(_data())

    def hook(a, b):
        if a.month == 6:
            raise E.TallyConnectionError("timed out")
    src.range_hook = hook
    eng = _eng(tmp_path, src, Backend())
    with pytest.raises(E.TallyConnectionError):
        eng.scan_manifest()
    assert not [c for c in src.calls if c[0] == "day"], "no fallback burst after a timeout"


def test_tally_down_aborts_the_daily_manifest_and_nothing_is_uploaded(tmp_path):
    src = Src(_data())
    be = Backend()
    eng = _eng(tmp_path, src, be)
    eng.checkpoints.update_checkpoint(E.CP_VOUCHERS, alter_id=500, records_count=0)
    eng.checkpoints.update_checkpoint(E.CP_BALANCES, records_count=0)
    eng.checkpoints.update_checkpoint(E.CP_MANIFEST, last_sync_date="2026-11-15", records_count=1)
    eng.manifest_due = lambda: True

    def down(a, b):
        if a.month == 9:
            raise E.TallyConnectionError("refused")
    src.range_hook = down
    src.day_hook = lambda d: (_ for _ in ()).throw(E.TallyConnectionError("refused"))
    r = eng.run_sync()
    assert r["status"] == "TALLY_UNAVAILABLE" and be.manifests() == [], "a partial scan never retires anything"
    assert eng.checkpoints.get_checkpoint(E.CP_MANIFEST)["last_sync_date"] == "2026-11-15", "still due next cycle"
    src.range_hook = src.day_hook = None
    r = eng.run_sync()
    assert r["status"] == "COMPLETED" and be.manifests()[0][1] == _all(_data())


def test_prescan_resumes_month_by_month_after_interruption(tmp_path):
    data = _data()
    src = Src(data, alter=500)

    def fail_june(a, b):
        if a.month == 6:
            raise E.TallyConnectionError("Tally closed")
    src.range_hook = fail_june
    src.day_hook = lambda d: (_ for _ in ()).throw(E.TallyConnectionError("Tally closed")) if d.month == 6 else None
    be = Backend()
    eng = _eng(tmp_path, src, be)
    with pytest.raises(E.TallyConnectionError):
        eng.initial_load("CMP")
    st = json.loads((tmp_path / "initial_load_v2.json").read_text())
    assert st["snapshots_done"] and "m0" not in st
    assert st["prescan_through"] == "2026-05-31" and st["prescan_guids"] == ["a1", "a30", "m1", "m31"]
    assert st["prescan_max_alter"] == 500 and not be.manifests()

    src2 = Src(data, alter=777)  # vouchers altered while it was down: later months see higher AlterIDs
    be2 = Backend()
    eng2 = _eng(tmp_path, src2, be2)
    eng2.initial_load("CMP")
    ranges = [c for c in src2.calls if c[0] == "range"]
    assert ranges[0] == ("range", D(2026, 6, 1), D(2026, 6, 30)), "April and May are not read again"
    assert len(ranges) == 6 and not [c for c in be2.calls if c[0] in ("ledgers", "bills")]
    assert be2.manifests()[0][1] == _all(data)
    assert eng2.checkpoints.get_checkpoint(E.CP_VOUCHERS)["last_alter_id"] == 777


def test_a_2_0_0_state_file_resumes_with_a_full_prescan(tmp_path):
    (tmp_path / "initial_load_v2.json").write_text(json.dumps({"snapshots_done": True}))  # the interrupted 16 Nov run
    src = Src(_data())
    be = Backend()
    eng = _eng(tmp_path, src, be)
    eng.initial_load("CMP")
    assert [c for c in src.calls if c[0] == "range"][0] == ("range", D(2026, 4, 1), D(2026, 4, 30))
    assert not [c for c in be.calls if c[0] in ("ledgers", "bills")], "snapshots are not repeated"
    assert be.manifests()[0][1] == _all(_data())


def test_progress_is_logged_per_month(tmp_path, monkeypatch):
    lines = []
    monkeypatch.setattr(E.logger, "info", lambda msg, *a, **k: lines.append(msg))
    monkeypatch.setattr(E.logger, "warning", lambda msg, *a, **k: lines.append("WARN " + msg))
    src = Src(_data())
    src.range_hook = lambda a, b: (_ for _ in ()).throw(E.ManifestRangeUntrusted("x")) if a.month == 8 else None
    _eng(tmp_path, src, Backend()).scan_manifest()
    scans = [l for l in lines if l.startswith("MANIFEST_SCAN 2026")]
    assert len(scans) == 8 and scans[0].startswith("MANIFEST_SCAN 2026-04-01..2026-04-30 mode=range guids=2")
    assert "mode=day-fallback" in scans[4] and any(l.startswith("WARN MANIFEST_SCAN 2026-08-01..2026-08-31") for l in lines)
    assert [l for l in lines if l.startswith("MANIFEST_SCAN_DONE")][0].split()[3:5] == ["chunks=8", "day_fallbacks=1"]


# ---------------------------------------------------------------------------
# Replay of probe responses saved by manifest_range_equivalence.ps1
# ---------------------------------------------------------------------------

def replay_probe_dir(folder: Path) -> dict:
    """Parse saved responses with the agent's own clean-up and parser and check range == union(days)."""
    def load(p: Path):
        return X.parse_manifest_entries(_root(p.read_text(encoding="utf-8-sig")))
    days = {p.stem[4:]: load(p) for p in sorted(folder.glob("day_*.xml"))}
    before = load(next(folder.glob("range_*_before.xml")))
    after = load(next(folder.glob("range_*_after.xml")))
    month_files = list(folder.glob("range_*_month.xml"))
    month = load(month_files[0]) if month_files else []
    union = {g: d for k, es in days.items() for g, d, _ in es}
    lo, hi = min(days), max(days)
    return {
        "days": {k: len(v) for k, v in days.items()},
        "day_dates_ok": all(d == k for k, es in days.items() for _, d, _ in es),
        "union": len(union),
        "range": len(before),
        "equal": {g for g, _, _ in before} == set(union) == {g for g, _, _ in after},
        "range_dates_ok": all(lo <= d <= hi and union.get(g) == d for g, d, _ in before),
        "range_dups": len(before) - len({g for g, _, _ in before}),
        "month": len(month),
        "month_contains_week": set(union) <= {g for g, _, _ in month} if month else None,
        "month_dates_ok": all(d[:6] == lo[:6] for _, d, _ in month),
        "month_dups": len(month) - len({g for g, _, _ in month}),
    }


def _write_probe(folder: Path, data):
    folder.mkdir(parents=True)

    def env(items):
        return "<ENVELOPE>" + "".join(
            f'<VOUCHER ACTION="Create"><DATE>{d:%Y%m%d}</DATE><GUID>{g}</GUID><UDF:X.LIST><VOUCHER>0</VOUCHER>'
            f'</UDF:X.LIST><ALTERID> 9</ALTERID></VOUCHER>' for d, g in items) + "</ENVELOPE>"
    week = [(d, g) for d, gs in sorted(data.items()) if d.day <= 7 for g in gs]
    for i in range(7):
        d = D(2026, 4, 1 + i)
        (folder / f"day_{d:%Y%m%d}.xml").write_text(env([x for x in week if x[0] == d]), encoding="utf-8-sig")
    for n in ("range_0401_0407_before", "range_0401_0407_after"):
        (folder / f"{n}.xml").write_text(env(week), encoding="utf-8-sig")
    (folder / "range_0401_0430_month.xml").write_text(
        env([(d, g) for d, gs in sorted(data.items()) if d.month == 4 for g in gs]), encoding="utf-8-sig")


def test_replay_checker_on_synthetic_probe_folder(tmp_path):
    data = {D(2026, 4, 1): ["a", "b"], D(2026, 4, 3): ["c"], D(2026, 4, 7): ["d"], D(2026, 4, 20): ["e"]}
    _write_probe(tmp_path / "p", data)
    r = replay_probe_dir(tmp_path / "p")
    assert r["equal"] and r["union"] == r["range"] == 4 and r["month"] == 5 and r["month_contains_week"]
    assert r["day_dates_ok"] and r["range_dates_ok"] and r["month_dates_ok"] and not r["range_dups"]
    (tmp_path / "p" / "range_0401_0407_after.xml").write_text("<ENVELOPE></ENVELOPE>", encoding="utf-8")
    assert not replay_probe_dir(tmp_path / "p")["equal"], "the checker does detect a difference"


PROBE = os.environ.get("FTP_PROBE_DIR")


@pytest.mark.skipif(not PROBE or not Path(PROBE).is_dir(), reason="set FTP_PROBE_DIR to the client's manifest_range_probe_* folder")
def test_real_client_probe_responses():
    r = replay_probe_dir(Path(PROBE))
    print(json.dumps(r, indent=2))
    assert r["equal"] and r["union"] == r["range"] == 472, r
    assert r["day_dates_ok"] and r["range_dates_ok"] and r["range_dups"] == 0
    assert r["month"] == 2781 and r["month_contains_week"] and r["month_dates_ok"] and r["month_dups"] == 0


def test_heartbeat_after_every_month_keeps_the_agent_online_during_scans(tmp_path):
    src = Src(_data())
    be = Backend()
    eng = _eng(tmp_path, src, be)
    eng.initial_load("CMP")
    hb = [c[1]["tally_status"] for c in be.calls if c[0] == "heartbeat"]
    assert hb.count("INITIAL_LOAD") >= 8, "one per pre-scan month (plus one per loaded day)"
    eng.checkpoints.update_checkpoint(E.CP_BALANCES, records_count=0)
    eng.manifest_due = lambda: True
    be.calls.clear()
    assert eng.run_sync()["status"] == "COMPLETED"
    hb = [c[1]["tally_status"] for c in be.calls if c[0] == "heartbeat"]
    assert hb.count("ONLINE") == 1 + 8, "cycle start + one per manifest month"
    assert len(be.manifests()) == 1
