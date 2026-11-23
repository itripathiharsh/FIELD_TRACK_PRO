"""Agent 3.0 lifecycle replay harness.

  python runner.py <data_dir> [--days N] [--cycles-per-day K] [--start 2026-04-01] [--end 2026-11-18] [--seed 7]

<data_dir> holds store.pkl (build_store.py) and agent.json (setup_backend.py create). The harness:
  * starts the REAL backend (uvicorn, this branch's code) on 127.0.0.1:8765 against the isolated harness database
  * runs the REAL agent 3.0 (MultiFySync -> SyncEngineV2 -> TallyV2Source -> TallyClient) in this process; only the
    Tally transport is the ReplayTally, and time is simulated (IST date, hour, checkpoint clock, breaker clock)
  * replays the recorded SGRG books in CHANGE ORDER (entry time derived from AlterID), K cycles per simulated day
  * injects SIMULATED events (seeded) and faults on a fixed schedule
  * verifies FieldTrack = Tally after EVERY cycle (oracle.py) and writes cycles.jsonl + summary.json
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import shutil
import sqlite3
import subprocess
import sys
import time
import urllib.request
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = Path(r"F:\Field track pro v2 for test")
BACKEND = ROOT / "field track pro" / "fieldtrackpro-backend"
PORT = 8765
IST = timezone(timedelta(hours=5, minutes=30))
COMPANY_GUID = "19a03e17-e1ab-44f2-8e7f-1bff56f20ebe"
LIVE_START = date(2026, 4, 1)
HISTORY = [(date(2025, 4, 1), date(2026, 3, 31))]


# ---------------------------------------------------------------------------------------------- environment
def configure(data: Path) -> dict:
    cred = json.loads((data / "agent.json").read_text())
    env = {
        "BACKEND_URL": f"http://127.0.0.1:{PORT}", "AGENT_ID": cred["agent_id"], "AGENT_KEY": cred["agent_key"],
        "EXPECTED_COMPANY_GUID": COMPANY_GUID, "FINANCIAL_YEARS": "2024-25,2025-26,2026-27",
        "SYNC_FROM_DATE": "2026-04-01", "HISTORY_UPLOAD": "2025-26", "HISTORY_DAYS_PER_CYCLE": "31",
        "HISTORY_INCREMENTAL_MINUTES": "60", "HISTORY_MANIFEST_HOURS": "168",
        "TALLY_MIN_PAUSE_SECONDS": "0", "TALLY_DUTY_FACTOR": "0", "TALLY_LOCK_WAIT_SECONDS": "30",
        "BALANCE_INTERVAL_MINUTES": "1440", "RECONCILE_HOURLY_MINUTES": "60", "RECONCILE_HOURLY_DAYS": "31",
        "RECONCILE_NIGHTLY_HOUR": "1", "BATCH_SIZE": "100", "LOG_LEVEL": "INFO", "TALLY_URL": "http://replay-tally.invalid:9000",
        "AGENT_INSTANCE_NAME": "", "BACKEND_TIMEOUT_SECONDS": "120",
    }
    os.environ.update(env)
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(HERE))
    return cred


def backend_env() -> dict:
    sys.path.insert(0, str(HERE))
    from setup_backend import harness_env
    e = harness_env()
    return {**os.environ, "DATABASE_URL": e["DATABASE_URL"], "MIGRATION_DATABASE_URL": e["MIGRATION_DATABASE_URL"],
            "ENVIRONMENT": "dev"}


class Backend:
    def __init__(self, log: Path):
        self.proc = None
        self.log = log

    def start(self):
        if self.proc and self.proc.poll() is None:
            return
        self.proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1",
                                      "--port", str(PORT), "--log-level", "warning"], cwd=BACKEND, env=backend_env(),
                                     stdout=open(self.log, "a"), stderr=subprocess.STDOUT)
        for _ in range(120):
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{PORT}/api/v1/integrations/tally/capabilities", timeout=2)
            except urllib.error.HTTPError:
                return
            except Exception:
                time.sleep(0.5)
                continue
            return
        raise RuntimeError("backend did not start")

    def stop(self):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(20)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        self.proc = None


# ---------------------------------------------------------------------------------------------- harness
class Harness:
    def __init__(self, data: Path, out: Path, seed: int):
        self.data, self.out = data, out
        self.cred = configure(data)
        from tally_sync_agent.core import logger as L
        import logging
        lg = L.logger
        for h in list(lg.handlers):
            lg.removeHandler(h)
        fh = logging.FileHandler(out / "agent.log", encoding="utf-8")
        fh.setFormatter(L.SanitizedFormatter(fmt="[%(asctime)s] [%(levelname)s] - %(message)s"))
        lg.addHandler(fh)
        lg.setLevel(logging.INFO)
        from replay_tally import ReplayTally
        self.tally = ReplayTally(str(data / "store.pkl"), COMPANY_GUID)
        self.agent_dir = out / "agent"
        self.agent_dir.mkdir(parents=True, exist_ok=True)
        self.db = self.agent_dir / "sync_agent.db"
        self.backend = Backend(out / "backend.log")
        self.rng = random.Random(seed)
        self.events: list = []
        self.cycle = 0
        self.agent = None
        self.pending_nightly_extras: dict = {}
        self.fault: set = set()
        self.loop = asyncio.new_event_loop()
        self.conn = None
        self.ledger_seq = 0

    # ------------------------------------------------------------------ clocks
    def sim_utc(self):
        return self.tally.now.astimezone(timezone.utc)

    def sim_today(self):
        return self.tally.now.date()

    # ------------------------------------------------------------------ agent lifecycle
    def make_agent(self, why: str):
        from tally_sync_agent.core import tally_guard as G
        from tally_sync_agent.core.backend_client import BackendClient
        from tally_sync_agent.core.checkpoint_manager import CheckpointManager
        from tally_sync_agent.core.quarantine_store import QuarantineStore
        from tally_sync_agent.core.retry_queue import RetryQueue
        from tally_sync_agent.engine.multi_fy import MultiFySync
        G._GUARDS.clear()  # a new process: a new guard (its breaker state is read back from the database)
        mf = MultiFySync(state=None, today=self.sim_today, tally_client=self.tally, backend_client=BackendClient(),
                         checkpoint_manager=CheckpointManager(self.db, clock=self.sim_utc), retry_queue=RetryQueue(self.db),
                         quarantine_store=QuarantineStore(self.db), data_dir=self.agent_dir)
        assert mf.config_error is None, mf.config_error
        for e in [mf.live] + mf.history:
            e.now = self.sim_utc
            e.clock_hour = lambda: self.tally.now.hour
            guard = getattr(e.src, "guard", None)
            if guard is not None:
                guard.breaker.clock = lambda: self.sim_utc().timestamp()
        self.agent = mf
        self.note("agent", f"agent process (re)started: {why}")

    def note(self, kind: str, text: str, simulated: bool = True):
        self.events.append({"cycle": self.cycle, "at": self.tally.now.isoformat(), "kind": kind, "simulated": simulated,
                            "event": text})

    # ------------------------------------------------------------------ verification
    def verify(self) -> dict:
        import asyncpg
        from oracle import compare, expected, fieldtrack
        from setup_backend import harness_env
        if self.conn is None:
            url = harness_env()["DATABASE_URL"].replace("postgresql+asyncpg://", "postgresql://")
            self.conn = self.loop.run_until_complete(asyncpg.connect(url))
        ex = expected(self.tally, self.sim_today(), LIVE_START, HISTORY)
        ft = self.loop.run_until_complete(fieldtrack(self.conn))
        return compare(ex, ft, LIVE_START)

    # ------------------------------------------------------------------ one cycle
    def run_cycle(self, label: str = "") -> dict:
        self.cycle += 1
        n0 = len(self.tally.log)
        t0 = time.perf_counter()
        try:
            res = self.agent.run_cycle()
            status = res.get("status")
        except Exception as ex:  # the daemon loop records it and goes on
            res, status = {"error": f"{type(ex).__name__}: {ex}"}, "ERROR"
        secs = time.perf_counter() - t0
        reqs = self.tally.log[n0:]
        t1 = time.perf_counter()
        v = self.last_verify = self.verify()
        vsecs = time.perf_counter() - t1
        kinds: dict = {}
        for cid, s, b, n in reqs:
            k = kinds.setdefault(cid, [0, 0.0, 0, 0])
            k[0] += 1
            k[1] += s
            k[2] += b
            k[3] += n
        rec = {"cycle": self.cycle, "sim": self.tally.now.isoformat(), "label": label, "status": status,
               "history": {k: (h or {}).get("status") for k, h in (res.get("history") or {}).items()} if isinstance(res.get("history"), dict) else res.get("history"),
               "fault": sorted(self.fault), "agent_seconds": round(secs, 2), "verify_seconds": round(vsecs, 2),
               "tally_requests": len(reqs), "tally_bytes": sum(r[2] for r in reqs),
               "tally_vouchers_returned": sum(r[3] for r in reqs),
               "by_kind": {k: {"n": a[0], "s": round(a[1], 3), "bytes": a[2], "vouchers": a[3]} for k, a in kinds.items()},
               "vouchers": _pick(res.get("vouchers"), ("changed_headers", "days", "validated", "sent", "failed", "queued", "checkpoint")),
               "hourly": _recon(res.get("hourly")), "nightly": _recon(res.get("nightly")),
               "initial_load": bool(res.get("initial_load")), "snapshot": bool(res.get("ledgers")),
               "verify": v["summary"], "samples": v["samples"]}
        with open(self.out / "cycles.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, default=str) + "\n")
        return rec

    # ------------------------------------------------------------------ simulated events
    def pick(self, pred, upto=None):
        today = self.sim_today()
        cands = [r for r in self.tally.visible() if pred(r) and r.date <= (upto or today)]
        return self.rng.choice(cands) if cands else None

    def daily_events(self):
        """A seeded daily mix of staff actions (all SIMULATED)."""
        t, today = self.tally, self.sim_today()
        live = lambda r: r.date >= LIVE_START
        sales = lambda r: live(r) and t.parent_of(r).lower() == "sales" and _has_debtor(t, r)
        rcpt = lambda r: live(r) and t.parent_of(r).lower() == "receipt" and _has_debtor(t, r)
        for _ in range(3):
            r = self.pick(lambda r: live(r) and _has_debtor(t, r))
            if r:
                t.edit_amount(r.guid, Decimal(str(self.rng.choice((0.5, 0.9, 1.1, 1.25, 2)))))
                self.note("edit_amount", f"{r.vtype} {r.guid[-12:]} dated {r.date}")
        for _ in range(2):
            r = self.pick(live)
            if r:
                t.edit_narration(r.guid, f"edited by staff {self.rng.randint(1, 999)}")
                self.note("edit_narration", f"{r.vtype} {r.guid[-12:]}")
        r = self.pick(lambda r: live(r) and _has_debtor(t, r))
        if r:
            t.delete(r.guid)
            self.note("delete", f"{r.vtype} {r.guid[-12:]} dated {r.date} ({(today - r.date).days} days old)")
        r = self.pick(lambda r: live(r) and _has_debtor(t, r))
        if r:
            t.cancel(r.guid)
            self.note("cancel", f"{r.vtype} {r.guid[-12:]} dated {r.date}")
        r = self.pick(sales)
        if r:
            num = f"SIM/{self.cycle}/{self.rng.randint(1000, 9999)}"
            n = t.clone(r.guid, today, number=num, bill_name=num)
            self.note("new_voucher", f"Sales {n.guid[-12:]} dated today")
        r = self.pick(rcpt)
        if r and today - timedelta(days=40) >= LIVE_START:
            d = today - timedelta(days=self.rng.randint(32, 60))
            n = t.clone(r.guid, max(d, LIVE_START))
            self.note("backdated", f"Receipt {n.guid[-12:]} dated {n.date} ({(today - n.date).days} days back)")
        r = self.pick(sales)
        if r:
            d = min(today + timedelta(days=self.rng.randint(1, 20)), date(2027, 3, 31))
            n = t.clone(r.guid, d, number=f"PDC/{self.cycle}", bill_name=f"PDC/{self.cycle}")
            self.note("post_dated", f"Sales {n.guid[-12:]} dated {d} (+{(d - today).days} days)")

    def weekly_events(self):
        t, today = self.tally, self.sim_today()
        live = lambda r: r.date >= LIVE_START
        # receipt reallocation: a receipt's Agst Ref moved to another bill of the same party
        r = self.pick(lambda r: live(r) and t.parent_of(r).lower() == "receipt" and "Agst Ref" in r.xml and _has_debtor(t, r))
        if r:
            party = _debtor_of(t, r)
            bills = [b for b in _bills_of_party(t, party) if b not in r.xml]
            if bills:
                t.reallocate(r.guid, bills[0])
                self.note("receipt_reallocation", f"receipt {r.guid[-12:]} -> bill {bills[0]!r}")
        for parent in ("credit note", "debit note"):
            r = self.pick(lambda r: t.parent_of(r).lower() == parent and _has_debtor(t, r), upto=today)
            if r:
                n = t.clone(r.guid, today)
                self.note(parent.replace(" ", "_"), f"{r.vtype} {n.guid[-12:]} dated today")
        # an old (> 31 days) deletion: only the nightly reconciliation can see it
        r = self.pick(lambda r: live(r) and _has_debtor(t, r) and (today - r.date).days > 45)
        if r:
            t.delete(r.guid)
            self.note("delete_old", f"{r.vtype} {r.guid[-12:]} dated {r.date} ({(today - r.date).days} days old)")

    def new_ledger_event(self):
        t, today = self.tally, self.sim_today()
        tmpl = self.pick(lambda r: r.date >= LIVE_START and t.parent_of(r).lower() == "sales" and _has_debtor(t, r))
        if not tmpl:
            return
        party = _debtor_of(t, tmpl)
        self.ledger_seq += 1
        name = f"Harness New Outlet {self.ledger_seq} [SIM{self.ledger_seq:04d}]"
        t.add_debtor_ledger(party, name)
        n = t.clone(tmpl.guid, today, ledger=name, number=f"NEWCUST/{self.ledger_seq}",
                    bill_name=f"NEWCUST/{self.ledger_seq}")
        self.note("new_customer", f"ledger {name!r} + its first invoice {n.guid[-12:]}")


def _pick(d, keys):
    return {k: d.get(k) for k in keys} if isinstance(d, dict) else d


def _recon(d):
    if not isinstance(d, dict):
        return d
    keep = ("window", "listed", "missing", "stale", "extra", "months", "guids", "repair_fetched", "repair_days", "seconds")
    out = {k: d.get(k) for k in keep if k in d}
    if isinstance(d.get("repair"), dict):
        out["repair"] = {k: d["repair"].get(k) for k in ("requested", "days", "fetched", "rejected", "failed", "queued")}
    if "retire" in d:
        out["retire"] = d["retire"] if not isinstance(d["retire"], dict) else {k: v for k, v in d["retire"].items() if k != "quarantine_released"}
    if "checkpoint_rebuilt" in d:
        out["checkpoint_rebuilt"] = d["checkpoint_rebuilt"]
    if "checkpoint_corrected" in d:
        out["checkpoint_corrected"] = d["checkpoint_corrected"]
    return out


def _has_debtor(t, r) -> bool:
    return any(n for n, _ in t.moves(r)[1])


def _debtor_of(t, r) -> str:
    return t.moves(r)[1][0][0]


def _bills_of_party(t, party: str) -> list:
    import xml.etree.ElementTree as ET
    out = []
    for r in t.visible():
        if t.parent_of(r).lower() != "sales" or party not in [n for n, _ in t.moves(r)[1]]:
            continue
        for le in ET.fromstring(r.xml).findall("ALLLEDGERENTRIES.LIST"):
            if (le.findtext("LEDGERNAME") or "").strip().lower() == party:
                for b in le.findall("BILLALLOCATIONS.LIST"):
                    if (b.findtext("BILLTYPE") or "").strip().lower() == "new ref" and (b.findtext("NAME") or "").strip():
                        out.append(b.findtext("NAME").strip())
        if len(out) > 5:
            break
    return out


# ---------------------------------------------------------------------------------------------- scenario
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("data")
    ap.add_argument("--out")
    ap.add_argument("--start", default="2026-04-01")
    ap.add_argument("--end", default="2026-11-18")
    ap.add_argument("--hours", default="3,9,15,21")
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()
    data = Path(args.data)
    out = Path(args.out or data / f"run_{datetime.now():%Y%m%d_%H%M%S}")
    out.mkdir(parents=True, exist_ok=True)
    h = Harness(data, out, args.seed)
    from scenario import run_scenario
    try:
        h.backend.start()
        run_scenario(h, date.fromisoformat(args.start), date.fromisoformat(args.end), [int(x) for x in args.hours.split(",")])
    finally:
        h.backend.stop()
        (out / "events.json").write_text(json.dumps(h.events, indent=1, default=str), encoding="utf-8")


if __name__ == "__main__":
    main()
