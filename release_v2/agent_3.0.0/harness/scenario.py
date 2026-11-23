"""The replay timeline: first load, then the recorded books in change order with simulated events and faults.

Every discrepancy the oracle reports after a cycle is classified:
  EXPECTED  - a fault is active in that cycle (Tally down / closed, backend down, corrupt checkpoint ...), or
            - the voucher was deleted / re-dated with a date older than the hourly window (31 days) since the last
              completed nightly reconciliation (by design only the nightly run sees those), or
            - it was changed in Tally WHILE the cycle was running (picked up next cycle)
  UNEXPECTED - anything else. The run fails if any unexpected discrepancy is seen, or if the final state differs.
"""
from __future__ import annotations

import json
import shutil
import sqlite3
from datetime import date, datetime, time as dtime, timedelta
from decimal import Decimal
from pathlib import Path

from runner import IST, LIVE_START, _debtor_of, _has_debtor

WINDOW_DAYS = 31


def _guid_of(item) -> set:
    if isinstance(item, str):
        return {item.split("::")[0]}
    if isinstance(item, (list, tuple)):
        out = set()
        for x in item:
            if isinstance(x, str) and len(x) > 30:
                out.add(x.split("::")[0])
            elif isinstance(x, (list, tuple)):
                out |= _guid_of(x)
        return out
    return set()


class Pending:
    def __init__(self):
        self.nightly: dict = {}      # guid -> ledgers (deleted / re-dated older than the window, until a nightly)
        self.next_cycle: dict = {}   # guid -> ledgers (changed while a cycle ran)

    def add(self, h, r, kind):
        ledgers = {n for n, _ in h.tally.moves(r)[1]}
        (self.nightly if kind == "nightly" else self.next_cycle)[r.guid] = ledgers

    def ledgers(self):
        out = set()
        for d in (self.nightly, self.next_cycle):
            for v in d.values():
                out |= v
        return out


def classify(h, rec: dict, v_detail: dict, pending: Pending, fault_cycle: bool) -> dict:
    unexpected = {}
    if rec["verify"]["equal"]:
        return unexpected
    allowed_g = set(pending.nightly) | set(pending.next_cycle)
    allowed_l = pending.ledgers()
    for k, items in v_detail.items():
        bad = []
        for it in items:
            if fault_cycle:
                continue
            if k == "outstanding":
                if it[0] in allowed_l:
                    continue
                if it[3] == "opening" and not rec.get("snapshot"):
                    continue   # Tally's FY opening moved (a FY 2025-26 change); FieldTrack takes it at the next snapshot
            elif _guid_of(it) & allowed_g:
                continue
            bad.append(it)
        if bad:
            unexpected[k] = bad
    return unexpected


# The RELEASED 2.2.3 source, extracted from release_v2/agent_2.2.3/agent-source-2.2.3.zip (checksum-verified) into
# a durable folder next to the harness (a scratchpad copy was partly deleted by a temp cleanup once).
SRC_223 = str(Path(__file__).resolve().parent / "_src_223")


def preflight_223() -> None:
    """Refuse to start a run whose version-rollback leg cannot work (fail in seconds, not after 3 hours)."""
    import subprocess
    import sys
    code = ("import sys; sys.path.insert(0, sys.argv[1]); from tally_sync_agent.config.settings import AGENT_VERSION; "
            "from tally_sync_agent.core import checkpoint_manager, quarantine_store, retry_queue, logger; "
            "from tally_sync_agent.engine import multi_fy, sync_engine_v2; assert AGENT_VERSION == '2.2.3', AGENT_VERSION")
    p = subprocess.run([sys.executable, "-I", "-c", code, SRC_223], capture_output=True, text=True)
    if p.returncode:
        raise SystemExit(f"PREFLIGHT FAILED: released 2.2.3 source not usable at {SRC_223}:\n{p.stderr[-1500:]}")
    print(f"preflight: released 2.2.3 source OK ({SRC_223})", flush=True)


def version_rollback(h, t, pending, summary, day) -> bool:
    """Day 68 21:00 .. day 69 09:00: the RELEASED 2.2.3 source runs 3 cycles on the same folder (operator rolled the
    exe back), with a post-dated and a back-dated voucher entered meanwhile (the 2.2.3 review's R5 situation). Then the
    main harness upgrades back to 3.0 (next cycle)."""
    import pickle
    import subprocess
    import sys
    from pathlib import Path
    if not Path(SRC_223, "tally_sync_agent").exists():
        h.note("version_rollback", "SKIPPED: 2.2.3 source not available", simulated=False)
        return False
    today = h.sim_today()
    r = h.pick(lambda r: r.date >= LIVE_START and t.parent_of(r).lower() == "sales" and _has_debtor(t, r))
    if r:
        n = t.clone(r.guid, today + timedelta(days=3), number="PDC-DURING-ROLLBACK", bill_name="PDC-DURING-ROLLBACK")
        h.note("post_dated", f"Sales {n.guid[-12:]} dated {n.date} entered while 2.2.3 runs (R5)")
    r = h.pick(lambda r: r.date >= LIVE_START and t.parent_of(r).lower() == "receipt" and _has_debtor(t, r))
    if r:
        n = t.clone(r.guid, today - timedelta(days=5))
        h.note("backdated", f"Receipt {n.guid[-12:]} dated {n.date} entered while 2.2.3 runs")
    h.agent = None
    saved = {k: t.__dict__.pop(k) for k in ("delete", "redate", "send_xml") if k in t.__dict__}
    pkl = h.out / "tally_for_223.pkl"
    with open(pkl, "wb") as f:
        pickle.dump(t, f, protocol=pickle.HIGHEST_PROTOCOL)
    t.__dict__.update(saved)
    times = [datetime.combine(day, dtime(21, 0), IST), datetime.combine(day + timedelta(days=1), dtime(3, 0), IST),
             datetime.combine(day + timedelta(days=1), dtime(9, 0), IST)]
    h.note("version_rollback", "agent rolled back to the released 2.2.3 source for 3 cycles (21:00, 03:00, 09:00)")
    p = subprocess.run([sys.executable, str(Path(__file__).with_name("rollback_223.py")), SRC_223, str(pkl),
                        str(h.agent_dir), str(h.data)] + [x.isoformat() for x in times], capture_output=True, text=True)
    pkl.unlink(missing_ok=True)
    if p.returncode:
        # Fail fast: without the rollback leg the run cannot prove what it claims, and every later cycle would run
        # without an agent. Stop the whole run with the reason instead of continuing for hours.
        print(p.stderr[-2000:], flush=True)
        raise SystemExit("ABORTED: the 2.2.3 rollback leg failed (see the traceback above)")
    runs = json.loads(p.stdout.strip().splitlines()[-1])
    summary["version_rollback"] = runs
    for x in runs:
        print(f"[2.2.3] {x['sim'][:16]} {x['status']} {x['vouchers']} post_dated={x['post_dated']}", flush=True)
    t.now = times[-1]
    h.cycle += 1
    v = h.last_verify = h.verify()
    rec = {"cycle": h.cycle, "sim": t.now.isoformat(), "label": "after the 2.2.3 window (2.2.3 ran)", "status": "2.2.3",
           "verify": v["summary"], "samples": v["samples"], "agent_223": runs}
    with open(h.out / "cycles.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, default=str) + "\n")
    summary["cycles"] += 1
    summary["expected_divergence" if not v["summary"]["equal"] else "equal"] += 1
    t.now = datetime.combine(day + timedelta(days=1), dtime(15, 0), IST)
    h.make_agent("day 69: upgrade back to 3.0 after the 2.2.3 window")
    return True


def run_scenario(h, start: date, end: date, hours: list):
    preflight_223()
    t = h.tally
    pending = Pending()
    summary = {"cycles": 0, "equal": 0, "expected_divergence": 0, "unexpected": 0, "unexpected_cycles": [],
               "faults": [], "statuses": {}}
    out = h.out

    def cycle(label, fault=False):
        rec = h.run_cycle(label)
        detail = h.last_verify["detail"] if not rec["verify"]["equal"] else {}
        une = classify(h, rec, detail, pending, fault)
        summary["cycles"] += 1
        summary["statuses"][rec["status"]] = summary["statuses"].get(rec["status"], 0) + 1
        if rec["verify"]["equal"]:
            summary["equal"] += 1
        elif une:
            summary["unexpected"] += 1
            summary["unexpected_cycles"].append({"cycle": rec["cycle"], "sim": rec["sim"], "label": label,
                                                 "status": rec["status"],
                                                 "items": {k: v[:5] for k, v in une.items()},
                                                 "counts": {k: len(v) for k, v in une.items()}})
        else:
            summary["expected_divergence"] += 1
        if rec.get("nightly") and rec["status"] == "COMPLETED":
            pending.nightly.clear()
            if (rec["nightly"] or {}).get("checkpoint_corrected"):
                h.fault.discard("checkpoint_ahead")
        pending.next_cycle.clear()
        print(f"[{rec['cycle']:4d}] {rec['sim'][:16]} {label:<28} {rec['status']:<20} req={rec['tally_requests']:<4} "
              f"agent={rec['agent_seconds']:>6.1f}s eq={rec['verify']['equal']!s:<5} "
              f"{'' if rec['verify']['equal'] else json.dumps({k: v for k, v in rec['verify'].items() if isinstance(v, int) and v and k not in ('tally_vouchers', 'tally_rows', 'tally_links', 'fieldtrack_index_active')})}"
              f"{' UNEXPECTED ' + json.dumps({k: len(v) for k, v in une.items()}) if une else ''}", flush=True)
        (out / "summary.json").write_text(json.dumps(summary, indent=1, default=str), encoding="utf-8")
        return rec

    def track_old(r, kind_label):
        if r is not None and (h.sim_today() - r.date).days > WINDOW_DAYS - 1:
            pending.add(h, r, "nightly")

    # wrap the tally mutators so deletions / re-dates of old vouchers are tracked as nightly-class
    orig_delete, orig_redate = t.delete, t.redate

    def delete(guid):
        r = t.recs[guid]
        track_old(r, "delete")
        return orig_delete(guid)

    def redate(guid, d):
        r = t.recs[guid]
        old = r.date
        if (h.sim_today() - old).days > WINDOW_DAYS - 1 or (h.sim_today() - d).days > WINDOW_DAYS - 1 or d > h.sim_today():
            pending.add(h, r, "nightly")
        return orig_redate(guid, d)
    t.delete, t.redate = delete, redate

    # ------------------------------------------------------------------ first load
    t.now = datetime.combine(start, dtime(0, 30), IST)
    h.make_agent("initial install")
    h.agent.live.kv.set("approve_first_load:2026-27", {"fy": "2026-27", "by": "harness-operator", "approved_at": t.now.isoformat(),
                                                        "checkpoint_status": "NEVER_LOADED"})
    h.note("operator", "approve-first-load 2026-27 (the explicit operator step)", simulated=False)
    for i in range(30):
        rec = cycle("first load", fault=True)   # FieldTrack fills up while the bounded first loads run
        hist = (rec.get("history") or {})
        if rec["status"] == "COMPLETED" and all(s in ("LOADED", "IDLE", "INCREMENTAL", None) for s in hist.values()) \
                and "LOADING" not in hist.values() and i > 0:
            break
        t.now += timedelta(minutes=5)

    # ------------------------------------------------------------------ the replay
    backup = h.out / "agent_db_backup.db"
    skip_until = None
    day = start
    n = 0
    while day <= end:
        n += 1
        d = (day - start).days
        for hr in hours:
            t.now = datetime.combine(day, dtime(hr, 0), IST)
            if skip_until and t.now <= skip_until:
                continue
            fault = False
            label = "cycle"
            # ---------------- simulated staff activity
            if hr == 15:
                h.daily_events()
                for e in h.events[-12:]:
                    if e["kind"] in ("delete", "backdated") and e["cycle"] == h.cycle:
                        pass
            if hr == 21 and day.weekday() == 0:
                h.weekly_events()
            if hr == 9 and d % 15 == 3:
                h.new_ledger_event()
            # ---------------- FY boundary (simulated; recorded late FY 2025-26 entries also arrive naturally)
            if hr == 15 and d == 5:
                r = h.pick(lambda r: r.date >= date(2026, 3, 1) and r.date <= date(2026, 3, 31)
                           and t.parent_of(r).lower() == "receipt" and _has_debtor(t, r))
                if r:
                    nr = t.clone(r.guid, date(2026, 3, 25))
                    pending.add(h, nr, "nightly")
                    h.note("fy_boundary", f"new receipt {nr.guid[-12:]} back-dated into the CLOSED FY 2025-26 (25-Mar-2026)")
            if hr == 15 and d == 6:
                r = h.pick(lambda r: r.date == date(2026, 4, 2) and _has_debtor(t, r))
                if r:
                    t.redate(r.guid, date(2026, 3, 30))
                    h.note("fy_boundary", f"{r.vtype} {r.guid[-12:]} re-dated 2-Apr-2026 -> 30-Mar-2026 (into FY 2025-26)")
            if hr == 15 and d == 7:
                r = h.pick(lambda r: r.date == date(2026, 3, 28) and _has_debtor(t, r))
                if r:
                    t.redate(r.guid, date(2026, 4, 3))
                    h.note("fy_boundary", f"{r.vtype} {r.guid[-12:]} re-dated 28-Mar-2026 -> 3-Apr-2026 (into FY 2026-27)")
            if hr == 15 and d == 8:
                r = h.pick(lambda r: r.date.year == 2025 and _has_debtor(t, r))
                if r:
                    t.edit_amount(r.guid, Decimal("1.5"))
                    h.note("fy_boundary", f"amount of FY 2025-26 {r.vtype} {r.guid[-12:]} changed: FY 2026-27 openings move")
            # ---------------- faults (simulated)
            if d == 9 and hr == 9:
                t.down = True
                fault = True
                label = "FAULT tally network down"
                h.fault.add("tally_down")
                summary["faults"].append(label)
            if d == 20 and hr == 9:
                h.backend.stop()
                h.fault.add("backend_down")
                summary["faults"].append("backend down 09:00-21:00")
            if "backend_down" in h.fault:
                fault = True
                label = "FAULT backend down"
            if d == 20 and hr == 21:
                h.backend.start()
                h.fault.discard("backend_down")
                fault = False
                label = "backend back"
            if d == 27 and hr == 21:
                t.company_loaded = False
                fault = True
                label = "FAULT company closed in Tally"
                h.fault.add("company_closed")
                summary["faults"].append(label)
            if d == 33 and hr == 3:
                cnt = {"n": 0}
                orig = t.send_xml

                def flaky(xml, _o=orig, _c=cnt):
                    if "FtpRange" in xml and "FtpAlter" not in xml:
                        _c["n"] += 1
                        if _c["n"] > 3:
                            t.down = True
                    return _o(xml)
                t.send_xml = flaky
                fault = True
                label = "FAULT tally down mid-nightly"
                h.fault.add("tally_down_mid_nightly")
                summary["faults"].append(label)
            if d in (40, 70, 100, 130, 160, 190, 220) and hr == 9:
                h.make_agent(f"day {d}: agent restart")
                label = "agent restart"
            if d == 47 and hr == 9:
                with sqlite3.connect(h.db) as c:
                    c.execute("UPDATE checkpoints SET last_alter_id='corrupt-#' WHERE entity_type='vouchers_v2'")
                h.note("checkpoint_corruption", "vouchers_v2 checkpoint overwritten with text")
                label = "checkpoint corrupted"
                fault = True   # this cycle runs the nightly rebuild; it must end equal anyway (checked below)
                summary["faults"].append(label)
            if d == 54 and hr == 9:
                with sqlite3.connect(h.db) as c:
                    c.execute("UPDATE checkpoints SET last_alter_id=last_alter_id+50000000 WHERE entity_type='vouchers_v2'")
                h.note("checkpoint_ahead", "vouchers_v2 checkpoint pushed 50,000,000 ahead (the fast path sees nothing)")
                label = "checkpoint far ahead"
                summary["faults"].append(label)
                h.fault.add("checkpoint_ahead")   # active until a nightly run corrects it
            if d == 58 and hr == 9:
                shutil.copy2(h.db, backup)
                h.note("backup", "agent database backed up (for the rollback on day 61)", simulated=False)
            if d == 61 and hr == 9:
                h.agent = None
                shutil.copy2(backup, h.db)
                h.make_agent("day 61: agent database rolled back to the day-58 backup")
                label = "state rollback"
                summary["faults"].append(label)
            if d == 75 and hr == 15:
                orig = t.send_xml
                fired = {"x": False}

                def during(xml, _o=orig, _f=fired):
                    res = _o(xml)
                    if not _f["x"] and "FtpAlter" in xml:
                        _f["x"] = True
                        r1 = h.pick(lambda r: r.date >= LIVE_START and _has_debtor(t, r))
                        if r1:
                            t.edit_amount(r1.guid, Decimal("3"))
                            pending.add(h, r1, "next")
                        r2 = h.pick(lambda r: r.date >= LIVE_START and t.parent_of(r).lower() == "sales" and _has_debtor(t, r))
                        if r2:
                            nr = t.clone(r2.guid, h.sim_today(), bill_name=f"DURING/{h.cycle}")
                            pending.add(h, nr, "next")
                        h.note("changes_during_sync", "an edit and a new voucher entered while the fast path was running")
                    return res
                t.send_xml = during
                label = "changes during sync"
            if d == 76 and hr == 3:
                orig = t.send_xml
                fired = {"n": 0}

                def during_n(xml, _o=orig, _f=fired):
                    res = _o(xml)
                    if "FtpRange" in xml and "FtpAlter" not in xml:
                        _f["n"] += 1
                        if _f["n"] == 4:   # four months already compared tonight
                            r1 = h.pick(lambda r: LIVE_START <= r.date <= date(2026, 5, 31) and _has_debtor(t, r))
                            if r1:
                                pending.add(h, r1, "nightly")
                                t.recs[r1.guid].deleted = True
                                t.recs[r1.guid].history.append("deleted during the nightly scan")
                            r2 = h.pick(lambda r: LIVE_START <= r.date <= date(2026, 5, 31) and _has_debtor(t, r))
                            if r2:
                                t.edit_amount(r2.guid, Decimal("0.5"))
                                pending.add(h, r2, "next")
                            h.note("changes_during_sync", "a deletion and an edit in months the nightly run had already compared")
                    return res
                t.send_xml = during_n
                label = "changes during nightly"
            if d == 68 and hr == 21:
                if version_rollback(h, t, pending, summary, day):
                    skip_until = datetime.combine(day + timedelta(days=1), dtime(9, 0), IST)
                    continue
            if d == 82 and hr == 3:
                h.backend.stop()
                h.fault.add("backend_down_nightly")
                fault = True
                label = "FAULT backend down at night"
                summary["faults"].append(label)

            rec = cycle(label, fault or "checkpoint_ahead" in h.fault)

            # ---------------- clear one-cycle faults / hooks
            if t.down or not t.company_loaded:
                t.down = False
                t.company_loaded = True
            for f in ("tally_down", "company_closed", "tally_down_mid_nightly", "backend_down_nightly"):
                h.fault.discard(f)
            if "send_xml" in t.__dict__:
                del t.__dict__["send_xml"]
            if d == 82 and hr == 3:
                h.backend.start()
            if d == 47 and hr == 9 and not rec["verify"]["equal"]:
                summary["unexpected_cycles"].append({"cycle": rec["cycle"], "label": "corrupt checkpoint cycle did not end equal"})
        day += timedelta(days=1)

    # ------------------------------------------------------------------ final: next night, everything settled
    t.now = datetime.combine(end + timedelta(days=1), dtime(3, 0), IST)
    rec = cycle("final nightly")
    t.now = datetime.combine(end + timedelta(days=1), dtime(9, 0), IST)
    rec = cycle("final")
    summary["final_equal"] = rec["verify"]["equal"]
    summary["final_verify"] = rec["verify"]
    summary["simulated_events"] = sum(1 for e in h.events if e["simulated"])
    by = {}
    for e in h.events:
        by[e["kind"]] = by.get(e["kind"], 0) + 1
    summary["events_by_kind"] = by
    (out / "summary.json").write_text(json.dumps(summary, indent=1, default=str), encoding="utf-8")
    print("FINAL", json.dumps({k: summary[k] for k in ("cycles", "equal", "expected_divergence", "unexpected", "final_equal")}))
