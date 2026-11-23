"""Agent 2.2.2 regression tests.

M1 - a quarantined voucher that is later DELETED in Tally must not cap the voucher checkpoint forever:
     an accepted manifest that no longer lists it releases it; post-dated and still-present entries stay;
     an entry older than 24 h is reported (log, heartbeat last_error, health).
M2 - validate-fy must tell real mismatches from vouchers that staff create / alter / delete while the run is
     reading: a baseline header scan before any balance read and a closing scan afterwards identify them;
     comparisons are judged on the rest; a real mismatch still FAILS; unknown ledgers give NOT VERIFIED.
"""
from __future__ import annotations

import json
import sqlite3
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from tally_sync_agent.config.fiscal import parse_fy
from tally_sync_agent.core.agent_state import build_health
from tally_sync_agent.core.checkpoint_manager import CheckpointManager
from tally_sync_agent.core.quarantine_store import QuarantineStore
from tally_sync_agent.core.retry_queue import RetryQueue
from tally_sync_agent.engine import fy_validation as V
from tally_sync_agent.engine import sync_engine_v2 as E
from tally_sync_agent.extractors import tally_xml as tx
from test_v2_agent import FakeSource, RecordingBackend, _engine, _masters, _vp

D1, D2, D3 = date(2026, 4, 1), date(2026, 4, 2), date(2026, 4, 3)


# =========================================================================================== M1


def _cp(eng):
    return eng.checkpoints.get_checkpoint(E.CP_VOUCHERS)["last_alter_id"]


def test_m1_quarantined_voucher_deleted_in_tally_is_released_and_checkpoint_recovers(tmp_path):
    src = FakeSource({D1: [_vp("A", 101), _vp("B", 102), _vp("C", 103)]})
    be = RecordingBackend(fail_guids={"B"})
    eng = _engine(tmp_path, src, be)
    eng.masters = src.m
    eng.checkpoints.update_checkpoint(E.CP_VOUCHERS, alter_id=100)

    r = eng.incremental_vouchers("CMP")
    assert r["checkpoint"] == 103 and eng.quarantine.count_unresolved("vouchers") == 1, \
        "3.0: B rejected -> quarantined for retry; the checkpoint is never capped"

    # Staff delete B in Tally; a new voucher D is entered.
    src.days[D1] = [_vp("A", 101), _vp("C", 103), _vp("D", 104)]
    r = eng.incremental_vouchers("CMP")
    assert r["checkpoint"] == 104 and be.calls[-1] == ("vouchers", ["D"]), "only D is read: no growing re-read"

    guids, _ = eng.scan_manifest()
    details = eng.upload_manifest("CMP", guids)
    assert details["quarantine_released"] == ["B"], "the accepted manifest no longer lists B -> released"
    assert eng.quarantine.count_unresolved("vouchers") == 0
    assert _cp(eng) == 104


def test_m1_quarantined_voucher_still_in_tally_is_kept(tmp_path):
    src = FakeSource({D1: [_vp("A", 101), _vp("B", 102)]})
    be = RecordingBackend(fail_guids={"B"})
    eng = _engine(tmp_path, src, be)
    eng.masters = src.m
    eng.checkpoints.update_checkpoint(E.CP_VOUCHERS, alter_id=100)
    eng.incremental_vouchers("CMP")
    guids, _ = eng.scan_manifest()
    details = eng.upload_manifest("CMP", guids)
    assert "quarantine_released" not in details
    assert eng.quarantine.count_unresolved("vouchers") == 1 and _cp(eng) == 102, \
        "still in Tally: kept for retry (reconciliation reports it missing), but never caps the checkpoint"


def test_m1_post_dated_and_undated_entries_are_not_released(tmp_path):
    src = FakeSource({D1: [_vp("A", 101)]})
    eng = _engine(tmp_path, src, RecordingBackend())   # today = 3-Apr
    q = eng.quarantine
    q.add("vouchers", "FUTURE", 150, "rejected", {"guid": "FUTURE", "date": "2026-04-20"})
    q.add("vouchers", "NODATE", 151, "rejected", {"source_reference": "NODATE"})
    q.add("vouchers", "GONE", 152, "debtor ledger 'X' has no cached details yet",
          {"source_reference": "GONE", "raw": {"date": "2026-04-02", "type": "Sales"}})
    released = eng.release_absent_quarantine({"A"})
    assert released == ["GONE"], "a parser rejection dated inside the window and absent from Tally is released"
    left = {r["source_reference"] for r in q.list_unresolved("vouchers")}
    assert left == {"FUTURE", "NODATE"}


def test_m1_rejected_manifest_releases_nothing(tmp_path):
    src = FakeSource({D1: [_vp("A", 101)]})

    class Refusing(RecordingBackend):
        def sync_manifest(self, batch_id, company_guid, guids, **kw):
            return {"details": {"error": "manifest too small"}}
    eng = _engine(tmp_path, src, Refusing())
    eng.quarantine.add("vouchers", "GONE", 120, "rejected", {"guid": "GONE", "date": "2026-04-01"})
    with pytest.raises(E.ManifestRejected):
        eng.upload_manifest("CMP", ["A"])
    assert eng.quarantine.count_unresolved("vouchers") == 1


def test_m1_other_fy_quarantine_is_untouched(tmp_path):
    src = FakeSource({D1: [_vp("A", 101)]})
    eng = _engine(tmp_path, src, RecordingBackend())
    eng.quarantine.add("vouchers:2025-26", "OLD", 50, "rejected", {"guid": "OLD", "date": "2025-06-01"})
    assert eng.release_absent_quarantine({"A"}) == []
    assert eng.quarantine.count_unresolved("vouchers:2025-26") == 1


def test_m1_stale_quarantine_is_reported(tmp_path):
    src = FakeSource({D1: [_vp("A", 101), _vp("B", 102)]})
    be = RecordingBackend(fail_guids={"B"})
    eng = _engine(tmp_path, src, be)
    eng.masters = src.m
    eng.checkpoints.update_checkpoint(E.CP_VOUCHERS, alter_id=100)
    r = eng.incremental_vouchers("CMP")
    assert r["quarantine_stale"] == 0
    old = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
    with sqlite3.connect(tmp_path / "s.db") as c:
        c.execute("UPDATE validation_quarantine SET first_seen_at = ?", (old,))
    errors = []
    eng._record_error = errors.append
    r = eng.incremental_vouchers("CMP")
    assert r["quarantine_stale"] == 1
    assert errors and "QUARANTINE_STALE" in errors[0] and "B" in errors[0]

    class _State:
        def snapshot(self):
            return {"instance": "", "agent_version": "2.2.2", "phase": "", "phase_detail": "", "cycle_started_at": None,
                    "cycle_running_seconds": None, "last_cycle_completed_at": None, "last_cycle_status": None,
                    "last_cycle_duration_seconds": None, "last_success": {}, "last_error": None, "interval_seconds": 300}
    h = build_health(_State(), eng.retry_queue, eng.quarantine)
    assert h["quarantine"]["stale_over_24h"] == 1 and h["quarantine"]["oldest_first_seen_at"] == old


# =========================================================================================== M2

COMPANY = "SGRG"


class ScriptedTally:
    """A tiny Tally for validate-fy: vouchers live in a dict and change when a scripted hook fires, exactly as when
    staff work in Tally during the run. Balances are computed from the vouchers AT THE MOMENT they are read."""

    def __init__(self, vouchers, opening):
        self.v = {g: dict(x) for g, x in vouchers.items()}
        self.opening = opening              # lower ledger name -> Decimal
        self.alter = max((x["alter"] for x in self.v.values()), default=0)
        self.m = _masters()
        self.scope = None
        self.hooks = []                     # (kind, n-th call, fn)
        self.calls = {}
        self.books_from = date(2024, 4, 1)

    # --- staff actions
    def create(self, guid, day, ledger, amount):
        self.alter += 1
        self.v[guid] = {"date": day, "ledger": ledger, "amount": Decimal(amount), "alter": self.alter}

    def alter_amount(self, guid, amount):
        self.alter += 1
        self.v[guid].update(amount=Decimal(amount), alter=self.alter)

    def delete(self, guid):
        self.v.pop(guid)

    def _fire(self, kind):
        self.calls[kind] = self.calls.get(kind, 0) + 1
        for k, n, fn in list(self.hooks):
            if k == kind and n == self.calls[kind]:
                fn()

    # --- what validate-fy calls
    def set_scope(self, s):
        self.scope = s

    def masters(self, cached=None, debtor_min_alter=0, full_debtors=False):
        return self.m

    def _bal(self):
        out = {}
        for k, name in (("shop a", "Shop A"), ("shop b", "Shop B")):
            o = self.opening.get(k, Decimal("0"))
            mv = sum((x["amount"] for x in self.v.values() if x["ledger"] == name
                      and self.scope.period_from <= x["date"] <= self.scope.period_to), Decimal("0"))
            out[k] = {"name": name, "opening": o, "closing": o + mv}
        return out

    def debtor_balances(self):
        if self.scope.period_to.year == 2026 and self.scope.period_to.month == 3:
            return {k: {"name": b["name"], "opening": Decimal("0"), "closing": self.opening.get(k, Decimal("0"))}
                    for k, b in self._bal().items()}
        r = self._bal()
        self._fire("balances")
        return r

    def creditors(self):
        return {}

    def group_summary_net(self, group, a, b):
        if group != "Sundry Debtors":
            return Decimal("0")
        if b.year == 2026 and b.month == 3:
            return sum(self.opening.values(), Decimal("0"))
        return sum((x["closing"] for x in self._bal().values()), Decimal("0"))

    def _xml(self, items):
        body = "".join(
            f"<VOUCHER VCHTYPE=\"Sales\"><GUID>{g}</GUID><DATE>{x['date'].strftime('%Y%m%d')}</DATE>"
            f"<VOUCHERTYPENAME>Sales</VOUCHERTYPENAME><VOUCHERNUMBER>{g}</VOUCHERNUMBER><ALTERID>{x['alter']}</ALTERID>"
            f"<ISCANCELLED>No</ISCANCELLED><ISOPTIONAL>No</ISOPTIONAL>"
            f"<ALLLEDGERENTRIES.LIST><LEDGERNAME>{x['ledger']}</LEDGERNAME><AMOUNT>{x['amount']}</AMOUNT></ALLLEDGERENTRIES.LIST>"
            f"<ALLLEDGERENTRIES.LIST><LEDGERNAME>Sales Account</LEDGERNAME><AMOUNT>{-x['amount']}</AMOUNT></ALLLEDGERENTRIES.LIST>"
            f"</VOUCHER>" for g, x in sorted(items))
        return ET.fromstring(f"<ENVELOPE>{body}</ENVELOPE>")

    def _root(self, req, kind):
        if kind.startswith("bills"):
            return ET.fromstring("<ENVELOPE/>")
        fetch, a, b, day = req
        if day is not None:
            items = [(g, x) for g, x in self.v.items() if x["date"] == day]
            self._fire(kind + ":" + day.isoformat())
            return self._xml(items)
        items = [(g, x) for g, x in self.v.items() if a <= x["date"] <= b]
        self._fire(kind)
        return self._xml(items)


@pytest.fixture
def requests_as_tuples(monkeypatch):
    monkeypatch.setattr(tx, "voucher_request", lambda fetch, day=None, date_from=None, date_to=None, scope=None, **k:
                        (fetch, date_from, date_to, day))
    monkeypatch.setattr(tx, "bills_receivable_request", lambda *a, **k: "bills")
    monkeypatch.setattr(tx, "bills_payable_request", lambda *a, **k: "bills")


def _tally():
    # Shop A: opening -1000, one sale of -500 on 1-Apr (closing -1500). Shop B: opening 0, one sale -200 on 2-Apr.
    return ScriptedTally({"S1": {"date": D1, "ledger": "Shop A", "amount": Decimal("-500"), "alter": 10},
                          "S2": {"date": D2, "ledger": "Shop B", "amount": Decimal("-200"), "alter": 11}},
                         {"shop a": Decimal("-1000"), "shop b": Decimal("0")})


def _run(t, prog=None):
    return V.validate_fy(t, parse_fy("2026-27"), COMPANY, D3, True, lambda *_: None, prog)


def _status(r, prefix):
    return [c["status"] for c in r["checks"] if c["check"].startswith(prefix)]


def test_m2_quiet_tally_passes_and_reports_no_change(requests_as_tuples):
    r = _run(_tally())
    assert _status(r, "full detail: same GUID set") == ["PASS"]
    assert _status(r, "per debtor") == ["PASS"]
    assert r["changed_during_run"]["vouchers"] == 0


def test_m2_voucher_created_during_the_run_is_identified_not_a_failure(requests_as_tuples):
    t = _tally()
    # After the balances are read, staff key in a sale to Shop B dated 2-Apr (that day is read later).
    t.hooks.append(("balances", 1, lambda: t.create("NEW1", D2, "Shop B", "-75")))
    r = _run(t)
    assert _status(r, "full detail: same GUID set") == ["PASS"], "the only difference is the voucher created meanwhile"
    assert _status(r, "per debtor") == ["PASS"], "Shop B's mismatch is excluded: it was touched during the run"
    cd = r["changed_during_run"]
    assert cd["vouchers"] == 1 and cd["by_change"] == {"created": 1}
    assert cd["list"][0]["guid"] == "NEW1" and cd["list"][0]["ledgers"] == ["Shop B"]
    assert r["debtor_reconciliation"]["excluded_changed_during_run"] == 1


def test_m2_2_2_1_logic_would_have_failed_this_run(requests_as_tuples):
    """The same sequence, judged without the guard (2.2.1): full detail has one GUID more than the baseline headers
    and Shop B does not reconcile - exactly the 18-Nov client symptom."""
    t = _tally()
    t.hooks.append(("balances", 1, lambda: t.create("NEW1", D2, "Shop B", "-75")))
    r = _run(t)
    assert r["voucher_full_detail"]["parsed"] == r["voucher_headers"]["unique_guids"] + 1
    assert r["debtor_reconciliation"]["mismatched"] == 1


def test_m2_voucher_created_after_its_day_was_read_is_named_by_a_re_read(requests_as_tuples):
    t = _tally()
    # 1-Apr has already been read when staff add a voucher dated 1-Apr for Shop A.
    t.hooks.append(("day:vouchers:2026-04-02", 1, lambda: t.create("LATE", D1, "Shop A", "-30")))
    r = _run(t)
    cd = r["changed_during_run"]
    assert cd["list"][0]["guid"] == "LATE" and cd["list"][0]["ledgers"] == ["Shop A"] and cd["list"][0]["number"] == "LATE"
    assert _status(r, "full detail: same GUID set") == ["PASS"] and _status(r, "per debtor") == ["PASS"]


def test_m2_voucher_altered_during_the_run(requests_as_tuples):
    t = _tally()
    # After the balances are read and before 1-Apr is read, S1's amount is changed.
    t.hooks.append(("balances", 1, lambda: t.alter_amount("S1", "-650")))
    r = _run(t)
    cd = r["changed_during_run"]
    assert cd["by_change"] == {"altered": 1} and cd["list"][0]["ledgers"] == ["Shop A"]
    assert _status(r, "per debtor") == ["PASS"], "Shop A differs only because of the alteration: excluded"


def test_m2_voucher_deleted_before_it_was_read_gives_not_verified(requests_as_tuples):
    t = _tally()
    t.hooks.append(("balances", 1, lambda: t.delete("S2")))   # deleted before 2-Apr is read: its ledger is unknown
    r = _run(t)
    cd = r["changed_during_run"]
    assert cd["by_change"] == {"deleted or re-dated out of the FY": 1} and cd["vouchers_with_unknown_ledgers"] == ["S2"]
    assert _status(r, "full detail: same GUID set") == ["PASS"]
    assert _status(r, "per debtor") == ["NOT VERIFIED"], "never a silent PASS when the touched ledger is unknown"


def test_m2_a_real_mismatch_still_fails(requests_as_tuples):
    t = _tally()
    t.opening["shop a"] = Decimal("-1000")
    real_bal = t._bal
    # Tally's balance for Shop A is wrong (e.g. an opening-balance edit) and no voucher changed: must FAIL.
    t._bal = lambda: {**real_bal(), "shop a": {**real_bal()["shop a"], "closing": Decimal("-1499")}}
    r = _run(t)
    assert r["changed_during_run"]["vouchers"] == 0
    assert _status(r, "per debtor") == ["FAIL"]


def test_m2_real_mismatch_on_an_untouched_ledger_fails_even_when_others_changed(requests_as_tuples):
    t = _tally()
    real_bal = t._bal
    t._bal = lambda: {**real_bal(), "shop a": {**real_bal()["shop a"], "closing": real_bal()["shop a"]["closing"] + 1}}
    t.hooks.append(("balances", 1, lambda: t.create("NEW1", D2, "Shop B", "-75")))
    r = _run(t)
    assert _status(r, "per debtor") == ["FAIL"], "Shop A was not touched during the run: its mismatch is real"
    assert r["debtor_reconciliation"]["mismatched_not_explained"] == 1


def test_m2_resumed_run_keeps_the_original_baseline(requests_as_tuples, tmp_path):
    t = _tally()
    prog = V._Progress(tmp_path / "validate_progress.json")

    def stop():
        raise V.TallyConnectionError("Tally closed")
    t.hooks.append(("day:vouchers:2026-04-02", 1, stop))
    with pytest.raises(V.TallyConnectionError):
        _run(t, prog)
    saved = json.loads((tmp_path / "validate_progress.json").read_text())["2026-27"]
    assert saved["baseline"]["alter_id"] == 11 and saved["next_day"] == "2026-04-02"
    t.hooks.clear()
    t.create("WHILE_STOPPED", D3, "Shop A", "-40")   # entered while the run was interrupted
    r = _run(t, V._Progress(tmp_path / "validate_progress.json"))
    cd = r["changed_during_run"]
    assert cd["baseline_alter_id"] == 11 and [c["guid"] for c in cd["list"]] == ["WHILE_STOPPED"]
    assert _status(r, "full detail: same GUID set") == ["PASS"] and _status(r, "per debtor") == ["PASS"]


def test_m2_summary_lists_the_changed_vouchers(requests_as_tuples, tmp_path):
    t = _tally()
    t.hooks.append(("balances", 1, lambda: t.create("NEW1", D2, "Shop B", "-75")))
    r = _run(t)
    r.pop("_guids")
    report = {"tool": "validate-fy 2.2.2", "upload_status": "NOTHING UPLOADED", "company": COMPANY, "result": "x",
              "financial_years": {"2026-27": r}}
    V._write(tmp_path, report)
    text = (tmp_path / "validation_summary.txt").read_text(encoding="utf-8")
    assert "changed in Tally during this run: 1 voucher(s)" in text and "created: 2026-04-02 Sales NEW1" in text
    assert "ledgers Shop B" in text
