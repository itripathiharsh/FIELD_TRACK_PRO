"""
Agent 2.2.0 - mandatory regression tests for every known failure (R1..R14), multi-FY isolation,
and golden tests on the client's real Phase 0 XML (18 Nov 2026).

  R1  collection without explicit company + FY scope            R8  reliance on Tally's session context
  R2  zero / blank ledger balances                              R9  wrong company selection / GUID fallback
  R2b opening balances overwritten by closing balances          R10 VM timezone (UTC) used for "today"
  R3  empty first load marked complete                          R11 untyped (wrong) Tally date format
  R4  checkpoints advanced after a rejected manifest            R12 .env with a BOM loses its first key
  R5  stale snapshot kept after recovery                        R13 historical data interfering with the live FY
  R6  dry-run output mistaken for backend acceptance            R14 duplicate records across FYs
  R7  manifest with a wrong (too small) count
Golden tests (G*) are skipped only when the Phase 0 folder is absent (PHASE0_DIR overrides it).
"""
from __future__ import annotations

import json
import os
import xml.etree.ElementTree as ET
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from test_v2_agent import DEBTORS, GROUPS, LEDGERS, RECEIPT, VTYPES, FakeSource, RecordingBackend, _engine, _masters, _vp
from tally_sync_agent import main
from tally_sync_agent.config import fiscal as F
from tally_sync_agent.config import settings as S
from tally_sync_agent.core.checkpoint_manager import CheckpointManager
from tally_sync_agent.core.quarantine_store import QuarantineStore
from tally_sync_agent.core.retry_queue import RetryQueue
from tally_sync_agent.core.tally_client import TallyClient
from tally_sync_agent.engine import multi_fy as MF
from tally_sync_agent.engine import sync_engine_v2 as E
from tally_sync_agent.extractors import tally_xml as tx
from tally_sync_agent.extractors import v2_extractors as X

COMPANY = "SGRG SERVICES (OPC) PRIVATE LIMITED"
GUID = "19a03e17-e1ab-44f2-8e7f-1bff56f20ebe"
FY26 = F.parse_fy("2026-27")
FY25 = F.parse_fy("2025-26")
FY24 = F.parse_fy("2024-25")
SC26 = tx.Scope(FY26.start, FY26.end, COMPANY)
SC25 = tx.Scope(FY25.start, FY25.end, COMPANY)
EMPTY = "<ENVELOPE></ENVELOPE>"
DEBTORS_BLANK = DEBTORS.replace("<OPENINGBALANCE>-1000.00</OPENINGBALANCE><CLOSINGBALANCE>-1500.00</CLOSINGBALANCE>",
                                "<OPENINGBALANCE></OPENINGBALANCE><CLOSINGBALANCE></CLOSINGBALANCE>")
DEBTORS_OPEN_EQ_CLOSE = DEBTORS.replace("<OPENINGBALANCE>-1000.00</OPENINGBALANCE>", "<OPENINGBALANCE>-1500.00</OPENINGBALANCE>")


def _ctx(fy: F.FinancialYear, legacy=False, historical=True) -> F.FyContext:
    return F.FyContext(fy=fy, legacy=legacy, historical=historical)


def _hist_engine(tmp_path, src, backend, fy=FY25, today=date(2026, 11, 18), db=None):
    db = db or tmp_path / "s.db"
    return E.SyncEngineV2(tally_client=object(), backend_client=backend, checkpoint_manager=CheckpointManager(db),
                          retry_queue=RetryQueue(db), quarantine_store=QuarantineStore(db), data_dir=tmp_path,
                          source=src, today=lambda: today, fy=_ctx(fy))


class ScopedTally:
    """A fake Tally that answers period collections only when the typed scope + company is sent (as the
    client's Tally did in Phase 0) and serves Group Summary totals; records every request."""

    def __init__(self, debtors=DEBTORS, gs_close=Decimal("-1500.00"), gs_prev=Decimal("-1000.00")):
        self.requests, self.debtors, self.gs_close, self.gs_prev = [], debtors, gs_close, gs_prev

    def execute_tdl(self, xml):
        self.requests.append(xml)
        typed = '<SVFROMDATE TYPE="Date">' in xml and "<SVCURRENTCOMPANY>" in xml
        if "<ID>Group Summary</ID>" in xml:
            amt = self.gs_prev if ("<SVTODATE>20260331</SVTODATE>" in xml
                                   or '<SVTODATE TYPE="Date">31-Mar-2026</SVTODATE>' in xml) else self.gs_close
            tag = "DSPCLDRAMTA" if amt < 0 else "DSPCLCRAMTA"
            return ET.fromstring(f"<ENVELOPE><DSPACCINFO><{tag}>{amt}</{tag}></DSPACCINFO></ENVELOPE>")
        if "FtpDebtors" in xml:
            return ET.fromstring(self.debtors if typed else DEBTORS_BLANK)
        if "<TYPE>Group</TYPE>" in xml:
            return ET.fromstring(GROUPS)
        if "<TYPE>VoucherType</TYPE>" in xml:
            return ET.fromstring(VTYPES)
        if "<TYPE>Ledger</TYPE>" in xml:
            return ET.fromstring(LEDGERS)
        if "<TYPE>Voucher</TYPE>" in xml:
            return ET.fromstring(RECEIPT if typed else EMPTY)
        return ET.fromstring(EMPTY)


def _approve_first_load(eng):
    """What `approve-first-load <fy>` writes (2.2.1 item 1)."""
    (eng.data_dir / f"approve_first_load_{eng.fy.label}.json").write_text("{}", encoding="utf-8")


def _live_engine_on(tmp_path, tally, backend=None, today=date(2026, 11, 18)):
    src = E.TallyV2Source(tally, pause_seconds=0)
    eng = _engine(tmp_path, src, backend or RecordingBackend(), today=today)
    eng.company_name = COMPANY
    return eng, src


# ============================================================ R1 / R8 / R11 - scope on every collection

def test_R1_every_period_collection_refuses_to_be_built_without_a_scope():
    for build in (lambda: tx.voucher_request(tx.MANIFEST_FETCH, day=date(2026, 4, 1)),
                  lambda: tx.voucher_request(tx.VOUCHER_FULL_FETCH, min_alter_id=5),
                  lambda: tx.debtors_request(), lambda: tx.creditors_request()):
        with pytest.raises(ValueError):
            build()
    with pytest.raises(ValueError):
        tx.Scope(FY26.start, FY26.end, "")  # a scope always names the company


def test_R11_collections_use_the_typed_form_and_never_the_untyped_one():
    v = tx.voucher_request(tx.MANIFEST_FETCH, day=date(2026, 11, 13), scope=SC26)
    d = tx.debtors_request(scope=SC25)
    assert ('<SVFROMDATE TYPE="Date">13-Nov-2026</SVFROMDATE><SVTODATE TYPE="Date">13-Nov-2026</SVTODATE>'
            f'<SVCURRENTCOMPANY>{COMPANY}</SVCURRENTCOMPANY>') in v  # 2.2.1 B11: the day, not the FY
    assert '<SVFROMDATE TYPE="Date">1-Apr-2025</SVFROMDATE><SVTODATE TYPE="Date">31-Mar-2026</SVTODATE>' in d
    for r in (v, d, tx.creditors_request(scope=SC25)):
        assert "<SVFROMDATE>" not in r and "<SVTODATE>" not in r, "the untyped form returned wrong balances (Phase 0)"
        ET.fromstring(r)


def test_R11_reports_use_the_typed_form_with_company_2_2_1():
    """2.2.1 A3: the untyped report form ignored past as-of dates (18-Nov probe); reports are typed now."""
    b = tx.bills_receivable_request(date(2026, 11, 18), COMPANY, date(2024, 4, 1))
    g = tx.group_summary_request("Sundry Debtors", FY25.start, FY25.end, COMPANY)
    assert ('<SVFROMDATE TYPE="Date">1-Apr-2024</SVFROMDATE><SVTODATE TYPE="Date">18-Nov-2026</SVTODATE>'
            f"<SVCURRENTCOMPANY>{COMPANY}</SVCURRENTCOMPANY>") in b
    assert ('<SVFROMDATE TYPE="Date">1-Apr-2025</SVFROMDATE><SVTODATE TYPE="Date">31-Mar-2026</SVTODATE>'
            f"<GROUPNAME>Sundry Debtors</GROUPNAME><EXPLODEFLAG>No</EXPLODEFLAG><SVCURRENTCOMPANY>{COMPANY}</SVCURRENTCOMPANY>") in g
    for r in (b, g):
        assert "<SVTODATE>2" not in r and "<SVFROMDATE>2" not in r, "untyped report dates are never sent"
    with pytest.raises(ValueError):
        tx.bills_receivable_request(date(2026, 11, 18), COMPANY)  # no books start -> refused, never untyped


def test_R1_R8_every_collection_the_source_sends_is_scoped(tmp_path):
    tally = ScopedTally()
    eng, src = _live_engine_on(tmp_path, tally)
    eng.apply_scope()
    m = src.masters(full_debtors=True)
    src.changed_headers(date(2026, 11, 1), date(2026, 11, 18), 121240)
    src.changed_vouchers_on(m, date(2026, 11, 13), 121240)
    src.day_vouchers(m, date(2026, 11, 13))
    src.day_manifest(date(2026, 11, 13))
    src.range_manifest(date(2026, 11, 1), date(2026, 11, 18))
    src.creditors()
    period_collections = [r for r in tally.requests if "<TYPE>Voucher</TYPE>" in r or "<CHILDOF>" in r]
    assert len(period_collections) >= 7
    import re as _re
    for r in period_collections:
        m_ = _re.search(r'<SVFROMDATE TYPE="Date">(\d+)-(\w+)-(\d{4})</SVFROMDATE><SVTODATE TYPE="Date">', r)
        assert m_ and f"<SVCURRENTCOMPANY>{COMPANY}" in r, r[:300]
        assert m_.group(3) == "2026" and m_.group(2) in ("Apr", "Nov"), "inside FY 2026-27 (FY start or the asked day/month)"


def test_R1_the_2_1_0_unscoped_request_gets_nothing_and_the_scoped_one_gets_vouchers(tmp_path):
    tally = ScopedTally()
    src = E.TallyV2Source(tally, pause_seconds=0)
    with pytest.raises(ValueError):  # 2.2.0 cannot even build the unscoped request
        src.day_vouchers(_masters(), date(2026, 11, 13))
    src.set_scope(SC26)
    good, _ = src.day_vouchers(_masters(), date(2026, 11, 13))
    assert [v["guid"] for v in good] == ["V-1", "V-2"]


# ============================================================ R2 / R2b - balances checked against Tally

def test_R2_blank_balances_are_refused_before_any_ledger_upload(tmp_path):
    tally = ScopedTally(debtors=DEBTORS_BLANK)  # every balance blank while Tally's Group Summary is -1500
    be = RecordingBackend()
    eng, _ = _live_engine_on(tmp_path, tally, be)
    with pytest.raises(E.BalanceCheckFailed):
        eng.ledger_snapshot(GUID)
    assert not [c for c in be.calls if c[0] == "ledgers"], "nothing uploaded"


def test_R2b_opening_overwritten_by_closing_is_refused(tmp_path):
    tally = ScopedTally(debtors=DEBTORS_OPEN_EQ_CLOSE)  # opening == closing (the untyped-form symptom)
    be = RecordingBackend()
    eng, _ = _live_engine_on(tmp_path, tally, be)
    with pytest.raises(E.BalanceCheckFailed) as ex:
        eng.ledger_snapshot(GUID)
    assert "sum_opening" in str(ex.value) and not [c for c in be.calls if c[0] == "ledgers"]


def test_R2_correct_balances_pass_and_are_uploaded_with_the_check_result(tmp_path):
    be = RecordingBackend()
    sent = []
    orig = be.sync_ledgers
    be.sync_ledgers = lambda b, c, ledgers, **kw: (sent.extend(ledgers), orig(b, c, ledgers, **kw))[1]
    eng, _ = _live_engine_on(tmp_path, ScopedTally(), be)
    r = eng.ledger_snapshot(GUID)
    assert r["balance_check"]["checked"] and r["balance_check"]["sum_closing"] == "-1500.00"
    shop_a = [x for x in sent if x.get("name") == "Shop A"][0]
    assert shop_a["opening_balance"] == "-1000.00" and shop_a["closing_balance"] == "-1500.00"


def test_R2_run_sync_reports_balance_check_failed_and_keeps_checkpoints(tmp_path):
    class T(ScopedTally):
        def get_company_info(self):
            return {"name": COMPANY, "guid": GUID, "companies": [COMPANY]}
    tally = T(debtors=DEBTORS_BLANK)
    eng, _ = _live_engine_on(tmp_path, tally)
    eng.tally = tally
    eng.checkpoints.update_checkpoint(E.CP_VOUCHERS, alter_id=121240, records_count=22989)
    before = eng.checkpoints.get_checkpoint(E.CP_BALANCES)
    r = eng.run_sync()
    assert r["status"] == "BALANCE_CHECK_FAILED"
    assert eng.checkpoints.get_checkpoint(E.CP_BALANCES) == before
    assert eng.checkpoints.get_checkpoint(E.CP_VOUCHERS)["last_alter_id"] == 121240


# ============================================================ R3 / R4 / R5 / R7 - load and manifest guards

def test_R3_empty_first_load_is_not_complete_and_writes_no_checkpoint(tmp_path):
    src, be = FakeSource({}), RecordingBackend()
    eng = _engine(tmp_path, src, be, today=date(2026, 4, 5))
    with pytest.raises(E.InitialLoadEmpty):
        eng.initial_load(GUID)
    assert not eng.checkpoints.get_checkpoint(E.CP_VOUCHERS).get("last_successful_sync_at")
    assert not eng.checkpoints.get_checkpoint(E.CP_MANIFEST).get("last_successful_sync_at")
    assert not [c for c in be.calls if c[0] in ("manifest", "vouchers")]
    state = eng._load_state()   # 3.0: in the agent database
    assert not any(k in state for k in ("completed_at", "m0", "loaded_through", "prescan_through", "movements"))


def test_R3_empty_load_is_retried_next_cycle(tmp_path):
    class T:
        def get_company_info(self):
            return {"name": COMPANY, "guid": GUID, "companies": [COMPANY]}
    src = FakeSource({})
    eng = _engine(tmp_path, src, RecordingBackend(), today=date(2026, 4, 3))
    eng.tally = T()
    assert eng.run_sync()["status"] == "CHECKPOINT_ZERO" and src.calls == []  # 2.2.1: no approval -> nothing requested
    _approve_first_load(eng)
    assert eng.run_sync()["status"] == "INITIAL_LOAD_EMPTY"
    src.days = {date(2026, 4, 2): [_vp("A", 10, "2026-04-02")]}
    r = eng.run_sync()
    assert r["status"] == "COMPLETED" and r["initial_load"]["vouchers"]["vouchers"] == 1


def test_R4_rejected_manifest_does_not_complete_then_completes_without_rereading(tmp_path):
    d1, d2 = date(2026, 4, 1), date(2026, 4, 2)
    src = FakeSource({d1: [_vp("A", 10)], d2: [_vp("B", 20, "2026-04-02")]})

    class Rejecting(RecordingBackend):
        reject = True

        def sync_manifest(self, batch_id, company_guid, guids, **kw):
            super().sync_manifest(batch_id, company_guid, guids, **kw)
            return {"details": {"error": "manifest lists 2 vouchers, FieldTrack holds 16879: not applied"}} if self.reject \
                else {"details": {"retired": {}}}
    be = Rejecting()
    eng = _engine(tmp_path, src, be, today=d2)
    with pytest.raises(E.ManifestRejected):
        eng.initial_load(GUID)
    assert not eng.checkpoints.get_checkpoint(E.CP_VOUCHERS).get("last_successful_sync_at")
    assert not eng.checkpoints.get_checkpoint(E.CP_MANIFEST).get("last_successful_sync_at")
    be.reject = False
    src.calls.clear()
    eng.initial_load(GUID)
    assert not [c for c in src.calls if c[0] == "day"], "days already uploaded are not read again"
    assert eng.checkpoints.get_checkpoint(E.CP_VOUCHERS)["last_alter_id"] == 100


def test_R4_rejected_nightly_manifest_keeps_existing_checkpoints(tmp_path):
    class T:
        def get_company_info(self):
            return {"name": COMPANY, "guid": GUID, "companies": [COMPANY]}

    class Rejecting(RecordingBackend):
        def sync_manifest(self, *a, **k):
            return {"details": {"error": "manifest lists 0 vouchers, FieldTrack holds 16879: not applied"}}
    eng = _engine(tmp_path, FakeSource({date(2026, 4, 1): [_vp("A", 101)]}), Rejecting())
    eng.tally = T()
    for cp, kw in ((E.CP_VOUCHERS, dict(alter_id=121240, records_count=22989)),
                   (E.CP_MANIFEST, dict(last_sync_date="2026-11-17", records_count=22753)),
                   (E.CP_BALANCES, dict(records_count=4990))):
        eng.checkpoints.update_checkpoint(cp, **kw)
    with eng.checkpoints._connection() as c:
        c.execute("UPDATE checkpoints SET last_successful_sync_at='2000-01-01T00:00:00+00:00' WHERE entity_type=?", (E.CP_MANIFEST,))
        c.commit()
    before = eng.checkpoints.get_checkpoint(E.CP_MANIFEST)
    eng.nightly_due = lambda: True   # 3.0: the manifest is the last step of the nightly reconciliation
    assert eng.run_sync()["status"] == "MANIFEST_REJECTED"
    assert not eng.checkpoints.get_checkpoint("reconcile_nightly_v3").get("last_sync_date"), "nightly stays due"
    assert eng.checkpoints.get_checkpoint(E.CP_MANIFEST) == before
    assert eng.checkpoints.get_checkpoint(E.CP_VOUCHERS)["last_alter_id"] == 121240


def test_R5_the_2_1_0_empty_completion_is_reloaded_with_fresh_snapshots(tmp_path):
    """Production's real state of 18 Nov 2026."""
    class T:
        def get_company_info(self):
            return {"name": COMPANY, "guid": GUID, "companies": [COMPANY]}
    d1, d3 = date(2026, 4, 1), date(2026, 4, 3)
    src, be = FakeSource({d1: [_vp("A", 10)], d3: [_vp("C", 30, "2026-04-03")]}), RecordingBackend()
    eng = _engine(tmp_path, src, be, today=d3)
    eng.tally = T()
    eng.checkpoints.update_checkpoint(E.CP_VOUCHERS, alter_id=0, records_count=0)
    eng.checkpoints.update_checkpoint(E.CP_MANIFEST, last_sync_date="2026-04-03", records_count=0)
    (tmp_path / "initial_load_v2.json").write_text(json.dumps(
        {"snapshots_done": True, "prescan_through": "2026-04-03", "prescan_guids": [], "prescan_max_alter": 0,
         "m0": 0, "loaded_through": "2026-04-03", "completed_at": "2026-04-03T20:43:41+00:00"}))
    r0 = eng.run_sync()  # 2.2.1 item 1: production's checkpoint-0 state stops safely until approved
    assert r0["status"] == "CHECKPOINT_ZERO" and src.calls == [] and r0["checkpoint_status"] == "EMPTY_COMPLETION"
    assert eng.checkpoints.get_checkpoint(E.CP_VOUCHERS)["last_alter_id"] == 0, "checkpoint not modified"
    _approve_first_load(eng)
    r = eng.run_sync()
    assert r["status"] == "COMPLETED"
    assert "ledgers" in r["initial_load"] and "bills" in r["initial_load"], "fresh snapshots after recovery"
    assert len([c for c in src.calls if c[0] == "day"]) == 3
    assert eng.checkpoints.get_checkpoint(E.CP_VOUCHERS)["last_alter_id"] == 100


def test_R7_manifest_floor_empty_and_below_half_are_refused_locally(tmp_path):
    be = RecordingBackend()
    eng = _engine(tmp_path, FakeSource({}), be)
    with pytest.raises(E.ManifestRejected):
        eng.upload_manifest(GUID, [])
    eng.checkpoints.update_checkpoint(eng.fy.cp_manifest_count, alter_id=22753)
    with pytest.raises(E.ManifestRejected):
        eng.upload_manifest(GUID, [f"g{i}" for i in range(11000)])
    assert not [c for c in be.calls if c[0] == "manifest"], "nothing was sent"
    eng.upload_manifest(GUID, [f"g{i}" for i in range(12000)])
    assert eng.checkpoints.get_checkpoint(eng.fy.cp_manifest_count)["last_alter_id"] == 12000


# ============================================================ R6 - dry run is never backend proof

def test_R6_dry_run_report_has_no_backend_fields_and_says_not_uploaded(tmp_path):
    engine = MagicMock()
    engine.tally.get_company_info.return_value = {"name": COMPANY, "guid": GUID, "companies": [COMPANY]}
    engine.initial_load.return_value = {"fy": "2026-27", "ledgers": {"ledgers": 5, "result": {}},
                                        "vouchers": {"days": 2, "vouchers": 9, "created": 9, "updated": 0},
                                        "manifest": {"ok": True}}
    engine.counters = {"extracted": 10, "validated": 9, "rejected_local": 1, "outside_fy": 0, "uploaded": 9, "accepted": 9}
    engine.quarantine.list_unresolved.return_value = []
    out = tmp_path / "dry"
    with patch.object(main, "SyncEngineV2", return_value=engine):
        main.cmd_dry_run(SimpleNamespace(out=str(out)))
    rep = json.loads((out / "dry_run_report.json").read_text())
    assert rep["upload_status"].startswith("NOT_UPLOADED")
    flat = json.dumps(rep)
    for k in ('"result"', '"created"', '"updated"', '"manifest"', '"accepted"', '"uploaded"'):
        assert k not in flat
    assert rep["counters_extracted_validated"] == {"extracted": 10, "validated": 9, "rejected_local": 1, "outside_fy": 0}


# ============================================================ R9 - company selection

class _CmpClient(TallyClient):
    def __init__(self, xml):
        self.xml = xml

    def execute_tdl(self, payload):
        return ET.fromstring(self.xml)


CMP_ONE = (f'<ENVELOPE><CMPINFO><COMPANY>8</COMPANY><VOUCHER>174</VOUCHER></CMPINFO>'
           f'<COMPANY NAME="{COMPANY}"><BOOKSFROM>20240401</BOOKSFROM><NAME>{COMPANY}</NAME><GUID>{GUID}</GUID></COMPANY></ENVELOPE>')


def test_R9_scalar_company_count_is_not_a_company_and_the_real_one_is_selected():
    with patch.object(S.settings, "expected_company_guid", GUID):
        c = _CmpClient(CMP_ONE).get_company_info()
    assert c["name"] == COMPANY and c["guid"] == GUID and c["companies"] == [COMPANY] and not c.get("error")


def test_R9_wrong_guid_multiple_companies_and_missing_guid_are_refused():
    with patch.object(S.settings, "expected_company_guid", "OTHER-GUID"):
        assert _CmpClient(CMP_ONE).get_company_info()["error"] == "WRONG_COMPANY"
    two = CMP_ONE.replace("</ENVELOPE>", '<COMPANY NAME="Other"><NAME>Other</NAME><GUID>X</GUID></COMPANY></ENVELOPE>')
    with patch.object(S.settings, "expected_company_guid", GUID):
        assert _CmpClient(two).get_company_info()["error"] == "MULTIPLE_COMPANIES"
    no_guid = CMP_ONE.replace(f"<GUID>{GUID}</GUID>", "")
    with patch.object(S.settings, "expected_company_guid", None):
        c = _CmpClient(no_guid).get_company_info()
    assert c["error"] == "NO_COMPANY_GUID" and c["guid"] is None, "no GUID is ever invented"


def test_R9_run_sync_does_not_sync_on_a_company_error(tmp_path):
    class T:
        def get_company_info(self):
            return {"error": "MULTIPLE_COMPANIES", "name": None, "guid": None, "companies": ["A", "B"]}
    src = FakeSource({date(2026, 4, 1): [_vp("A", 101)]})
    eng = _engine(tmp_path, src, RecordingBackend())
    eng.tally = T()
    assert eng.run_sync()["status"] == "MULTIPLE_COMPANIES"
    assert src.calls == []


# ============================================================ R10 - India time / R12 - .env BOM

def test_R10_today_is_the_indian_date_and_fy_boundaries_follow_it():
    utc = datetime(2026, 11, 17, 21, 44, tzinfo=timezone.utc)  # 03:14 IST on 18 Nov
    assert utc.astimezone(F.IST).date() == date(2026, 11, 18)
    boundary = datetime(2027, 3, 31, 18, 31, tzinfo=timezone.utc).astimezone(F.IST).date()  # 00:01 IST 1 Apr
    assert boundary == date(2027, 4, 1) and F.fy_containing(boundary).label == "2027-28"
    assert E.SyncEngineV2.__init__.__defaults__ is not None
    eng = E.SyncEngineV2(tally_client=object(), backend_client=object(), checkpoint_manager=object(),
                         retry_queue=object(), quarantine_store=object(), source=object())
    assert eng.today is F.ist_today


def test_R12_env_with_a_bom_keeps_its_first_key(tmp_path, monkeypatch):
    (tmp_path / ".env").write_bytes("﻿AGENT_ID=abc-123\nBACKEND_URL=https://x.test\n".encode("utf-8"))
    monkeypatch.setattr(S, "BASE_DIR", tmp_path)
    monkeypatch.delenv("AGENT_ID", raising=False)
    monkeypatch.delenv("BACKEND_URL", raising=False)
    cfg = S.SyncAgentSettings.load()
    assert cfg.agent_id == "abc-123" and cfg.backend_url == "https://x.test"


# ============================================================ FY configuration

def test_fy_contexts_live_names_preserve_production_state_and_history_is_disjoint():
    ctx = F.build_contexts("2024-25,2025-26,2026-27", "2026-04-01", "2025-26", date(2026, 11, 18))
    live, (h,) = ctx["live"], ctx["historical"]
    assert (live.cp_vouchers, live.cp_manifest, live.cp_balances, live.cp_debtors, live.quarantine_entity,
            live.batch_type, live.state_file) == ("vouchers_v2", "manifest_v2", "balances_v2", "debtors_v2", "vouchers",
                                                  "vouchers", "initial_load_v2.json")
    names_live = {live.cp_vouchers, live.cp_manifest, live.cp_balances, live.cp_debtors, live.cp_manifest_count,
                  live.quarantine_entity, live.state_file}
    names_hist = {h.cp_vouchers, h.cp_manifest, h.cp_balances, h.cp_debtors, h.cp_manifest_count,
                  h.quarantine_entity, h.state_file}
    assert not names_live & names_hist and h.cp_vouchers == "vouchers_v2@2025-26"


def test_fy_config_refuses_to_guess():
    with pytest.raises(F.FyConfigError):  # 1 Apr 2027 without the year-end procedure
        F.build_contexts("2024-25,2025-26,2026-27", "2026-04-01", "", date(2027, 4, 1))
    with pytest.raises(F.FyConfigError):  # opening anchor would move
        F.build_contexts("2025-26,2026-27", "2025-04-01", "", date(2026, 11, 18))
    with pytest.raises(F.FyConfigError):  # history FY not configured
        F.build_contexts("2025-26,2026-27", "2026-04-01", "2024-25", date(2026, 11, 18))
    with pytest.raises(F.FyConfigError):  # the live FY is not history
        F.build_contexts("2025-26,2026-27", "2026-04-01", "2026-27", date(2026, 11, 18))
    with pytest.raises(F.FyConfigError):
        F.parse_fy("2025-27")
    assert F.build_contexts("2024-25,2025-26,2026-27", "2026-04-01", "", date(2026, 11, 18))["historical"] == []
    assert S.SyncAgentSettings().history_upload == "", "historical upload is disabled by default"


# ============================================================ R13 / R14 - historical isolation, duplicates

def test_R13_historical_rejection_never_caps_the_live_checkpoint(tmp_path):
    db = tmp_path / "s.db"
    live = _engine(tmp_path, FakeSource({date(2026, 4, 1): [_vp("L", 121300)]}), RecordingBackend())
    live.masters = _masters()
    live.checkpoints = CheckpointManager(db); live.quarantine = QuarantineStore(db)
    live.checkpoints.update_checkpoint(E.CP_VOUCHERS, alter_id=121240)
    hist = _hist_engine(tmp_path, FakeSource({date(2025, 6, 1): [_vp("H", 500, "2025-06-01")]}),
                        RecordingBackend(fail_guids={"H"}), db=db)
    hist.masters = _masters()
    hist.checkpoints.update_checkpoint("vouchers_v2@2025-26", alter_id=400, records_count=1)  # 2.2.1: a real checkpoint
    r = hist.incremental_vouchers(GUID)
    assert r["failed"] == 1 and hist.quarantine.count_unresolved("vouchers@2025-26") == 1
    assert hist.quarantine.count_unresolved("vouchers") == 0
    assert live.incremental_vouchers(GUID)["checkpoint"] == 121300, "the live FY advances regardless"
    # 3.0: the rejected voucher is quarantined for retry in its own FY; it caps nothing, in its own row
    assert hist.checkpoints.get_checkpoint("vouchers_v2@2025-26")["last_alter_id"] == 500
    assert live.checkpoints.get_checkpoint(E.CP_VOUCHERS)["last_alter_id"] == 121300


def test_R13_historical_fy_never_uploads_ledger_or_bills_snapshots(tmp_path):
    hist = _hist_engine(tmp_path, FakeSource({}), RecordingBackend())
    with pytest.raises(RuntimeError):
        hist.ledger_snapshot(GUID)
    with pytest.raises(RuntimeError):
        hist.bills_snapshot(GUID)


def test_R13_historical_load_is_bounded_per_cycle_resumable_and_skips_snapshots(tmp_path, monkeypatch):
    monkeypatch.setattr(S.settings, "history_days_per_cycle", 10)
    days = {date(2025, 4, 1): [_vp("A", 10, "2025-04-01")], date(2025, 4, 25): [_vp("B", 20, "2025-04-25")]}
    src, be = FakeSource(days), RecordingBackend()
    hist = _hist_engine(tmp_path, src, be, today=date(2025, 4, 30))
    r1 = hist.historical_step(GUID)
    assert r1["status"] == "LOADING" and r1["vouchers"]["days"] == 10
    assert not [c for c in be.calls if c[0] in ("ledgers", "bills")], "no snapshot for a historical FY"
    hist.historical_step(GUID); r3 = hist.historical_step(GUID)
    assert r3["status"] == "LOADED"
    assert len([c for c in src.calls if c[0] == "day"]) == 30, "each day read exactly once"
    assert hist.checkpoints.get_checkpoint("vouchers_v2@2025-26")["last_alter_id"] == 100
    assert not hist.checkpoints.get_checkpoint("vouchers_v2").get("last_successful_sync_at"), "live state untouched"
    assert hist.kv.get("initial_load:2025-26", {}).get("completed_at") and not hist.kv.get("initial_load:2026-27")


def test_R14_vouchers_dated_outside_the_fy_are_never_uploaded_under_it(tmp_path):
    src = FakeSource({date(2026, 4, 1): [_vp("IN", 101, "2026-04-01"), _vp("OUT", 102, "2026-03-31")]})
    be = RecordingBackend()
    eng = _engine(tmp_path, src, be)
    eng.masters = _masters()
    eng.checkpoints.update_checkpoint(E.CP_VOUCHERS, alter_id=100)
    r = eng.incremental_vouchers(GUID)
    # 2.2.1: month-scoped headers inside the FY never select OUT; the _in_fy guard is tested in test_2_2_1
    assert ("vouchers", ["IN"]) in be.calls and not [c for c in be.calls if c[0] == "vouchers" and "OUT" in c[1]]


def test_retry_queue_replays_a_historical_batch_into_its_own_quarantine(tmp_path):
    eng = _engine(tmp_path, FakeSource({}), RecordingBackend(fail_guids={"H"}))
    eng.retry_queue.enqueue("vouchers@2025-26", "b1", GUID, [_vp("H", 5, "2025-06-01")])
    with eng.retry_queue._connection() as c:
        c.execute("UPDATE retry_queue SET next_retry_at = '2000-01-01T00:00:00+00:00'")
        c.commit()
    eng.process_retry_queue()
    assert eng.quarantine.count_unresolved("vouchers@2025-26") == 1 and eng.quarantine.count_unresolved("vouchers") == 0


def test_counters_distinguish_extracted_validated_uploaded_accepted_rejected_queued(tmp_path):
    src = FakeSource({date(2026, 4, 1): [_vp("A", 101), _vp("B", 102)]})
    eng = _engine(tmp_path, src, RecordingBackend(fail_guids={"B"}))
    eng.masters = _masters()
    eng.checkpoints.update_checkpoint(E.CP_VOUCHERS, alter_id=100)
    eng.incremental_vouchers(GUID)
    c = eng.counters
    assert (c["extracted"], c["validated"], c["uploaded"], c["accepted"], c["rejected_backend"], c["queued"]) == (2, 2, 2, 1, 1, 0)


def test_per_debtor_reconciliation_detects_a_missing_movement(tmp_path):
    class Src(FakeSource):
        def debtor_balances(self):
            return {"shop a": {"name": "Shop A", "guid": "G-A", "opening": Decimal("-1000"), "closing": Decimal("-1500")}}
    eng = _engine(tmp_path, Src({}), RecordingBackend())
    ok = eng.reconcile_movements({"movements": {"G-A": "-500"}})
    bad = eng.reconcile_movements({"movements": {"G-A": "-200"}})
    assert ok["mismatched"] == 0 and bad["mismatched"] == 1 and bad["examples"][0]["difference"] == "-300"
    assert eng.kv.get("validation:2026-27")["mismatched"] == 1
    v = {"is_cancelled": True, "debtor_lines": [{"ledger_guid": "G-A", "amount": "-5"}]}
    st = {}
    E.SyncEngineV2._add_movements(st, [v, {**v, "is_cancelled": False, "voucher_parent": "Delivery Note"},
                                       {**v, "is_cancelled": False, "voucher_parent": "Sales"}])
    assert st["movements"] == {"G-A": "-5"}, "cancelled and non-accounting vouchers do not move balances"


# ============================================================ multi-FY orchestration

def _multi(tmp_path, monkeypatch, history_upload="2025-26", capabilities=None, hist_step=None):
    monkeypatch.setattr(S.settings, "history_upload", history_upload)
    monkeypatch.setattr(S.settings, "financial_years", "2024-25,2025-26,2026-27")
    monkeypatch.setattr(S.settings, "sync_from_date", "2026-04-01")
    backend = MagicMock()
    backend.get_capabilities.return_value = capabilities if capabilities is not None else {}
    db = tmp_path / "s.db"
    mf = MF.MultiFySync(today=lambda: date(2026, 11, 18), tally_client=object(), backend_client=backend,
                        checkpoint_manager=CheckpointManager(db), retry_queue=RetryQueue(db),
                        quarantine_store=QuarantineStore(db), data_dir=tmp_path, source_factory=lambda: FakeSource({}))
    mf.live.run_sync = lambda: {"status": "COMPLETED"}
    mf.live.company_name, mf.live.company_guid = COMPANY, GUID
    for e in mf.history:
        e.historical_step = hist_step or (lambda guid, _e=e: {"status": "LOADING", "fy": _e.fy.label})
    return mf


def test_multi_fy_history_is_blocked_until_the_backend_is_history_safe(tmp_path, monkeypatch):
    called = []
    mf = _multi(tmp_path, monkeypatch, capabilities={}, hist_step=lambda g: called.append(g) or {"status": "X"})
    r = mf.run_cycle()
    assert "blocked" in r["history"] and called == []


def test_multi_fy_runs_history_when_safe_and_isolates_failures(tmp_path, monkeypatch):
    def boom(g):
        raise RuntimeError("Tally answered nonsense for 2024-25")
    mf = _multi(tmp_path, monkeypatch, history_upload="2024-25,2025-26", capabilities={"history_safe": True})
    mf.history[0].historical_step = boom
    r = mf.run_cycle()
    assert r["status"] == "COMPLETED"
    assert r["history"]["2024-25"]["status"] == "RuntimeError" and r["history"]["2025-26"]["status"] == "LOADING"


def test_multi_fy_without_history_runs_only_the_live_fy_and_config_errors_stop_cleanly(tmp_path, monkeypatch):
    mf = _multi(tmp_path, monkeypatch, history_upload="")
    assert mf.history == [] and "history" not in mf.run_cycle()
    monkeypatch.setattr(S.settings, "sync_from_date", "2025-04-01")
    bad = MF.MultiFySync(today=lambda: date(2026, 11, 18), tally_client=object(), backend_client=MagicMock(),
                         checkpoint_manager=CheckpointManager(tmp_path / "x.db"), retry_queue=RetryQueue(tmp_path / "x.db"),
                         quarantine_store=QuarantineStore(tmp_path / "x.db"), data_dir=tmp_path)
    assert bad.run_cycle()["status"] == "FY_CONFIG_ERROR"


# ============================================================ golden tests on the client's real Phase 0 XML

PHASE0 = Path(os.environ.get("PHASE0_DIR", Path(__file__).resolve().parents[2] / "release_v2" / "agent_2.2.0" /
                             "phase0_results" / "zip wala"))
needs_phase0 = pytest.mark.skipif(not PHASE0.exists(), reason="Phase 0 raw XML not available")


def _p0(name: str) -> str:
    return (PHASE0 / name).read_text(encoding="utf-8-sig")


def _p0root(name: str) -> ET.Element:
    return ET.fromstring(TallyClient()._clean_xml(_p0(name)))


@needs_phase0
@pytest.mark.parametrize("file,build", [
    ("s3_2026-27_T_headers_fullyear.request.xml",
     lambda: tx.voucher_request(tx.MANIFEST_FETCH, date_from=FY26.start, date_to=FY26.end, scope=SC26)),
    ("s6_2026-27_BillsReceivable_company.request.xml",
     lambda: tx.bills_receivable_request(date(2026, 11, 18), COMPANY, date(2024, 4, 1))),
    ("s6_2025-26_groupsummary_SundryDebtors_company.request.xml",
     lambda: tx.group_summary_request("Sundry Debtors", FY25.start, FY25.end, COMPANY)),
])
def test_G1_the_2_2_0_forms_replaced_in_2_2_1_are_no_longer_sent(file, build):
    """2.2.1: FY-wide voucher scope (B11) and untyped report dates (A3) are gone; byte identity to the requests
    proven on 18 Nov is asserted in test_2_2_1.py (G9)."""
    ours = build()
    assert ours != _p0(file).strip()
    assert "<SVTODATE>2" not in ours and "<SVFROMDATE>2" not in ours



@needs_phase0
def test_G1_debtor_scope_block_is_the_proven_one():
    proven = _p0("s2_2025-26_T_debtors.request.xml")
    block = proven[proven.index("<STATICVARIABLES>"):proven.index("</STATICVARIABLES>")]
    ours = tx.debtors_request(scope=SC25)
    assert block in ours


@needs_phase0
@pytest.mark.parametrize("fy,deb,cred,gs_d,gs_c,exp_d,exp_c", [
    ("2025-26", "s2_2025-26_T_debtors.xml", "s5_2025-26_T_creditors.xml", "s6_2025-26_groupsummary_SundryDebtors_company.xml",
     "s6_2025-26_groupsummary_SundryCreditors_company.xml", "-119271508.94", "1977006.64"),
    ("2026-27", "s2_2026-27_T_debtors.xml", "s5_2026-27_T_creditors.xml", "s6_2026-27_groupsummary_SundryDebtors_company.xml",
     "s6_2026-27_groupsummary_SundryCreditors_company.xml", "-191341588.97", "11541086.21"),
])
def test_G2_typed_balances_equal_tallys_group_summary_to_the_paisa(fy, deb, cred, gs_d, gs_c, exp_d, exp_c):
    d = X.parse_ledger_balances(_p0root(deb))
    c = X.parse_ledger_balances(_p0root(cred))
    assert sum(b["closing"] for b in d.values()) == X.parse_group_summary_net(_p0root(gs_d)) == Decimal(exp_d)
    assert sum(b["closing"] for b in c.values()) == X.parse_group_summary_net(_p0root(gs_c)) == Decimal(exp_c)


@needs_phase0
def test_G3_closing_2025_26_equals_opening_2026_27_for_every_debtor():
    a = X.parse_ledger_balances(_p0root("s2_2025-26_T_debtors.xml"))
    b = X.parse_ledger_balances(_p0root("s2_2026-27_T_debtors.xml"))
    both = [k for k in b if k in a]
    assert len(both) == 1599 and all(a[k]["closing"] == b[k]["opening"] for k in both)
    assert sum(x["opening"] for x in b.values()) == Decimal("-119271508.94"), "the production opening anchor"


@needs_phase0
def test_G4_fy_2024_25_is_genuinely_empty_not_a_failed_request():
    assert X.parse_group_summary_net(_p0root("s6_2024-25_groupsummary_SundryDebtors_company.xml")) == 0
    assert X.parse_bills_any(_p0root("s6_2024-25_BillsReceivable_company.xml")) == []
    bal = X.parse_ledger_balances(_p0root("s2_2024-25_T_debtors.xml"))
    # 1,599 real ledgers (the Phase 0 summary's "1600" counted the scalar <LEDGER>527</LEDGER> in <CMPINFO>)
    assert len(bal) == 1599 and all(b["closing_blank"] for b in bal.values())
    entries = X.parse_manifest_entries(_p0root("s3_2024-25_T_headers_fullyear.xml"))
    assert len(entries) == 3


@needs_phase0
def test_G5_the_balance_check_rejects_the_real_untyped_response_and_accepts_the_typed_one(tmp_path):
    class Src:
        def __init__(self, debtors_file):
            self.m = X.parse_masters(ET.fromstring(EMPTY), ET.fromstring(EMPTY), _p0root(debtors_file), ET.fromstring(EMPTY))

        def group_summary_net(self, group, a, b):
            return X.parse_group_summary_net(_p0root("s6_2025-26_groupsummary_SundryDebtors_company.xml" if b == FY25.end
                                                     else "s6_2026-27_groupsummary_SundryDebtors_company.xml"))
    ok = Src("s2_2026-27_T_debtors.xml")
    eng = _engine(tmp_path, ok, RecordingBackend(), today=date(2026, 11, 18))
    assert eng.check_debtor_balances(ok.m)["checked"]
    bad = Src("s2_2026-27_U_debtors.xml")  # what 2.1.2 would have uploaded
    eng.src = bad
    with pytest.raises(E.BalanceCheckFailed):
        eng.check_debtor_balances(bad.m)


@needs_phase0
def test_G6_debtor_bills_today_equal_production():
    d = X.parse_ledger_balances(_p0root("s2_2026-27_T_debtors.xml"))
    bills = X.parse_bills_any(_p0root("s6_2026-27_BillsReceivable_company.xml"), set(d))
    assert len(bills) == 2495 and sum(Decimal(b["pending_amount"]) for b in bills) == Decimal("-191846439.65")
    assert all(b.get("due_date") for b in bills)


@needs_phase0
def test_G7_voucher_counts_and_no_cross_fy_duplicates():
    sets = {fy: {g for g, _, _ in X.parse_manifest_entries(_p0root(f"s3_{fy}_T_headers_fullyear.xml"))}
            for fy in ("2024-25", "2025-26", "2026-27")}
    assert {k: len(v) for k, v in sets.items()} == {"2024-25": 3, "2025-26": 14905, "2026-27": 22753}
    assert not (sets["2024-25"] & sets["2025-26"]) and not (sets["2025-26"] & sets["2026-27"]) and not (sets["2024-25"] & sets["2026-27"])


@needs_phase0
@pytest.mark.parametrize("fy", ["2024-25", "2025-26", "2026-27"])
def test_G8_full_detail_samples_parse_with_no_rejection(fy):
    m = X.parse_masters(ET.fromstring(EMPTY), ET.fromstring(EMPTY), _p0root(f"s2_{fy}_T_debtors.xml"), ET.fromstring(EMPTY))
    good, bad = X.parse_vouchers(_p0root(f"s4_{fy}_T_full_sample.xml"), m)
    assert bad == [] and good


# ============================================================ ported from the retired 2.1.1 suite

def test_R5_a_real_checkpoint_is_not_treated_as_an_empty_completion(tmp_path):
    """STAGING's state (AlterID 121240): normal incremental cycle, no reload."""
    class T:
        def get_company_info(self):
            return {"name": COMPANY, "guid": GUID, "companies": [COMPANY]}
    src = FakeSource({date(2026, 4, 1): [_vp("A", 121241)]})
    eng = _engine(tmp_path, src, RecordingBackend())
    eng.tally = T()
    eng.checkpoints.update_checkpoint(E.CP_VOUCHERS, alter_id=121240, records_count=22989)
    eng.checkpoints.update_checkpoint(E.CP_BALANCES, records_count=1)
    eng.checkpoints.update_checkpoint(E.CP_MANIFEST, last_sync_date="2026-04-03", records_count=1)
    r = eng.run_sync()
    assert r["status"] == "COMPLETED" and "initial_load" not in r and r["vouchers"]["checkpoint"] == 121241
    assert not [c for c in src.calls if c[0] == "day"]


def test_R3_an_empty_load_leaves_an_existing_checkpoint_row_untouched(tmp_path):
    class T:
        def get_company_info(self):
            return {"name": COMPANY, "guid": GUID, "companies": [COMPANY]}
    eng = _engine(tmp_path, FakeSource({}), RecordingBackend(), today=date(2026, 4, 3))
    eng.tally = T()
    eng.checkpoints.update_checkpoint(E.CP_VOUCHERS, alter_id=0, records_count=0)  # 2.1.0 empty completion
    before = {k: eng.checkpoints.get_checkpoint(k) for k in (E.CP_VOUCHERS, E.CP_MANIFEST, E.CP_BALANCES)}
    assert eng.run_sync()["status"] == "CHECKPOINT_ZERO"
    _approve_first_load(eng)
    assert eng.run_sync()["status"] == "INITIAL_LOAD_EMPTY"
    assert {k: eng.checkpoints.get_checkpoint(k) for k in before} == before
