"""Agent 2.2.3 regression tests - M4: post-dated vouchers.

The live FY's incremental reads vouchers dated up to today. A voucher entered today but dated later used to be lost:
the checkpoint moved past its AlterID and, when its date arrived, nothing returned it. 2.2.3 registers every
post-dated voucher (header-only read of tomorrow..FY end) in a durable register and uploads it on its date.
"""
from __future__ import annotations

from datetime import date

import pytest

from tally_sync_agent.core.checkpoint_manager import CheckpointManager
from tally_sync_agent.core.deferred_store import DeferredStore
from tally_sync_agent.core.quarantine_store import QuarantineStore
from tally_sync_agent.core.retry_queue import RetryQueue
from tally_sync_agent.engine import sync_engine_v2 as E
from tally_sync_agent.extractors import tally_xml as tx
from test_v2_agent import FakeSource, RecordingBackend, _engine, _vp

D1, D3 = date(2026, 4, 1), date(2026, 4, 3)
APR20, APR25 = date(2026, 4, 20), date(2026, 4, 25)


def _v(guid, alter, d, vtype="Sales", parent="Sales"):
    v = _vp(guid, alter, d.isoformat())
    v.update(voucher_type=vtype, voucher_parent=parent)
    return v


class FutureSource(FakeSource):
    """FakeSource + the 2.2.3 header-only read of tomorrow..FY end."""

    def future_headers(self, a, b, fy_end, min_alter=None):
        self.calls.append(("future", a, b, min_alter))
        return [(v["guid"], d.strftime("%Y%m%d"), v["alter_id"]) for d, vs in sorted(self.days.items())
                if a <= d <= b for v in vs if min_alter is None or v["alter_id"] > min_alter]

    def move(self, guid, new_day, new_alter):
        """Staff change a voucher's date in Tally (it gets a new AlterID)."""
        for d, vs in list(self.days.items()):
            for v in list(vs):
                if v["guid"] == guid:
                    vs.remove(v)
                    self.days.setdefault(new_day, []).append({**v, "date": new_day.isoformat(), "alter_id": new_alter})
                    return


def _uploads(be, guid):
    return sum(c[1].count(guid) for c in be.calls if c[0] == "vouchers")


def _live(tmp_path, src, be, today=D3, checkpoint=100):
    eng = _engine(tmp_path, src, be, today=today)
    eng.masters = src.m
    eng.checkpoints.update_checkpoint(E.CP_VOUCHERS, alter_id=checkpoint)
    return eng


def _cp(eng):
    return eng.checkpoints.get_checkpoint(E.CP_VOUCHERS)["last_alter_id"]


# --------------------------------------------------------------------------------- core lifecycle


def test_post_dated_receipt_is_held_then_uploaded_once_on_its_date(tmp_path):
    src = FutureSource({D1: [_v("A", 101, D1)], APR20: [_v("PDC", 102, APR20, "BANK RECEIPT", "Receipt")]})
    be = RecordingBackend()
    eng = _live(tmp_path, src, be)

    r = eng.incremental_vouchers("CMP")
    assert _uploads(be, "A") == 1 and _uploads(be, "PDC") == 0, "a post-dated receipt is never uploaded early"
    assert r["post_dated"] == {"registered": 1, "due": 0, "uploaded": 0, "no_longer_on_date": 0, "pending": 1}
    assert _cp(eng) == 102, "the checkpoint may move past it: the register brings it in"

    for _ in range(3):  # quiet days: nothing re-uploaded, the register keeps it
        eng.incremental_vouchers("CMP")
    assert _uploads(be, "PDC") == 0 and eng.deferred.count("2026-27") == 1

    eng.today = lambda: APR20
    r = eng.incremental_vouchers("CMP")
    assert _uploads(be, "PDC") == 1 and r["post_dated"]["uploaded"] == 1 and r["post_dated"]["pending"] == 0
    eng.incremental_vouchers("CMP")
    eng.today = lambda: APR25
    eng.incremental_vouchers("CMP")
    assert _uploads(be, "PDC") == 1, "uploaded exactly once"
    assert _uploads(be, "A") == 1


@pytest.mark.parametrize("vtype,parent", [
    ("Sales", "Sales"), ("Oppo", "Sales"), ("BANK RECEIPT", "Receipt"), ("Receipt", "Receipt"),
    ("Credit Note", "Credit Note"), ("Debit Note", "Debit Note"), ("Journal", "Journal"),
])
def test_every_voucher_type_is_held_and_uploaded_on_its_date(tmp_path, vtype, parent):
    src = FutureSource({D1: [_v("A", 101, D1)], APR20: [_v("P", 103, APR20, vtype, parent)]})
    be = RecordingBackend()
    eng = _live(tmp_path, src, be)
    eng.incremental_vouchers("CMP")
    assert _uploads(be, "P") == 0
    eng.today = lambda: date(2026, 4, 19)
    eng.incremental_vouchers("CMP")
    assert _uploads(be, "P") == 0, "the day before its date: still held"
    eng.today = lambda: APR20
    eng.incremental_vouchers("CMP")
    eng.incremental_vouchers("CMP")
    assert _uploads(be, "P") == 1


def test_first_load_registers_post_dated_vouchers_older_than_m0(tmp_path):
    # A post-dated voucher entered before the first load (AlterID 50, below the pre-scan's M0 = 100).
    src = FutureSource({D1: [_v("A", 10, D1)], D3: [_v("C", 30, D3)], APR25: [_v("OLDPDC", 50, APR25, "BANK RECEIPT", "Receipt")]})
    be = RecordingBackend()
    eng = _engine(tmp_path, src, be, today=D3)
    rep = eng.initial_load("CMP")
    assert rep["post_dated_registered"] == 1 and _uploads(be, "OLDPDC") == 0
    assert _cp(eng) == 100 and eng.deferred.scanned("2026-27")
    eng.today = lambda: APR25
    eng.masters = src.m
    eng.incremental_vouchers("CMP")
    assert _uploads(be, "OLDPDC") == 1, "M0 > its AlterID, yet it is uploaded on its date"


def test_upgrade_catch_up_reads_all_post_dated_once(tmp_path):
    """An agent upgraded from 2.2.1/2.2.2 with a valid checkpoint: post-dated vouchers entered earlier (AlterID below
    the checkpoint) are found by a one-time scan without the AlterID filter; later cycles use the filter."""
    src = FutureSource({D1: [_v("A", 101, D1)], APR20: [_v("EARLY", 90, APR20, "Receipt", "Receipt")]})
    be = RecordingBackend()
    eng = _live(tmp_path, src, be, checkpoint=100)
    eng.incremental_vouchers("CMP")
    eng.incremental_vouchers("CMP")
    fut = [c for c in src.calls if c[0] == "future"]
    assert fut[0][3] is None and all(c[3] is not None for c in fut[1:]), "full scan once, then AlterID-filtered"
    assert fut[0][1] == date(2026, 4, 4) and fut[0][2] == date(2027, 3, 31), "tomorrow .. FY end"
    eng.today = lambda: APR20
    eng.incremental_vouchers("CMP")
    assert _uploads(be, "EARLY") == 1


# --------------------------------------------------------------------------------- changes before the date


def test_post_dated_voucher_deleted_before_its_date_is_dropped(tmp_path):
    src = FutureSource({D1: [_v("A", 101, D1)], APR20: [_v("P", 102, APR20)]})
    be = RecordingBackend()
    eng = _live(tmp_path, src, be)
    eng.incremental_vouchers("CMP")
    src.days[APR20] = []  # staff delete it
    eng.today = lambda: APR20
    r = eng.incremental_vouchers("CMP")
    assert _uploads(be, "P") == 0 and r["post_dated"]["no_longer_on_date"] == 1 and eng.deferred.count() == 0


def test_post_dated_voucher_brought_forward_to_today_is_uploaded_once(tmp_path):
    src = FutureSource({D1: [_v("A", 101, D1)], APR20: [_v("P", 102, APR20, "Receipt", "Receipt")]})
    be = RecordingBackend()
    eng = _live(tmp_path, src, be)
    eng.incremental_vouchers("CMP")
    src.move("P", D3, 105)  # re-dated to today: new AlterID -> the normal incremental reads it
    eng.incremental_vouchers("CMP")
    assert _uploads(be, "P") == 1 and eng.deferred.count() == 0
    eng.today = lambda: APR20
    eng.incremental_vouchers("CMP")
    assert _uploads(be, "P") == 1, "not uploaded again on its old date"


def test_post_dated_voucher_moved_later_follows_the_new_date(tmp_path):
    src = FutureSource({D1: [_v("A", 101, D1)], APR20: [_v("P", 102, APR20)]})
    be = RecordingBackend()
    eng = _live(tmp_path, src, be)
    eng.incremental_vouchers("CMP")
    src.move("P", APR25, 106)
    eng.incremental_vouchers("CMP")
    assert eng.deferred.list("2026-27")[0]["voucher_date"] == "2026-04-25"
    eng.today = lambda: APR20
    eng.incremental_vouchers("CMP")
    assert _uploads(be, "P") == 0, "not on 20-Apr any more"
    eng.today = lambda: APR25
    eng.incremental_vouchers("CMP")
    assert _uploads(be, "P") == 1


def test_post_dated_voucher_altered_while_waiting_keeps_one_entry(tmp_path):
    src = FutureSource({D1: [_v("A", 101, D1)], APR20: [_v("P", 102, APR20)]})
    be = RecordingBackend()
    eng = _live(tmp_path, src, be)
    eng.incremental_vouchers("CMP")
    src.days[APR20] = [_v("P", 107, APR20)]  # amount edited, same date
    eng.incremental_vouchers("CMP")
    reg = eng.deferred.list("2026-27")
    assert len(reg) == 1 and reg[0]["alter_id"] == 107
    eng.today = lambda: APR20
    eng.incremental_vouchers("CMP")
    assert _uploads(be, "P") == 1


# --------------------------------------------------------------------------------- failures and restarts


def test_rejected_on_its_date_stays_registered_and_is_retried(tmp_path):
    src = FutureSource({D1: [_v("A", 101, D1)], APR20: [_v("P", 102, APR20)]})
    be = RecordingBackend(fail_guids={"P"})
    eng = _live(tmp_path, src, be)
    eng.incremental_vouchers("CMP")
    eng.today = lambda: APR20
    r = eng.incremental_vouchers("CMP")
    assert r["post_dated"]["uploaded"] == 0 and eng.deferred.count() == 1, "rejected: kept for retry"
    assert eng.deferred.list()[0]["attempts"] == 1 and eng.quarantine.count_unresolved("vouchers") == 1
    be.fail.clear()
    eng.incremental_vouchers("CMP")
    assert eng.deferred.count() == 0 and eng.quarantine.count_unresolved("vouchers") == 0


def test_backend_down_on_its_date_goes_to_the_durable_retry_queue(tmp_path):
    src = FutureSource({D1: [_v("A", 101, D1)], APR20: [_v("P", 102, APR20)]})

    class Down(RecordingBackend):
        def sync_vouchers(self, *a, **k):
            raise ConnectionError("backend unreachable")
    eng = _live(tmp_path, src, RecordingBackend())
    eng.incremental_vouchers("CMP")
    eng.backend = Down()
    eng.today = lambda: APR20
    eng.incremental_vouchers("CMP")
    assert eng.retry_queue.count_pending() == 1, "kept durably in the retry queue"
    assert eng.deferred.count() == 0, "safe to clear: the retry queue replays it"


def test_register_survives_a_restart(tmp_path):
    src = FutureSource({D1: [_v("A", 101, D1)], APR20: [_v("P", 102, APR20)]})
    be = RecordingBackend()
    _live(tmp_path, src, be).incremental_vouchers("CMP")
    eng2 = _engine(tmp_path, src, be, today=APR20)  # agent / VM restart: same data folder
    eng2.masters = src.m
    eng2.incremental_vouchers("CMP")
    assert _uploads(be, "P") == 1


# --------------------------------------------------------------------------------- bounded requests, scope


def test_cycles_never_re_read_the_whole_fy(tmp_path):
    days = {date(2026, 4, d): [_v(f"V{d}", 100 + d, date(2026, 4, d))] for d in (1, 2, 3)}
    days[APR20] = [_v("P", 104, APR20)]
    src = FutureSource(days)
    be = RecordingBackend()
    eng = _live(tmp_path, src, be, checkpoint=103)
    eng.incremental_vouchers("CMP")  # catch-up cycle
    src.calls.clear()
    eng.incremental_vouchers("CMP")
    # The fake answers month header requests through its changed_vouchers helper ("changed"): headers only.
    assert [c for c in src.calls if c[0] == "future"] == [("future", date(2026, 4, 4), date(2027, 3, 31), 104)]
    assert not [c for c in src.calls if c[0] == "day"], "a quiet cycle reads no day in full"
    eng.today = lambda: APR20
    src.calls.clear()
    eng.incremental_vouchers("CMP")
    day_reads = [c for c in src.calls if c[0] == "day"]
    assert day_reads == [("day", APR20)], "only the due date is read in full"


def test_after_fy_end_and_historical_fy_are_not_registered(tmp_path):
    src = FutureSource({D1: [_v("A", 101, D1)], date(2027, 4, 5): [_v("NEXTFY", 102, date(2027, 4, 5))]})
    eng = _live(tmp_path, src, RecordingBackend())
    eng.incremental_vouchers("CMP")
    assert eng.deferred.count() == 0, "dated in the next FY: the next FY's own load reads it"
    eng.today = lambda: date(2027, 3, 31)  # the FY's last day: no future range left
    assert eng._future_range() is None


def test_future_headers_request_is_bounded_and_typed():
    sent = []

    class Client:
        def execute_tdl(self, xml):
            sent.append(xml)
            import xml.etree.ElementTree as ET
            return ET.fromstring("<ENVELOPE></ENVELOPE>")

    class Guard:
        def request(self, kind, fn, **k):
            return fn()
    src = E.TallyV2Source(Client(), guard=Guard())
    src.set_scope(tx.Scope(date(2026, 4, 1), date(2026, 11, 20), "SGRG SERVICES (OPC) PRIVATE LIMITED"))
    src.future_headers(date(2026, 11, 21), date(2027, 3, 31), date(2027, 3, 31), 121702)
    x = sent[-1]
    assert '<SVFROMDATE TYPE="Date">21-Nov-2026</SVFROMDATE>' in x and '<SVTODATE TYPE="Date">31-Mar-2027</SVTODATE>' in x
    assert "$$Number:$AlterId &gt; 121702" in x and "<TALLYREQUEST>Export</TALLYREQUEST>" in x
    assert "ALLLEDGERENTRIES" not in x.upper().replace("ALLLEDGERENTRIES.LIST", ""), "headers only"
    with pytest.raises(ValueError):  # never reaches back into the already-synced window
        src.future_headers(date(2026, 11, 20), date(2027, 3, 31), date(2027, 3, 31))
    with pytest.raises(ValueError):  # never beyond the FY end
        src.future_headers(date(2026, 11, 21), date(2027, 4, 30), date(2027, 3, 31))


def test_deferred_store_basics(tmp_path):
    d = DeferredStore(tmp_path / "s.db")
    d.upsert("2026-27", "G", "2026-04-20", 5)
    d.upsert("2026-27", "G", "2026-04-25", 9)
    d.upsert("2026-27", "G", "2026-04-25", 7)  # an older read never lowers the AlterID
    assert d.list("2026-27")[0]["voucher_date"] == "2026-04-25" and d.list("2026-27")[0]["alter_id"] == 9
    assert d.due("2026-27", "2026-04-24") == [] and len(d.due("2026-27", "2026-04-25")) == 1
    assert d.count("2025-26") == 0 and not d.scanned("2026-27")
    d.mark_scanned("2026-27", "2027-03-31")
    assert d.scanned("2026-27") and d.remove("2026-27", ["G"]) == 1
