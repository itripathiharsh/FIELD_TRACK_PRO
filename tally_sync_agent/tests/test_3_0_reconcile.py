"""Agent 3.0 - reconciliation. The AlterID cursor gives speed; reconciliation gives correctness.

Every test drives the real SyncEngineV2 against an in-memory Tally (headers carry the vouchers' real AlterIDs) and the
RecordingBackend of test_v2_agent, whose /sync/reconcile answers from a voucher index exactly like the backend's
(missing / stale / extra). Regressions of the 2.2.x findings under the new model: M1 (quarantine never caps), M4
(post-dated vouchers without a register), R5 (a rollback window), R6 (lost local state).
"""
from __future__ import annotations

from datetime import date

import pytest

from tally_sync_agent.config import settings as S
from tally_sync_agent.engine import sync_engine_v2 as E
from test_v2_agent import FakeSource, RecordingBackend, _engine, _vp

APR1, APR2, APR3, APR20 = date(2026, 4, 1), date(2026, 4, 2), date(2026, 4, 3), date(2026, 4, 20)
COMPANY, GUID = "SGRG", "CMP"


class Tally(FakeSource):
    """Range / day headers report each voucher's own AlterID (the real Tally does)."""

    def range_manifest(self, a, b):
        self.calls.append(("range", a, b))
        return [(v["guid"], d.strftime("%Y%m%d"), v["alter_id"]) for d, vs in sorted(self.days.items())
                if a <= d <= b for v in vs]

    def changed_headers(self, a, b, min_alter):
        self.calls.append(("headers", a, b, min_alter))
        return [(v["guid"], d.strftime("%Y%m%d"), v["alter_id"]) for d, vs in sorted(self.days.items())
                if a <= d <= b for v in vs if v["alter_id"] > min_alter]

    def changed_vouchers_on(self, m, day, min_alter):
        self.calls.append(("vday", day, min_alter))
        return [dict(v) for v in self.days.get(day, []) if v["alter_id"] > min_alter], []

    def day_vouchers(self, m, d):
        self.calls.append(("day", d))
        return [dict(v) for v in self.days.get(d, [])], []

    def get_company_info(self):
        return {"name": COMPANY, "guid": GUID, "companies": [COMPANY]}

    # staff actions -----------------------------------------------------------------------------------------
    def add(self, d, guid, alter, **kw):
        self.days.setdefault(d, []).append({**_vp(guid, alter, d.isoformat()), **kw})

    def edit(self, guid, alter, **kw):
        for vs in self.days.values():
            for v in vs:
                if v["guid"] == guid:
                    v.update(alter_id=alter, **kw)

    def delete(self, guid):
        for vs in self.days.values():
            vs[:] = [v for v in vs if v["guid"] != guid]

    def move(self, guid, new_day, alter):
        for vs in list(self.days.values()):
            for v in list(vs):
                if v["guid"] == guid:
                    vs.remove(v)
                    self.add(new_day, guid, alter)

    def guids_upto(self, end):
        return {v["guid"]: v["alter_id"] for d, vs in self.days.items() if d <= end for v in vs}


def _setup(tmp_path, days, today=APR3, checkpoint=None, fail=()):
    src, be = Tally(days), RecordingBackend(fail_guids=fail)
    eng = _engine(tmp_path, src, be, today=today)
    eng.tally = src
    eng.masters = src.m
    for vs in days.values():           # FieldTrack already holds what Tally held at the checkpoint
        be.sync_vouchers("seed", GUID, [v for v in vs if checkpoint is None or v["alter_id"] <= checkpoint])
    be.calls.clear()
    eng.checkpoints.update_checkpoint(E.CP_VOUCHERS, alter_id=checkpoint or max(
        [v["alter_id"] for vs in days.values() for v in vs] or [1]))
    eng.checkpoints.update_checkpoint(eng.fy.cp_manifest_count, alter_id=max(1, sum(len(v) for v in days.values())))
    return src, be, eng


def _equal(src, be, end):
    """FieldTrack = Tally: every voucher Tally holds up to `end` is ACTIVE at its AlterID, nothing else is ACTIVE."""
    tally = src.guids_upto(end)
    active = {g: a for g, (a, d, act) in be.index.items() if act and d <= end.isoformat()}
    return tally == active


def _uploads(be, guid):
    return sum(c[1].count(guid) for c in be.calls if c[0] == "vouchers")


# ------------------------------------------------------------------------------------------------ the three paths

def test_fast_path_is_unchanged_for_normal_changes(tmp_path):
    src, be, eng = _setup(tmp_path, {APR1: [_vp("A", 101)]})
    src.add(APR2, "B", 102)
    src.edit("A", 103)
    r = eng.incremental_vouchers(GUID)
    assert r["checkpoint"] == 103 and _equal(src, be, APR3)
    assert eng.hourly_reconcile(GUID)["missing"] == 0 and eng.hourly_reconcile(GUID)["stale"] == 0


def test_hourly_repairs_missed_new_edited_and_deleted_vouchers_without_the_fast_path(tmp_path):
    """The cursor is pushed past everything (as if a cycle had been lost): only reconciliation can see the changes."""
    src, be, eng = _setup(tmp_path, {APR1: [_vp("A", 101), _vp("B", 102), _vp("C", 103)]})
    src.add(APR2, "NEW", 110)
    src.edit("A", 111, narration="edited amount")
    src.delete("C")
    eng.checkpoints.update_checkpoint(E.CP_VOUCHERS, alter_id=999)   # the fast path will see nothing
    assert eng.incremental_vouchers(GUID)["changed_headers"] == 0
    r = eng.hourly_reconcile(GUID)
    assert (r["missing"], r["stale"], r["extra"]) == (1, 1, 1)
    assert r["repair"]["fetched"] == 2 and r["retire"]["ok"] is True
    assert _equal(src, be, APR3)
    again = eng.hourly_reconcile(GUID)
    assert (again["missing"], again["stale"], again["extra"]) == (0, 0, 0), "converged: nothing to do next hour"


def test_repair_fetches_only_the_affected_dates_narrowed_by_alter_id(tmp_path):
    days = {date(2026, 4, d): [_vp(f"V{d}", 100 + d, date(2026, 4, d).isoformat())] for d in range(1, 21)}
    src, be, eng = _setup(tmp_path, days, today=APR20)
    src.edit("V7", 200)
    eng.checkpoints.update_checkpoint(E.CP_VOUCHERS, alter_id=999)
    src.calls.clear()
    eng.hourly_reconcile(GUID)
    headers = [c for c in src.calls if c[0] == "range"]
    details = [c for c in src.calls if c[0] == "vday"]
    assert headers == [("range", APR1, APR20)], "one headers-only request for the window"
    assert details == [("vday", date(2026, 4, 7), 199)], "full details for the one affected date, AlterID >= 200 only"
    assert not [c for c in src.calls if c[0] == "day"], "no unfiltered full-day read"


def test_nightly_covers_the_whole_fy_and_retires_with_one_manifest(tmp_path):
    old = date(2026, 4, 5)
    src, be, eng = _setup(tmp_path, {old: [_vp("OLD", 101, old.isoformat())], APR20: [_vp("X", 102, APR20.isoformat())]},
                          today=date(2026, 6, 30))
    src.edit("OLD", 150)          # back-dated edit, more than 31 days ago
    src.add(old, "OLD2", 151)
    eng.checkpoints.update_checkpoint(E.CP_VOUCHERS, alter_id=999)
    h = eng.hourly_reconcile(GUID)
    assert h["window"] == "2026-05-30..2026-06-30" and h["missing"] == h["stale"] == 0, "outside the hourly window"
    n = eng.nightly_reconcile(GUID)
    assert n["missing"] == 1 and n["stale"] == 1 and n["months"] == 3
    assert len([c for c in be.calls if c[0] == "manifest"]) == 1, "one full-FY manifest"
    assert _equal(src, be, date(2026, 6, 30))
    assert eng.checkpoints.get_checkpoint("reconcile_nightly_v3")["last_sync_date"] == "2026-06-30"


# ------------------------------------------------------------------------------------------------ M4 / R5 / R6

def test_m4_post_dated_voucher_arrives_on_its_date_exactly_once_without_a_register(tmp_path):
    src, be, eng = _setup(tmp_path, {APR1: [_vp("A", 101)]})
    src.add(APR20, "PDC", 102)         # keyed in on 3-Apr, dated 20-Apr
    src.add(APR3, "B", 103)
    r = eng.incremental_vouchers(GUID)
    assert r["checkpoint"] == 103 and _uploads(be, "PDC") == 0, "not uploaded before its date"
    for today in (date(2026, 4, 10), date(2026, 4, 19)):
        eng.today = lambda t=today: t
        eng.incremental_vouchers(GUID)
        assert eng.hourly_reconcile(GUID)["missing"] == 0 and _uploads(be, "PDC") == 0
    eng.today = lambda: APR20
    eng.incremental_vouchers(GUID)
    r = eng.hourly_reconcile(GUID)
    assert r["missing"] == 1 and _uploads(be, "PDC") == 1
    eng.incremental_vouchers(GUID)
    eng.hourly_reconcile(GUID)
    assert _uploads(be, "PDC") == 1, "exactly once"
    assert _equal(src, be, APR20)


def test_m4_post_dated_voucher_moved_later_and_deleted_before_its_date(tmp_path):
    src, be, eng = _setup(tmp_path, {APR1: [_vp("A", 101)]})
    src.add(APR20, "P1", 102)
    src.add(APR20, "P2", 103)
    eng.incremental_vouchers(GUID)
    src.move("P1", date(2026, 4, 25), 104)
    src.delete("P2")
    eng.today = lambda: APR20
    eng.incremental_vouchers(GUID)
    eng.hourly_reconcile(GUID)
    assert _uploads(be, "P1") == 0 and _uploads(be, "P2") == 0
    eng.today = lambda: date(2026, 4, 25)
    eng.hourly_reconcile(GUID)
    assert _uploads(be, "P1") == 1 and _equal(src, be, date(2026, 4, 25))


def test_voucher_moved_from_today_into_the_future_is_retired_until_its_new_date(tmp_path):
    src, be, eng = _setup(tmp_path, {APR3: [_vp("A", 101, APR3.isoformat()), _vp("B", 102, APR3.isoformat())]})
    src.move("A", APR20, 103)
    eng.incremental_vouchers(GUID)
    r = eng.hourly_reconcile(GUID)
    assert r["extra"] == 1 and be.index["A"][2] is False, "no longer dated up to today: not in today's books"
    eng.today = lambda: APR20
    eng.hourly_reconcile(GUID)
    assert be.index["A"] == (103, "2026-04-20", True) and _equal(src, be, APR20)


def test_r5_a_rollback_window_loses_nothing(tmp_path):
    """2.2.3 R5: an older version ran meanwhile and advanced the checkpoint past a post-dated voucher. 3.0 keeps no
    register, so nothing can be missing from one: the hourly window finds the voucher on its date."""
    src, be, eng = _setup(tmp_path, {APR1: [_vp("A", 101)]})
    src.add(APR20, "PDC", 102)
    src.add(APR3, "X", 150)
    eng.checkpoints.update_checkpoint(E.CP_VOUCHERS, alter_id=150)   # what the older version left behind
    be.sync_vouchers("old-version", GUID, [v for v in src.days[APR3]])
    eng.today = lambda: APR20
    eng.incremental_vouchers(GUID)
    eng.hourly_reconcile(GUID)
    assert _uploads(be, "PDC") == 1 and _equal(src, be, APR20)


def test_r6_lost_local_state_is_harmless(tmp_path):
    """2.2.3 R6: losing the agent's local tables (quarantine, kv state) loses nothing: Tally and the backend index
    are compared directly."""
    src, be, eng = _setup(tmp_path, {APR1: [_vp("A", 101)]}, fail={"B"})
    src.add(APR2, "B", 102)
    eng.incremental_vouchers(GUID)
    with eng.quarantine._connection() as c:
        c.execute("DELETE FROM validation_quarantine")
        c.commit()
    with eng.kv._connection() as c:
        c.execute("DELETE FROM agent_kv")
        c.commit()
    be.fail.clear()
    eng.hourly_reconcile(GUID)
    assert _equal(src, be, APR3)


def test_m1_quarantine_is_retry_only_and_is_settled_by_reconciliation(tmp_path):
    src, be, eng = _setup(tmp_path, {APR1: [_vp("A", 101)]}, fail={"B"})
    src.add(APR2, "B", 102)
    src.add(APR2, "C", 103)
    assert eng.incremental_vouchers(GUID)["checkpoint"] == 103
    assert eng.quarantine.count_unresolved("vouchers") == 1
    src.add(APR3, "D", 104)
    assert eng.incremental_vouchers(GUID)["changed_headers"] == 1, "no growing re-read of the quarantined range"
    be.fail.clear()
    r = eng.hourly_reconcile(GUID)
    assert r["repair"]["fetched"] == 1 and eng.quarantine.count_unresolved("vouchers") == 0
    assert _equal(src, be, APR3)


# ------------------------------------------------------------------------------------------------ safety floors

def test_truncated_tally_answer_never_retires_real_vouchers(tmp_path):
    days = {APR1: [_vp(f"V{i}", 100 + i) for i in range(40)]}
    src, be, eng = _setup(tmp_path, days)
    src.range_manifest = lambda a, b: [("V0", "20260401", 100)]      # Tally answers a fraction of the window
    r = eng.hourly_reconcile(GUID)
    assert "refused" in r["retire"] and all(act for (_, _, act) in be.index.values())
    assert not [c for c in be.calls if c[0] == "manifest"]


def test_empty_window_answer_retires_nothing(tmp_path):
    src, be, eng = _setup(tmp_path, {APR1: [_vp("A", 101)]})
    src.range_manifest = lambda a, b: []
    src.day_headers = lambda d: []
    r = eng.hourly_reconcile(GUID)
    assert "skipped" in r["retire"] and be.index["A"][2] is True


def test_reconcile_refuses_nothing_on_failure_and_leaves_the_clock(tmp_path):
    src, be, eng = _setup(tmp_path, {APR1: [_vp("A", 101)]})

    def down(a, b):
        raise E.TallyConnectionError("refused")
    src.range_manifest = down
    with pytest.raises(E.TallyConnectionError):
        eng.hourly_reconcile(GUID)
    assert eng.hourly_due(), "still due next cycle"


# ------------------------------------------------------------------------------------------------ checkpoint faults

def test_checkpoint_corruption_pauses_the_fast_path_reconciles_and_rebuilds(tmp_path):
    src, be, eng = _setup(tmp_path, {APR1: [_vp("A", 101)]})
    src.add(APR2, "B", 102)
    with eng.checkpoints._connection() as c:
        c.execute("UPDATE checkpoints SET last_alter_id = 'garbage' WHERE entity_type = ?", (E.CP_VOUCHERS,))
        c.commit()
    r = eng.run_sync()
    assert r["checkpoint_status"].startswith("INVALID") and "vouchers" not in r
    assert r["nightly"]["checkpoint_rebuilt"] == 102 and r["status"] == "COMPLETED"
    assert _equal(src, be, APR3)
    src.add(APR3, "C", 103)
    r = eng.run_sync()
    assert r["vouchers"]["checkpoint"] == 103 and _equal(src, be, APR3)


def test_checkpoint_rolled_back_rereads_idempotently(tmp_path):
    src, be, eng = _setup(tmp_path, {APR1: [_vp("A", 101), _vp("B", 102)]})
    eng.checkpoints.update_checkpoint(E.CP_VOUCHERS, alter_id=50)
    r = eng.incremental_vouchers(GUID)
    assert r["checkpoint"] == 102 and _equal(src, be, APR3)
    assert len([g for g, (_, _, act) in be.index.items() if act]) == 2, "no duplicate"


def test_corrupt_checkpoint_before_any_completed_load_still_stops(tmp_path):
    src, be, eng = _setup(tmp_path, {APR1: [_vp("A", 101)]})
    eng.checkpoints.update_checkpoint(eng.fy.cp_manifest_count, alter_id=0)
    with eng.checkpoints._connection() as c:
        c.execute("UPDATE checkpoints SET last_alter_id = -5 WHERE entity_type = ?", (E.CP_VOUCHERS,))
        c.commit()
    src.calls.clear()
    assert eng.run_sync()["status"] == "CHECKPOINT_INVALID" and src.calls == []


# ------------------------------------------------------------------------------------------------ scheduling

def test_schedule_hourly_and_nightly(tmp_path, monkeypatch):
    src, be, eng = _setup(tmp_path, {APR1: [_vp("A", 101)]})
    eng.clock_hour = lambda: 0
    assert eng.hourly_due() and not eng.nightly_due(), "never run: hourly due; nightly waits for its hour"
    r = eng.run_sync()
    assert "hourly" in r and "nightly" not in r and not eng.hourly_due()
    eng.clock_hour = lambda: 2
    assert eng.nightly_due()
    r = eng.run_sync()
    assert "nightly" in r and "hourly" not in r
    assert not eng.nightly_due() and not eng.hourly_due(), "once per IST date; the nightly run covers the hour"
    eng.today = lambda: date(2026, 4, 4)
    assert eng.nightly_due(), "next IST date"


def test_first_load_starts_the_reconciliation_clocks(tmp_path):
    src = Tally({APR1: [_vp("A", 10)]})
    be = RecordingBackend()
    eng = _engine(tmp_path, src, be)
    eng.clock_hour = lambda: 5
    eng.initial_load(GUID)
    assert not eng.nightly_due() and not eng.hourly_due()


def test_historical_fy_reconciles_on_its_own_cadence(tmp_path, monkeypatch):
    from tally_sync_agent.config.fiscal import FyContext, parse_fy
    monkeypatch.setattr(S.settings, "history_manifest_hours", 168)
    src, be = Tally({date(2025, 6, 1): [_vp("H", 500, "2025-06-01")]}), RecordingBackend()
    eng = _engine(tmp_path, src, be, today=date(2026, 4, 3))
    eng.fy = FyContext(fy=parse_fy("2025-26"), legacy=False, historical=True)
    eng.period_start, eng.period_end = eng.fy.fy.start, eng.fy.fy.end
    assert eng.nightly_due(), "never run"
    r = eng.reconcile_if_due(GUID)
    assert "nightly" in r and "hourly" not in r, "a historical FY has no hourly window"
    eng.checkpoints.update_checkpoint("reconcile_nightly_v3@2025-26", last_sync_date="2026-04-03")
    assert not eng.nightly_due()


def test_checkpoint_ahead_of_tally_is_corrected_by_the_nightly_run(tmp_path):
    """A valid checkpoint far above Tally's AlterIDs hides every later change from the fast path; the nightly run
    lowers it to the highest AlterID Tally holds, and the fast path works again."""
    src, be, eng = _setup(tmp_path, {APR1: [_vp("A", 101), _vp("B", 102)]})
    eng.checkpoints.update_checkpoint(E.CP_VOUCHERS, alter_id=50_000_000)
    src.add(APR2, "OLD", 103)
    assert eng.incremental_vouchers(GUID)["changed_headers"] == 0, "hidden from the fast path"
    n = eng.nightly_reconcile(GUID)
    assert n["checkpoint_corrected"] == 103 and _equal(src, be, APR3)
    src.add(APR3, "NEW", 104)
    assert eng.incremental_vouchers(GUID)["checkpoint"] == 104, "the fast path sees changes again"
    assert _uploads(be, "NEW") == 1
