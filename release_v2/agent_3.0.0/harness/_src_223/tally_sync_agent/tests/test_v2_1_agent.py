"""
Agent 2.1.0: independent heartbeat, single sender, health payload (contract C2), retry queue that
never blocks or loses batches, named instances (contract C6), dry-run company guard, status.
"""
from __future__ import annotations

import json
import sqlite3
import sys
import threading
import time
from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from tally_sync_agent import main
from tally_sync_agent.config import settings as S
from tally_sync_agent.core.agent_state import AgentState, build_health, sanitize_error
from tally_sync_agent.core.backend_client import BackendAuthError, BackendServerError
from tally_sync_agent.core.checkpoint_manager import CheckpointManager
from tally_sync_agent.core.heartbeat import HeartbeatThread
from tally_sync_agent.core.quarantine_store import QuarantineStore
from tally_sync_agent.core.retry_queue import RetryQueue
from tally_sync_agent.engine import sync_engine_v2 as E
from incremental_adapter import IncrementalFromChanged  # 2.2.1 month/day incremental for 2.2.0 fakes

HEALTH_KEYS = {"instance", "agent_version", "phase", "phase_detail", "cycle_started_at", "cycle_running_seconds",
               "last_cycle_completed_at", "last_cycle_status", "last_cycle_duration_seconds", "last_success",
               "retry_queue", "quarantine", "last_error", "interval_seconds",
               "financial_years"}  # 2.2.0 (additive): per-FY status and counters


def _vp(guid, alter, d="2026-04-01"):
    return {"guid": guid, "alter_id": alter, "date": d, "voucher_type": "Sales", "voucher_parent": "Sales",
            "debtor_lines": [], "counter_lines": []}


class Recorder:
    """Backend double recording heartbeats and uploads; behaviour per call is configurable."""

    def __init__(self):
        self.heartbeats = []
        self.vouchers = []
        self.voucher_effects = []  # list of exceptions/None consumed per sync_vouchers call
        self.lock = threading.Lock()

    def heartbeat(self, **kw):
        with self.lock:
            self.heartbeats.append((time.time(), kw))

    def sync_vouchers(self, batch_id, company_guid, vouchers):
        eff = self.voucher_effects.pop(0) if self.voucher_effects else None
        if eff is not None:
            raise eff
        self.vouchers.append([v["guid"] for v in vouchers])
        return {"created_count": len(vouchers), "updated_count": 0, "retired_count": 0, "errors": []}

    def sync_ledgers(self, *a, **k):
        return {"details": {}}

    def sync_bills(self, *a, **k):
        return {"details": {}}

    def sync_manifest(self, *a, **k):
        return {"details": {}}


class SlowSource(IncrementalFromChanged):
    def __init__(self, block=0.0, vouchers=()):
        from test_v2_agent import _masters
        self.m = _masters()
        self.block = block
        self.vouchers = list(vouchers)

    def masters(self, cached=None, debtor_min_alter=0, full_debtors=False):
        return self.m

    def changed_vouchers(self, m, min_alter):
        time.sleep(self.block)  # a Tally request that takes a long time
        return [v for v in self.vouchers if v["alter_id"] > min_alter], []

    def bills(self, m, as_of):  # 2.2.1: a bill-wise debtor with a receivable has an open bill (sanity rule)
        return [{"ledger_name": "Shop A", "ledger_guid": "G-A", "bill_name": "1", "bill_date": "2026-04-01",
                 "pending_amount": "-5"}]

    def day_vouchers(self, m, d):
        return [], []

    def range_manifest(self, a, b):
        return [("G1", a.strftime("%Y%m%d"), 1)]

    def day_manifest(self, d):
        return ["G1"], 1


class Tally:
    def __init__(self, guid="CMP"):
        self.guid = guid

    def get_company_info(self):
        return {"name": "SGRG", "guid": self.guid}


def _engine(tmp_path, backend, source, state=None, today=date(2026, 4, 3)):
    db = tmp_path / "s.db"
    e = E.SyncEngineV2(tally_client=Tally(), backend_client=backend, checkpoint_manager=CheckpointManager(db),
                       retry_queue=RetryQueue(db), quarantine_store=QuarantineStore(db), data_dir=tmp_path,
                       source=source, today=lambda: today, state=state)
    e.period_start = date(2026, 4, 1)
    return e


def _steady(e):
    """Not a first run, balances and manifest not due."""
    e.checkpoints.update_checkpoint(E.CP_VOUCHERS, alter_id=100, records_count=0)
    e.checkpoints.update_checkpoint(E.CP_BALANCES, records_count=0)
    e.manifest_due = lambda: False


# ---------------------------------------------------------------------------- heartbeat independence

def test_heartbeat_keeps_ticking_while_a_tally_request_blocks(tmp_path):
    state = AgentState(instance="default", interval_seconds=300, agent_version="2.1.0")
    engine_backend, hb_backend = Recorder(), Recorder()
    e = _engine(tmp_path, engine_backend, SlowSource(block=1.2, vouchers=[_vp("A", 101)]), state=state)
    _steady(e)
    db = tmp_path / "s.db"
    hb = HeartbeatThread(state, hb_backend, CheckpointManager(db), RetryQueue(db), QuarantineStore(db),
                         interval_seconds=0.05, agent_version="2.1.0", state_file=tmp_path / "agent_state.json")
    hb.start()
    try:
        state.cycle_start()
        t0 = time.time()
        res = e.run_sync()
        t1 = time.time()
        state.cycle_end(res["status"], t1 - t0)
        time.sleep(0.15)
    finally:
        hb.stop()
        hb.join(2)
    during = [kw for ts, kw in hb_backend.heartbeats if t0 + 0.1 < ts < t1 - 0.1]
    assert res["status"] == "COMPLETED" and t1 - t0 >= 1.2
    assert len(during) >= 5, "heartbeats continued while the sync cycle was blocked in Tally"
    h = during[-1]["checkpoints"]["_health"]
    assert set(h) == HEALTH_KEYS and h["phase"] == "CYCLE" and h["cycle_running_seconds"] >= 0
    assert hb_backend.heartbeats[-1][1]["checkpoints"]["_health"]["last_cycle_status"] == "COMPLETED"
    assert hb_backend.heartbeats[-1][1]["tally_status"] == "ONLINE"
    assert json.loads((tmp_path / "agent_state.json").read_text())["health"]["phase"] == "IDLE"


def test_engine_sends_no_heartbeat_itself_when_a_state_is_attached(tmp_path):
    state = AgentState()
    be = Recorder()
    e = _engine(tmp_path, be, SlowSource(vouchers=[_vp("A", 5)]), state=state)
    e.initial_load("CMP")          # first load: per-month and per-day progress
    _steady(e)
    e.manifest_due = lambda: True  # daily manifest path too
    e.run_sync()
    assert be.heartbeats == [], "single sender: only the heartbeat thread sends in daemon mode"
    assert state.company_name == "SGRG" and state.last_success["vouchers"] and state.last_success["manifest"]
    # without a state (sync / dry-run CLI) the engine still heartbeats as before
    be2 = Recorder()
    e2 = _engine(tmp_path / "x", be2, SlowSource(vouchers=[_vp("A", 5)]))
    (tmp_path / "x").mkdir(exist_ok=True)
    _steady(e2)
    e2.run_sync()
    assert be2.heartbeats


def test_daemon_restarts_a_dead_heartbeat_thread():
    dead, alive = MagicMock(), MagicMock()
    dead.is_alive.return_value = False
    alive.is_alive.return_value = True
    clock = iter(range(0, 100000, 400))
    with patch.object(main, "SingleInstanceLock") as Lock, patch.object(main, "SyncEngineV2") as Engine, \
         patch.object(main, "_new_heartbeat", side_effect=[dead, alive]) as NewHb, patch.object(main, "time") as T:
        Lock.return_value.acquire.return_value = True
        Engine.return_value.run_sync.return_value = {"status": "COMPLETED"}
        T.time.side_effect = lambda: float(next(clock))
        main.cmd_daemon(None, max_cycles=2)
    assert NewHb.call_count == 2, "the dead thread was replaced"
    alive.start.assert_called_once()
    alive.stop.assert_called_once()


def test_tally_status_and_phases():
    s = AgentState()
    assert s.tally_status() == "STARTING"
    s.set_phase("INITIAL_LOAD", "day 2026-04-02 (2/231)")
    assert s.tally_status() == "INITIAL_LOAD"
    s.cycle_end("COMPLETED", 3.0)
    assert s.tally_status() == "ONLINE" and s.phase == "IDLE"
    s.cycle_end("TALLY_UNAVAILABLE", 1.0)
    assert s.tally_status() == "TALLY_UNAVAILABLE"


def test_last_error_is_truncated_and_never_contains_the_agent_key(tmp_path):
    s = AgentState(secrets=("SUPERSECRETKEY123",))
    s.record_error("Backend said: X-Agent-Key SUPERSECRETKEY123 invalid " + "x" * 500)
    msg = s.snapshot()["last_error"]["message"]
    assert "SUPERSECRETKEY123" not in msg and "[REDACTED]" in msg and len(msg) == 300
    assert sanitize_error("short") == "short"


def test_health_payload_matches_contract_c2(tmp_path):
    db = tmp_path / "s.db"
    rq, qs, cp = RetryQueue(db), QuarantineStore(db), CheckpointManager(db)
    cp.update_checkpoint("vouchers_v2", alter_id=5, records_count=1)
    rq.enqueue("vouchers", "b1", "CMP", [_vp("A", 1)])
    qs.add("vouchers", "G-Q", 9, "ledger unknown", {"guid": "G-Q"})
    h = build_health(AgentState(instance="STAGING", interval_seconds=300, agent_version="2.1.0"), rq, qs, cp)
    assert set(h) == HEALTH_KEYS
    assert set(h["retry_queue"]) == {"pending", "oldest_age_seconds", "max_attempts", "rejected_4xx", "last_error"}
    q = dict(h["quarantine"])
    assert q.pop("oldest_first_seen_at"), "2.2.2 (M1): when the oldest entry was first seen"
    assert q.pop("stale_over_24h") == 0, "2.2.2 (M1): entries older than 24 h"
    assert h["retry_queue"]["pending"] == 1 and q == {"unresolved": 1, "oldest_guid": "G-Q", "by_fy_entity": {"vouchers": 1}}
    assert set(h["last_success"]) == {"vouchers", "masters", "ledgers", "bills", "manifest"}
    assert h["last_success"]["vouchers"], "falls back to the checkpoint time after a restart"
    assert h["instance"] == "STAGING" and h["interval_seconds"] == 300
    json.dumps(h)  # serialisable


# ---------------------------------------------------------------------------- retry queue

def _queue(tmp_path, n):
    rq = RetryQueue(tmp_path / "s.db")
    ids = [rq.enqueue("vouchers", f"b{i}", "CMP", [_vp(f"V{i}", i)], initial_delay_seconds=0) for i in range(n)]
    return rq, ids


def _rows(rq):
    with rq._connection() as c:
        return {r["id"]: dict(r) for r in c.execute("SELECT * FROM retry_queue").fetchall()}


def test_a_rejected_batch_never_blocks_the_ones_behind_it(tmp_path):
    be = Recorder()
    e = _engine(tmp_path, be, SlowSource())
    rq, ids = _queue(tmp_path, 3)
    e.retry_queue = rq
    be.voucher_effects = [BackendServerError("Backend error 422: invalid", status=422), None, None]
    stats = e.process_retry_queue()
    rows = _rows(rq)
    assert stats["replayed"] == 2 and stats["rejected"] == 1
    assert list(rows) == [ids[0]], "the two good batches went through in the same pass"
    assert rows[ids[0]]["rejected_4xx"] == 1 and rows[ids[0]]["retry_count"] == 1, "kept, flagged, never deleted"
    h = rq.health_stats()
    assert h["pending"] == 1 and h["rejected_4xx"] == 1 and "422" in h["last_error"]


def test_three_consecutive_connection_errors_stop_the_pass_and_items_keep_their_schedule(tmp_path):
    be = Recorder()
    e = _engine(tmp_path, be, SlowSource())
    rq, ids = _queue(tmp_path, 5)
    e.retry_queue = rq
    be.voucher_effects = [BackendServerError("Could not connect", status=None)] * 5
    stats = e.process_retry_queue()
    rows = _rows(rq)
    assert stats["failed"] == 3 and stats["stopped_early"] == 1
    assert [rows[i]["retry_count"] for i in ids] == [1, 1, 1, 0, 0]
    assert all(rows[i]["rejected_4xx"] == 0 for i in ids), "connection errors are transient, not rejections"
    assert len(be.voucher_effects) == 2, "items 4 and 5 were not even attempted in the stopped pass"
    # the backend comes back: everything due is replayed
    be.voucher_effects = []
    with rq._connection() as c:
        c.execute("UPDATE retry_queue SET next_retry_at = '2000-01-01T00:00:00+00:00'")
        c.commit()
    assert e.process_retry_queue()["replayed"] == 5 and rq.count_pending() == 0


def test_auth_error_stops_the_pass_and_the_cycle_reports_auth_error(tmp_path):
    be = Recorder()
    e = _engine(tmp_path, be, SlowSource())
    _steady(e)
    rq, ids = _queue(tmp_path, 2)
    e.retry_queue = rq
    be.voucher_effects = [BackendAuthError("401")]
    res = e.run_sync()
    assert res["status"] == "AUTH_ERROR" and rq.count_pending() == 2


def test_auth_error_on_upload_is_not_queued_and_does_not_advance_the_checkpoint(tmp_path):
    be = Recorder()
    e = _engine(tmp_path, be, SlowSource(vouchers=[_vp("A", 150)]))
    _steady(e)
    be.voucher_effects = [BackendAuthError("403")]
    res = e.run_sync()
    assert res["status"] == "AUTH_ERROR"
    assert e.retry_queue.count_pending() == 0
    assert e.checkpoints.get_checkpoint(E.CP_VOUCHERS)["last_alter_id"] == 100


def test_upload_rejection_is_queued_and_flagged_immediately(tmp_path):
    be = Recorder()
    e = _engine(tmp_path, be, SlowSource(vouchers=[_vp("A", 150)]))
    _steady(e)
    be.voucher_effects = [BackendServerError("Backend error 422: bad", status=422)]
    e.run_sync()
    h = e.retry_queue.health_stats()
    assert h["pending"] == 1 and h["rejected_4xx"] == 1
    assert e.checkpoints.get_checkpoint(E.CP_VOUCHERS)["last_alter_id"] == 150, "queued durably: safe to advance"


def test_enqueue_failure_never_advances_the_checkpoint(tmp_path):
    be = Recorder()
    e = _engine(tmp_path, be, SlowSource(vouchers=[_vp("A", 150)]))
    _steady(e)
    be.voucher_effects = [BackendServerError("Could not connect", status=None)]
    e.retry_queue.enqueue = MagicMock(side_effect=sqlite3.OperationalError("disk I/O error"))
    with pytest.raises(sqlite3.OperationalError):
        e.incremental_vouchers("CMP")
    assert e.checkpoints.get_checkpoint(E.CP_VOUCHERS)["last_alter_id"] == 100, "vouchers are re-read next cycle"


def test_health_counts_match_the_queue_table(tmp_path):
    rq, ids = _queue(tmp_path, 4)
    rq.mark_failure(ids[1], "Backend error 500", rejected=False)
    rq.mark_failure(ids[1], "Backend error 500", rejected=False)
    rq.mark_failure(ids[2], "Backend error 422: x", rejected=True)
    rows = _rows(rq)
    h = rq.health_stats()
    assert h["pending"] == len(rows) == 4
    assert h["max_attempts"] == max(r["retry_count"] for r in rows.values()) == 2
    assert h["rejected_4xx"] == sum(r["rejected_4xx"] for r in rows.values()) == 1
    assert h["oldest_age_seconds"] is not None and h["oldest_age_seconds"] >= 0
    assert h["last_error"] == "Backend error 422: x"


def test_an_old_queue_database_is_migrated_in_place(tmp_path):
    db = tmp_path / "old.db"
    with sqlite3.connect(db) as c:  # the 2.0.0 table, with a pending batch
        c.execute("""CREATE TABLE retry_queue (id INTEGER PRIMARY KEY AUTOINCREMENT, batch_type TEXT NOT NULL,
                     batch_id TEXT NOT NULL, company_guid TEXT, payload_json TEXT NOT NULL, retry_count INTEGER DEFAULT 0,
                     next_retry_at TEXT NOT NULL, created_at TEXT NOT NULL, last_error TEXT)""")
        c.execute("INSERT INTO retry_queue (batch_type, batch_id, payload_json, next_retry_at, created_at) "
                  "VALUES ('vouchers','b','[]','2000-01-01T00:00:00+00:00','2026-11-01T00:00:00+00:00')")
    rq = RetryQueue(db)
    rows = _rows(rq)
    assert len(rows) == 1 and list(rows.values())[0]["rejected_4xx"] == 0
    assert rq.health_stats()["pending"] == 1
    RetryQueue(db)  # idempotent


# ---------------------------------------------------------------------------- named instances (C6)

def _cfg(name="", url="https://staging.example.test", allow=False):
    return SimpleNamespace(agent_instance_name=name, backend_url=url, allow_named_instance_on_production=allow)


def test_default_instance_keeps_the_1_2_1_mutex_name():
    c = S.instance_config(_cfg())
    assert c == {"instance": "default", "mutex": "Global\\FieldTrackTallyAgent_SingleInstance", "named": False}
    assert S.instance_config(_cfg(url=S.PRODUCTION_BACKEND_URL))["named"] is False, "production agent unaffected"


def test_named_instance_gets_its_own_mutex():
    c = S.instance_config(_cfg("staging"))
    assert c["instance"] == "STAGING" and c["mutex"] == "Global\\FieldTrackTallyAgent_SingleInstance_STAGING"


@pytest.mark.parametrize("bad", ["DEFAULT", "STAGING-1", "A" * 21, "st aging", "ÄB"])
def test_invalid_instance_names_are_refused(bad):
    with pytest.raises(S.InstanceConfigError):
        S.instance_config(_cfg(bad.upper()))


def test_named_instance_refuses_the_production_backend():
    with pytest.raises(S.InstanceConfigError):
        S.instance_config(_cfg("STAGING", url=S.PRODUCTION_BACKEND_URL + "/"))
    assert S.instance_config(_cfg("STAGING", url=S.PRODUCTION_BACKEND_URL, allow=True))["named"]


def test_daemon_refuses_a_misconfigured_instance_before_taking_any_lock(capsys):
    with patch.object(main, "settings", SimpleNamespace(agent_instance_name="STAGING", backend_url=S.PRODUCTION_BACKEND_URL,
                                                        allow_named_instance_on_production=False)), \
         patch.object(main, "SingleInstanceLock") as Lock, patch.object(main, "MultiFySync") as Engine:
        with pytest.raises(SystemExit) as ex:
            main.cmd_daemon(None)
    assert ex.value.code == 2
    Lock.assert_not_called()
    Engine.assert_not_called()
    assert "Refusing to start" in capsys.readouterr().out


@pytest.mark.skipif(sys.platform != "win32", reason="Windows named mutex")
def test_default_and_named_mutexes_can_be_held_at_the_same_time():
    from tally_sync_agent.core.single_instance import SingleInstanceLock
    suffix = f"TEST{int(time.time() * 1000) % 100000}"
    a = SingleInstanceLock(f"Local\\FieldTrackTallyAgent_SingleInstance_{suffix}A")
    b = SingleInstanceLock(f"Local\\FieldTrackTallyAgent_SingleInstance_{suffix}B")
    a2 = SingleInstanceLock(f"Local\\FieldTrackTallyAgent_SingleInstance_{suffix}A")
    try:
        assert a.acquire() and b.acquire(), "different instance names never block each other"
        assert not a2.acquire(), "the same name is still single-instance"
    finally:
        a.release(); b.release(); a2.release()


# ---------------------------------------------------------------------------- CLI

def test_dry_run_refuses_the_wrong_company(tmp_path, capsys):
    engine = MagicMock()
    # 2.2.0: company detection itself selects by GUID and reports the refusal (R9)
    engine.tally.get_company_info.return_value = {"error": "WRONG_COMPANY", "name": "Other Co", "guid": "OTHER",
                                                  "companies": ["Other Co"]}
    with patch.object(main, "SyncEngineV2", return_value=engine), \
         patch.object(main.settings, "expected_company_guid", "19a03e17-e1ab-44f2-8e7f-1bff56f20ebe"):
        with pytest.raises(SystemExit) as ex:
            main.cmd_dry_run(SimpleNamespace(out=str(tmp_path / "dry")))
    assert ex.value.code == 2
    engine.initial_load.assert_not_called()
    assert "WRONG_COMPANY" in capsys.readouterr().out


def test_status_prints_queue_and_last_daemon_health(tmp_path, capsys):
    db = tmp_path / "s.db"
    health = build_health(AgentState(instance="default", agent_version="2.1.0"), RetryQueue(db), QuarantineStore(db))
    health["last_cycle_status"] = "COMPLETED"
    state_file = tmp_path / "agent_state.json"
    state_file.write_text(json.dumps({"written_at": "2026-11-17T10:00:00+00:00", "health": health}))
    with patch.object(main, "STATE_FILE", state_file), \
         patch.object(main, "CheckpointManager", lambda: CheckpointManager(db)), \
         patch.object(main, "RetryQueue", lambda: RetryQueue(db)), \
         patch.object(main, "QuarantineStore", lambda: QuarantineStore(db)):
        main.cmd_status(None)
    out = capsys.readouterr().out
    assert "Retry Queue:" in out and "rejected_4xx=0" in out and "Last cycle:    COMPLETED" in out
    assert "Instance:" in out and S.AGENT_VERSION in out
