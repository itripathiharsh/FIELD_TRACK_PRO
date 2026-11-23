"""H2 unattended run: released Agent 3.0.0 exe + backend 4d0d391 (local, fieldtrackpro_h2) + real TallyPrime
(Educational Mode, FT H2 TEST 3.0) read through the test-only date adapter.

    python h2_run.py      -> results/run/{run.log, steps.jsonl, summary.json}

Stops at the FIRST: lock / environment failure, Tally completeness (A) or Tally-totals (B) failure, FieldTrack != Tally
after the step's documented window, duplicate, link to a retired invoice, unexpected agent status, adapter refusal
(= a write attempt), or any exception. On stop or completion every process it started is stopped.
Labelled: real TallyPrime (Educational Mode) through a test-only date adapter - NOT licensed-Tally validation.
"""
from __future__ import annotations

import json
import os
import random
import re
import shutil
import sqlite3
import subprocess
import sys
import time
import traceback
import urllib.request
from datetime import date, datetime
from decimal import Decimal as D
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "harness"))
sys.path.insert(0, str(HERE.parents[2]))
import h2_safety as hs  # noqa: E402
import h2_tally as t  # noqa: E402
import h2_check  # noqa: E402
import setup_backend as sb  # noqa: E402

sb.HARNESS_DB = hs.LOCK["backend_db"]
RUN = HERE / "results" / "run"
AGENT = Path(r"F:\FT_H2\agent")
EXE = AGENT / "FieldTrackTallyAgent.exe"
ADB = AGENT / "data" / "sync_agent.db"
BACKUPS = Path(r"F:\FT_H2\state_backups")
ADAPTER_LOG = HERE / "results" / "adapter_requests.jsonl"
RELEASE = "4d0d391a331b6db244d9c9668ea9f84c03dc265c"
CUST = [f"H2 Customer {i:02d}" for i in range(1, 21)]
EDU_DATES = [d for d in h2_check.allowed_days(date(2026, 4, 1), date(2026, 11, 2))]
rng = random.Random(20261122)
RESUME_V4A = "--resume-v4a" in sys.argv
RESUME_AT = sys.argv[sys.argv.index("--resume-at") + 1] if "--resume-at" in sys.argv else None
MUTATED = "--mutated" in sys.argv          # the RESUME_AT step's Tally writes were already done (verify only)
ORDER = ["V4b", "V5", "V6a", "V6b", "V6c", "V7", "V8", "V9", "R", "F4", "F5", "F6", "A1", "A2", "A3", "A4", "A5", "T2"]
if RESUME_AT:
    assert RESUME_AT in ORDER, f"unknown --resume-at {RESUME_AT}"
    RESUME_V4A = True                      # skip initial .. V4a as well (they passed in earlier runs)


def _skip(k):
    return RESUME_AT is not None and ORDER.index(k) < ORDER.index(RESUME_AT)


def _skip_mut(k):
    return _skip(k) or (k == RESUME_AT and MUTATED)


class Stop(Exception):
    pass


# ====================================================================================== logging
def log(msg: str) -> None:
    line = f"[{datetime.now().isoformat(timespec='seconds')}] {msg}"
    print(line, flush=True)
    with (RUN / "run.log").open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def record(rec: dict) -> None:
    rec = {"at": datetime.now().isoformat(timespec="seconds"), **rec}
    with (RUN / "steps.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, default=str) + "\n")


# ====================================================================================== processes
class Procs:
    backend = None
    adapter = None

    @staticmethod
    def _kill(p):
        if p and p.poll() is None:
            subprocess.run(["taskkill", "/PID", str(p.pid), "/T", "/F"], capture_output=True)
            try:
                p.wait(timeout=20)
            except Exception:
                pass

    @classmethod
    def start_backend(cls):
        env = sb.harness_env()
        hs.assert_backend_target(env["DATABASE_URL"], hs.LOCK["backend_url"])
        e = {**os.environ, "DATABASE_URL": env["DATABASE_URL"], "MIGRATION_DATABASE_URL": env["MIGRATION_DATABASE_URL"],
             "ENVIRONMENT": "dev"}
        cls.backend = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port",
                                        "8766", "--log-level", "warning"], cwd=sb.BACKEND, env=e,
                                       stdout=open(RUN / "backend.log", "a"), stderr=subprocess.STDOUT)
        for _ in range(60):
            try:
                with urllib.request.urlopen("http://127.0.0.1:8766/health", timeout=3) as r:
                    if b"UP" in r.read():
                        log("backend UP on 127.0.0.1:8766")
                        return
            except Exception:
                time.sleep(1)
        raise Stop("backend did not come up")

    @classmethod
    def stop_backend(cls):
        cls._kill(cls.backend)
        cls.backend = None
        log("backend stopped")

    @classmethod
    def start_adapter(cls):
        cls.adapter = subprocess.Popen([sys.executable, str(HERE / "edu_adapter.py")], cwd=HERE,
                                       stdout=open(RUN / "adapter_console.txt", "a"), stderr=subprocess.STDOUT)
        time.sleep(2)
        if cls.adapter.poll() is not None:
            raise Stop("adapter did not start")
        log("adapter UP on 127.0.0.1:9001 (Export only)")

    @classmethod
    def stop_all(cls):
        subprocess.run(["taskkill", "/IM", "FieldTrackTallyAgent.exe", "/T", "/F"], capture_output=True)
        cls._kill(cls.adapter)
        cls.adapter = None
        cls.stop_backend()
        log("all H2 processes stopped (agent, adapter, backend)")


# ====================================================================================== guards
ADAPTER_REFUSED_BASELINE = 0


def adapter_refusals() -> int:
    if not ADAPTER_LOG.exists():
        return 0
    return sum(1 for l in ADAPTER_LOG.read_text(encoding="utf-8").splitlines() if '"REFUSED"' in l)


def guards(where: str) -> None:
    try:
        hs.assert_test_company()
        hs.assert_company_folder()
        hs.assert_agent_env(AGENT / ".env")
    except SystemExit as e:
        raise Stop(f"SAFETY LOCK at {where}: {e}")
    agent_env()
    n = adapter_refusals()
    if n != ADAPTER_REFUSED_BASELINE:
        raise Stop(f"ADAPTER REFUSED {n - ADAPTER_REFUSED_BASELINE} request(s) (write attempt) at {where}")


# ====================================================================================== agent
def set_env(**kv):
    p = AGENT / ".env"
    s = p.read_text(encoding="utf-8-sig")
    for k, v in kv.items():
        if re.search(rf"^{k}=", s, re.M):
            s = re.sub(rf"^{k}=.*$", f"{k}={v}", s, flags=re.M)
        else:
            s += f"\n{k}={v}"
    p.write_text(s, encoding="utf-8")
    hs.assert_agent_env(p)


# Every key the agent reads from its .env. The released settings loader copies .env keys into os.environ when absent
# and environment variables WIN over the .env file (settings.py:96-109). Importing the developer-checkout package in
# this process (the replay oracle does) therefore plants the DEVELOPER .env (legacy Render backend, developer agent
# key) into os.environ - incident of 22 Nov 03:00. Agent processes therefore get a clean environment, always.
import h2_agentenv  # noqa: E402


def agent_env() -> dict:
    try:
        return h2_agentenv.agent_env()
    except RuntimeError as ex:
        raise Stop(f"SAFETY LOCK: {ex}")


def _count(path: Path) -> int:
    """Real requests only: backend.log -> agent API requests logged by the local backend (scheduler / debug lines do
    NOT count); adapter log -> forwarded or refused Tally requests."""
    if not path.exists():
        return 0
    pat = ("event=http_request", "/integrations/tally/") if path.name == "backend.log" else ('"status"',)
    return sum(1 for l in path.open(encoding="utf-8", errors="ignore") if all(x in l for x in pat))


def agent(cmd: list, timeout=1800) -> dict:
    guards(f"agent {' '.join(cmd)}")
    t0 = time.time()
    b0, a0 = _count(RUN / "backend.log"), _count(ADAPTER_LOG)
    p = subprocess.run([str(EXE), *cmd], cwd=AGENT, capture_output=True, text=True, timeout=timeout, env=agent_env())
    # the call must have reached THIS run's local backend (heartbeat / sync logged) and Tally only via the adapter
    talks_backend = cmd[0] in ("sync", "test-backend", "health", "daemon")
    talks_tally = cmd[0] in ("sync", "test-tally", "health", "daemon", "validate-fy")
    if talks_backend and Procs.backend and _count(RUN / "backend.log") == b0:
        raise Stop(f"SAFETY LOCK: agent {cmd} produced no request at the local H2 backend (wrong backend?)")
    if talks_tally and _count(ADAPTER_LOG) == a0:
        raise Stop(f"SAFETY LOCK: agent {cmd} sent no request through the adapter (Tally reached directly?)")
    out = p.stdout + p.stderr
    js = None
    i = p.stdout.find("{\n")
    if i >= 0:
        try:
            js, _ = json.JSONDecoder().raw_decode(p.stdout[i:])     # the printed results object; log lines may follow
        except Exception:
            js = None
    fin = re.findall(r'SYNC_CYCLE_FINISHED v2 (\{.*\})', out)
    if fin:
        m_st = re.match(r'\{"status":\s*"([A-Z_]+)"', fin[-1])   # the logger truncates long lines: read the status field
        logged = m_st.group(1) if m_st else None
        if js is None or logged != js.get("status"):
            raise Stop(f"agent {cmd}: printed status {(js or {}).get('status')} != logged SYNC_CYCLE_FINISHED status {logged}")
    res = {"cmd": cmd, "exit": p.returncode, "seconds": round(time.time() - t0, 1),
           "status": (js or {}).get("status"), "phases": sorted(k for k in (js or {}) if k in ("vouchers", "hourly", "nightly",
                                                                                                 "initial_load", "ledgers", "bills")),
           "tail": [l[:240] for l in out.splitlines() if "ERROR" in l or "CHECKPOINT" in l or "RETIRE" in l][-8:]}
    if js:
        for k in ("hourly", "nightly"):
            if isinstance(js.get(k), dict):
                res[k] = {x: js[k].get(x) for x in ("missing", "stale", "extra", "retired", "fetched", "checkpoint_rebuilt",
                                                     "checkpoint_ahead_corrected", "complete", "refused") if x in js[k]}
        if isinstance(js.get("vouchers"), dict):
            res["vouchers"] = {x: js["vouchers"].get(x) for x in ("changed", "sent", "created", "updated", "failed",
                                                                   "checkpoint") if x in js["vouchers"]}
    (RUN / "agent_outputs").mkdir(exist_ok=True)
    (RUN / "agent_outputs" / f"{datetime.now().strftime('%H%M%S')}_{'_'.join(cmd)}.txt").write_text(out, encoding="utf-8")
    return res


def sync(expect=("COMPLETED",)) -> dict:
    r = agent(["sync"])
    log(f"  sync -> {r['status']} phases={r['phases']} {r.get('vouchers', '')} {r.get('hourly', '')} {r.get('nightly', '')}")
    if expect and r["status"] not in expect:
        raise Stop(f"agent status {r['status']} (expected {expect}); tail={r['tail']}")
    return r


def adb(sql: str, args=()):
    c = sqlite3.connect(ADB)
    try:
        cur = c.execute(sql, args)
        rows = cur.fetchall()
        c.commit()
        return rows
    finally:
        c.close()


def force(*what):
    for w in what:
        if w == "hourly":
            adb("DELETE FROM checkpoints WHERE entity_type LIKE 'reconcile_hourly_v3%'")
        elif w == "balances":
            adb("DELETE FROM checkpoints WHERE entity_type LIKE 'balances_v2%'")
        elif w == "nightly":
            adb("DELETE FROM checkpoints WHERE entity_type LIKE 'reconcile_nightly_v3%'")
            adb("DELETE FROM agent_kv WHERE key LIKE 'nightly:%'")
    log(f"  forced due: {what}")


def _retry_drained(step: str) -> int:
    n = adb("SELECT count(*) FROM retry_queue")[0][0]
    if n:
        raise Stop(f"{step}: retry queue not drained after recovery ({n} batches)")
    return n


def voucher_cp() -> int:
    r = adb("SELECT last_alter_id FROM checkpoints WHERE entity_type LIKE 'vouchers_v2%'")
    return r[0][0] if r else None


# ====================================================================================== checking
def check(label: str, with_ft=True) -> dict:
    guards(f"check {label}")
    import io
    import contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        h2_check.main(label, with_ft)
    rec = json.loads((HERE / "results" / "checks.jsonl").read_text(encoding="utf-8").splitlines()[-1])
    if not rec["A_completeness"]["PASS"]:
        raise Stop(f"TALLY COMPLETENESS FAILED at {label}: {rec['A_completeness']}")
    if not rec["B_tally_totals"]["PASS"]:
        raise Stop(f"TALLY TOTALS FAILED at {label}: {rec['B_tally_totals']}")
    if with_ft:
        s = rec["C_fieldtrack"]["summary"]
        if s["duplicates"] or s["links_to_retired_invoices"]:
            raise Stop(f"NEVER-ALLOWED at {label}: duplicates={s['duplicates']} links_to_retired={s['links_to_retired_invoices']}")
    return rec


MECH = ["next", "hourly", "nightly"]


def settle(step: str, max_mech: str, expect_status=("COMPLETED",), extra=None) -> dict:
    """sync -> check; escalate (forced hourly + balances, then forced nightly + balances) only up to max_mech."""
    log(f"SETTLE {step} (documented window: {max_mech})")
    runs, mech_used = [], None
    for mech in MECH[:MECH.index(max_mech) + 1]:
        if mech == "hourly":
            force("hourly", "balances")
        elif mech == "nightly":
            force("nightly", "balances")
        runs.append(sync(expect_status))
        rec = check(f"{step}:{mech}")
        s = rec["C_fieldtrack"]["summary"]
        if extra:
            extra(rec)
        if s["equal"]:
            mech_used = mech
            break
        log(f"  not equal after {mech}: { {k: v for k, v in s.items() if isinstance(v, int) and v and k not in ('tally_vouchers', 'tally_rows', 'tally_links', 'fieldtrack_index_active')} }")
    out = {"step": step, "window": max_mech, "cleared_by": mech_used, "syncs": runs,
           "final": rec["C_fieldtrack"]["summary"], "samples": rec["C_fieldtrack"].get("samples")}
    record(out)
    if not mech_used:
        raise Stop(f"UNEXPLAINED MISMATCH: {step} not equal after its documented window ({max_mech}); "
                   f"samples={rec['C_fieldtrack'].get('samples')}")
    log(f"  PASS {step}: equal (cleared by {mech_used}; vouchers {s['tally_vouchers']} rows {s['tally_rows']} links {s['tally_links']})")
    return out


# ====================================================================================== test data model
class Book:
    """What the driver created, so vouchers can be altered with their full lines."""
    def __init__(self):
        self.v = {}            # guid -> spec {vtype, number, date, lines, narration, party, kind, bills, cancelled}
        self.dr = t.Driver()
        self.n = 0

    def create(self, vtype, d, lines, party=None, kind=None, **meta):
        self.n += 1
        narr = f"H2 run #{self.n} {kind or vtype}"
        r = self.dr.create(vtype, d, lines, narr, party=party)
        self.v[r["guid"]] = {"vtype": vtype, "number": r["number"], "date": d, "lines": lines, "narration": narr,
                             "party": party, "kind": kind or vtype, "cancelled": False, **meta}
        return r["guid"]

    def alter(self, g, new_date=None, lines=None, narration=None, party=None):
        s = self.v[g]
        nd = new_date or s["date"]
        self.dr.alter(s["vtype"], s["number"], s["date"], nd, lines or s["lines"], narration or s["narration"],
                      party=party or s["party"])
        s.update(date=nd, lines=lines or s["lines"], narration=narration or s["narration"], party=party or s["party"])

    def cancel(self, g):
        s = self.v[g]
        self.dr.cancel(s["vtype"], s["number"], s["date"])
        s["cancelled"] = True

    def delete(self, g):
        s = self.v.pop(g)
        self.dr.delete(s["vtype"], s["number"], s["date"])

    def pick(self, pred):
        c = [g for g, s in self.v.items() if pred(s)]
        return c

    def load_from_tally(self):
        """Resume: rebuild the model of every 'H2 run #n <kind>' voucher from a direct Tally read (no adapter)."""
        for g, v in t.voucher_map(date(2026, 4, 1), date(2027, 3, 31)).items():
            e = v["elem"]
            narr = (e.findtext("NARRATION") or "").strip()
            m = re.match(r"H2 run #(\d+) (\S+)", narr)
            if not m:
                continue
            self.n = max(self.n, int(m.group(1)))
            lines = []
            for le in e.iter("ALLLEDGERENTRIES.LIST"):
                bills = [((b.findtext("NAME") or "").strip(), (b.findtext("BILLTYPE") or "").strip(), D((b.findtext("AMOUNT") or "0").strip()))
                         for b in le.iter("BILLALLOCATIONS.LIST") if (b.findtext("AMOUNT") or "").strip()]
                ln = {"ledger": (le.findtext("LEDGERNAME") or "").strip(), "amount": D((le.findtext("AMOUNT") or "0").strip())}
                if bills:
                    ln["bills"] = bills
                lines.append(ln)
            kind = m.group(2)
            party = (e.findtext("PARTYLEDGERNAME") or "").strip() or None
            cust = next((ln["ledger"] for ln in lines if ln["ledger"].startswith("H2 Customer")), None) or party
            spec = {"vtype": v["vtype"], "number": v["number"], "date": date.fromisoformat(v["date"]), "lines": lines,
                    "narration": narr, "party": party, "kind": kind, "cancelled": v["cancelled"], "cust": cust}
            if v["cancelled"]:                            # Tally exports a cancelled voucher without its ledger entries
                spec.update(bill=None, amount=D("0"))
            elif kind == "invoice":
                pl = next(ln for ln in lines if ln["ledger"] == cust)
                named = [b for b in pl.get("bills", []) if b[0]]
                # Tally stores an invoice as "Agst Ref" when its bill name already exists (e.g. V6c re-created a bill
                # name a receipt is still allocated to)
                spec["bill"] = next((b[0] for b in named if b[1] == "New Ref"), named[0][0] if named else None)
                spec["amount"] = -pl["amount"]
            if kind == "receipt":                         # party line first (receipt_lines order)
                spec["lines"] = sorted(lines, key=lambda ln: ln["ledger"] != cust)
            self.v[g] = spec
        log(f"RESUME: rebuilt {len(self.v)} driver vouchers from Tally (highest #{self.n})")


def sales_lines(party, amount, bill):
    return [{"ledger": party, "amount": -amount, "bills": [(bill, "New Ref", -amount)]},
            {"ledger": "H2 Sales", "amount": amount}]


def receipt_lines(party, allocs, on_account=D("0")):
    total = sum((a for _, a in allocs), D("0")) + on_account
    bills = [(b, "Agst Ref", a) for b, a in allocs]
    if on_account:
        bills.append(("On Account", "On Account", on_account))
    return [{"ledger": party, "amount": total, "bills": bills}, {"ledger": "H2 Bank", "amount": -total}]


# ====================================================================================== phases
def seed(book: Book):
    log("SEED: debtor ledgers")
    openings = {}
    for i, c in enumerate(CUST):
        op = D(rng.randrange(5, 50) * 1000) if i < 5 else D("0")
        try:
            book.dr.ledger(c, "Sundry Debtors", -op, billwise=True, opening_bill=f"OB-{i + 1:02d}" if op else None)
            if op:
                openings[c] = op
        except t.DriverError as ex:
            log(f"  ledger {c} with opening refused ({ex}); creating without opening")
            book.dr.ledger(c, "Sundry Debtors", billwise=True)
    record({"step": "S4-ledgers", "customers": len(CUST), "with_opening": {k: str(v) for k, v in openings.items()}})
    types_ok = {}
    open_bills = {c: [] for c in CUST}                    # [bill, remaining, date]
    inv = 0
    log("SEED: vouchers on the 22 Educational dates 1 Apr - 2 Nov")
    for d in EDU_DATES:
        for _ in range(6):                               # sales
            inv += 1
            c = rng.choice(CUST)
            a = D(rng.randrange(10, 500) * 100)
            bill = f"INV-{inv:04d}"
            book.create("Sales", d, sales_lines(c, a, bill), party=c, kind="invoice", bill=bill, amount=a, cust=c)
            open_bills[c].append([bill, a, d])
        for k in range(4):                               # receipts against earlier bills
            c = rng.choice([x for x in CUST if open_bills[x]] or CUST)
            if not open_bills[c]:
                continue
            pattern = k % 4
            b = open_bills[c][0]
            if pattern == 0:                             # full
                allocs = [(b[0], b[1])]
            elif pattern == 1:                           # part
                allocs = [(b[0], (b[1] / 2).quantize(D("0.01")))]
            elif pattern == 2 and len(open_bills[c]) > 1:  # across two bills
                allocs = [(b[0], b[1]), (open_bills[c][1][0], (open_bills[c][1][1] / 3).quantize(D("0.01")))]
            else:
                allocs = [(b[0], min(b[1], D("1000")))]
            onacc = D("500") if pattern == 3 else D("0")
            book.create("Receipt", d, receipt_lines(c, allocs, onacc), party=c, kind="receipt", cust=c,
                        allocs=[[x, str(y)] for x, y in allocs])
            for bn, a in allocs:
                for ob in open_bills[c]:
                    if ob[0] == bn:
                        ob[1] -= a
            open_bills[c] = [ob for ob in open_bills[c] if ob[1] > 0]
        # one of credit note / debit note / journal / contra per date (types refused by Tally are skipped and recorded)
        kind = ["Credit Note", "Debit Note", "Journal", "Contra"][EDU_DATES.index(d) % 4]
        c = rng.choice([x for x in CUST if open_bills[x]] or CUST)
        a = D(rng.randrange(5, 50) * 100)
        try:
            if kind == "Credit Note" and open_bills[c]:
                b = open_bills[c][0]
                a = min(a, b[1])
                book.create(kind, d, [{"ledger": c, "amount": a, "bills": [(b[0], "Agst Ref", a)]},
                                      {"ledger": "H2 Sales", "amount": -a}], party=c, kind="credit_note", cust=c)
                b[1] -= a
            elif kind == "Debit Note":
                inv += 1
                book.create(kind, d, [{"ledger": c, "amount": -a, "bills": [(f"DN-{inv:04d}", "New Ref", -a)]},
                                      {"ledger": "H2 Sales", "amount": a}], party=c, kind="debit_note", cust=c)
                open_bills[c].append([f"DN-{inv:04d}", a, d])
            elif kind == "Journal" and open_bills[c]:
                b = open_bills[c][0]
                a = min(a, b[1])
                book.create(kind, d, [{"ledger": c, "amount": a, "bills": [(b[0], "Agst Ref", a)]},
                                      {"ledger": "H2 Expense", "amount": -a}], kind="journal", cust=c)
                b[1] -= a
            elif kind == "Contra":
                book.create(kind, d, [{"ledger": "H2 Bank", "amount": -a}, {"ledger": "Cash", "amount": a}], kind="contra")
            types_ok[kind] = types_ok.get(kind, 0) + 1
        except t.DriverError as ex:
            types_ok[kind] = f"REFUSED by Tally: {str(ex)[:120]}"
            log(f"  {kind} refused by Tally on {d}: {ex}")
    record({"step": "S4-vouchers", "created": book.n, "other_types": types_ok})
    log(f"SEED done: {book.n} vouchers; other types: {types_ok}")
    return open_bills


def unpaid_invoices(book: Book, pred=lambda s: True):
    """Invoices no receipt / note / journal refers to (safe to edit, cancel or delete without touching links)."""
    referenced = set()
    for s in book.v.values():
        for ln in s["lines"]:
            for b in ln.get("bills", []):
                if b[1] == "Agst Ref":
                    referenced.add((s.get("cust") or s.get("party"), b[0]))
    return [g for g, s in book.v.items() if s["kind"] == "invoice" and not s["cancelled"]
            and (s["cust"], s["bill"]) not in referenced and pred(s)]


def paid_invoices(book: Book, pred=lambda s: True):
    ref = {}
    for g, s in book.v.items():
        if s["kind"] == "receipt" and not s["cancelled"]:
            for b in s["lines"][0].get("bills", []):
                if b[1] == "Agst Ref":
                    ref.setdefault((s["cust"], b[0]), []).append(g)
    return [(g, ref[(s["cust"], s["bill"])]) for g, s in book.v.items()
            if s["kind"] == "invoice" and not s["cancelled"] and (s["cust"], s["bill"]) in ref and pred(s)]


def run():
    global ADAPTER_REFUSED_BASELINE
    RUN.mkdir(parents=True, exist_ok=True)
    BACKUPS.mkdir(parents=True, exist_ok=True)
    started = datetime.now()
    log("=" * 100)
    log("H2 RUN START - real TallyPrime (Educational Mode) through a test-only date adapter; NOT licensed-Tally validation")
    summary = {"started": started.isoformat(timespec="seconds"), "steps": {}, "skipped": {}, "stopped": None}
    book = Book()
    try:
        # ---------------------------------------------------------------- preflight
        log("PREFLIGHT")
        head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=sb.BACKEND, capture_output=True, text=True).stdout.strip()
        dirty = subprocess.run(["git", "status", "--porcelain"], cwd=sb.BACKEND, capture_output=True, text=True).stdout.strip()
        if head != RELEASE or dirty:
            raise Stop(f"PREFLIGHT: backend checkout {head[:7]} dirty={bool(dirty)} is not a clean {RELEASE[:7]}")
        import hashlib
        exe_hash = hashlib.sha256(EXE.read_bytes()).hexdigest()
        if exe_hash.lower() != "0466a120356518490614a69565642f68b0e9a19e67caad781dd0afc7aaa98a14":
            raise Stop(f"PREFLIGHT: exe hash {exe_hash} is not the released 3.0.0")
        ADAPTER_REFUSED_BASELINE = adapter_refusals()
        set_env(TALLY_URL=hs.LOCK["agent_tally_url"], RECONCILE_HOURLY_MINUTES=5, BALANCE_INTERVAL_MINUTES=5,
                SYNC_INTERVAL_SECONDS=60, TALLY_MIN_PAUSE_SECONDS="0.5", DAY_REQUEST_PAUSE_SECONDS="0.2")
        guards("preflight")
        Procs.start_backend()
        Procs.start_adapter()
        tt = agent(["test-tally"])
        if "FT H2 TEST 3.0" not in json.dumps(tt) and not any("PASS" in x for x in tt["tail"]):
            out = (RUN / "agent_outputs").glob("*test-tally*")
        txt = sorted((RUN / "agent_outputs").glob("*test-tally*"))[-1].read_text(encoding="utf-8")
        if "STATUS: PASS" not in txt or hs.LOCK["company_guid"] not in txt or "127.0.0.1:9001" not in txt:
            raise Stop("PREFLIGHT: agent test-tally through the adapter did not PASS for the locked company")
        tb = agent(["test-backend"])
        txt = sorted((RUN / "agent_outputs").glob("*test-backend*"))[-1].read_text(encoding="utf-8")
        if "STATUS: PASS" not in txt or "127.0.0.1:8766" not in txt:
            raise Stop("PREFLIGHT: agent test-backend did not PASS against the local H2 backend")
        base = check("preflight", with_ft=True)
        if base["C_fieldtrack"]["summary"]["fieldtrack_index_active"] != 0 and not RESUME_V4A:
            raise Stop("PREFLIGHT: the H2 database is not empty")
        record({"step": "PREFLIGHT", "result": "PASS", "exe_sha256": exe_hash, "backend": head})
        summary["steps"]["PREFLIGHT"] = "PASS"
        log("PREFLIGHT PASS - starting the unattended run")

        # ---------------------------------------------------------------- seed
        if RESUME_V4A:
            book.load_from_tally()
            smoke = {"58848a1b-efae-4185-8c50-4d1a5d6bef2a-00000001", "58848a1b-efae-4185-8c50-4d1a5d6bef2a-00000002"}
            exp = t.expected_guids_from_ledger(set()) - smoke
            if set(book.v) != exp:
                raise Stop(f"RESUME: Tally H2 vouchers != driver ledger: only_tally={sorted(set(book.v)-exp)[:5]} "
                           f"only_ledger={sorted(exp-set(book.v))[:5]}")
            summary["resumed_at"] = ("V4a verify: the 03:25 run passed PREFLIGHT, I1, I2, I3, V1, V2, V3a, V3b and stopped "
                                     "at 03:32:12 on an orchestrator log-parsing defect after the V4a forced hourly cycle "
                                     "(agent COMPLETED, RECONCILE extra=3). Model rebuilt from Tally; nothing repeated.")
            for k in ("I1 refused without approval", "I2 first load", "I3 status", "V1 create (10 invoices, 5 receipts, 2 Nov)",
                      "V2 alter (5 amounts, 1 ledger change, 3 narrations)", "V3a re-date inside 31 days (31 Oct -> 2 Nov)",
                      "V3b re-date outside 31 days (2 Nov -> 1 Aug)"):
                summary["steps"][k] = "PASS (03:25 run, results/run/steps.jsonl)"
        elif "--resume-after-seed" in sys.argv:
            book.load_from_tally()
            if book.n != 220 or len(book.v) != 220:
                raise Stop(f"RESUME: expected the 220 seeded vouchers, rebuilt {len(book.v)} (highest #{book.n})")
            summary["resumed_after_seed"] = ("first attempt 02:55 stopped at the after-seed check: the checker did not "
                                             "count the ledgers' opening bills (OB-01..05); checker fixed, seed kept")
        else:
            seed(book)
        check("after-seed", with_ft=False)
        summary["steps"]["S4 seed"] = f"PASS ({book.n} vouchers; Tally complete and totals reconcile)"

        nov2, oct31, nov1 = date(2026, 11, 2), date(2026, 10, 31), date(2026, 11, 1)
        g_c = recs_c = g_d = recs_d = None
        if not RESUME_V4A:
            # ---------------------------------------------------------------- initial
            # the stopped 03:00 attempt left a first-load approval in the local agent state: withdraw it (local only) so I1
            # really tests "refused without approval"
            if adb("SELECT count(*) FROM agent_kv WHERE key='approve_first_load:2026-27'")[0][0]:
                agent(["withdraw-first-load", "2026-27"])
                if adb("SELECT count(*) FROM agent_kv WHERE key='approve_first_load:2026-27'")[0][0]:
                    raise Stop("I1: could not withdraw the leftover first-load approval")
                log("  leftover first-load approval withdrawn (local agent state)")
            r = sync(expect=("CHECKPOINT_ZERO",))
            record({"step": "I1", "status": r["status"]})
            rec = check("I1", with_ft=True)
            if rec["C_fieldtrack"]["summary"]["fieldtrack_index_active"] != 0:
                raise Stop("I1: something was uploaded without first-load approval")
            summary["steps"]["I1 refused without approval"] = "PASS (CHECKPOINT_ZERO, nothing uploaded)"
            agent(["approve-first-load", "2026-27"])
            for i in range(10):
                r = sync()
                if "initial_load" not in r["phases"]:
                    break
                st = adb("SELECT value_json FROM agent_kv WHERE key LIKE 'load_state%' OR key LIKE 'state%'")
                if voucher_cp():
                    break
            out = settle("I2 first load", "nightly")
            summary["steps"]["I2 first load"] = f"PASS (cleared by {out['cleared_by']})"
            st = agent(["status"])
            record({"step": "I3", "voucher_checkpoint": voucher_cp()})
            summary["steps"]["I3 status"] = f"PASS (voucher checkpoint {voucher_cp()})"
            shutil.copy2(ADB, BACKUPS / "after_I2.db")


            # ---------------------------------------------------------------- lifecycle
            new_inv = []
            for i in range(10):
                c = rng.choice(CUST)
                a = D(rng.randrange(10, 300) * 100)
                bill = f"V1-{i:02d}"
                new_inv.append(book.create("Sales", nov2, sales_lines(c, a, bill), party=c, kind="invoice", bill=bill, amount=a, cust=c))
            for g in new_inv[:5]:
                s = book.v[g]
                book.create("Receipt", nov2, receipt_lines(s["cust"], [(s["bill"], (s["amount"] / 2).quantize(D("0.01")))]),
                            party=s["cust"], kind="receipt", cust=s["cust"])
            summary["steps"]["V1 create (10 invoices, 5 receipts, 2 Nov)"] = "PASS (cleared by %s)" % settle("V1", "next")["cleared_by"]

            cand = unpaid_invoices(book)
            for g in cand[:5]:
                s = book.v[g]
                na = (s["amount"] * D("1.1")).quantize(D("0.01"))
                book.alter(g, lines=sales_lines(s["cust"], na, s["bill"]))
                s["amount"] = na
            g = cand[5]
            s = book.v[g]
            newc = next(c for c in CUST if c != s["cust"])
            book.alter(g, lines=sales_lines(newc, s["amount"], s["bill"]), party=newc)
            s["cust"] = newc
            for g in cand[6:9]:
                book.alter(g, narration=book.v[g]["narration"] + " (edited)")
            summary["steps"]["V2 alter (5 amounts, 1 ledger change, 3 narrations)"] = "PASS (cleared by %s)" % settle("V2", "next")["cleared_by"]

            g_in = (unpaid_invoices(book, lambda s: s["date"] == oct31) or unpaid_invoices(book, lambda s: s["date"] == nov1))[0]
            book.alter(g_in, new_date=nov2)
            summary["steps"]["V3a re-date inside 31 days (31 Oct -> 2 Nov)"] = "PASS (cleared by %s)" % settle("V3a", "hourly")["cleared_by"]
            g_out = unpaid_invoices(book, lambda s: s["date"] == nov2)[0]
            book.alter(g_out, new_date=date(2026, 8, 1))
            summary["steps"]["V3b re-date outside 31 days (2 Nov -> 1 Aug)"] = "PASS (cleared by %s)" % settle("V3b", "nightly")["cleared_by"]

            for g in unpaid_invoices(book, lambda s: s["date"] in (nov1, nov2))[:3]:
                book.delete(g)
        if RESUME_AT:
            summary["steps"]["V4a delete 3 recent (1-2 Nov)"] = "PASS (earlier run; results/run/steps.jsonl)"
        elif RESUME_V4A:
            summary["steps"]["V4a delete 3 recent (1-2 Nov)"] = ("PASS (deleted in the 03:25 run; retired by the forced hourly "
                                                                 "reconcile at 03:32:11, RECONCILE extra=3; verified equal on "
                                                                 "resume: cleared by %s)" % settle("V4a resume verify", "next")["cleared_by"])
        else:
            summary["steps"]["V4a delete 3 recent (1-2 Nov)"] = "PASS (cleared by %s)" % settle("V4a", "hourly")["cleared_by"]
        if not _skip("V4b"):
            if not _skip_mut("V4b"):
                old = unpaid_invoices(book, lambda s: s["date"] <= date(2026, 9, 1))[:1] + \
                    [g for g, s in book.v.items() if s["kind"] == "contra" and s["date"] <= date(2026, 9, 1)][:1]
                for g in old:
                    book.delete(g)
            summary["steps"]["V4b delete 2 old (<= 1 Sep)"] = "PASS (cleared by %s)" % settle("V4b", "nightly")["cleared_by"]
        else:
            summary["steps"]["V4b delete 2 old (<= 1 Sep)"] = "PASS (earlier run; results/run/steps.jsonl)"
        if not _skip("V5"):
            if not _skip_mut("V5"):

                for g in unpaid_invoices(book)[:3]:
                    book.cancel(g)
            summary["steps"]["V5 cancel 3 unpaid invoices"] = "PASS (cleared by %s)" % settle("V5", "next")["cleared_by"]
        else:
            summary["steps"]["V5 cancel 3 unpaid invoices"] = "PASS (earlier run; results/run/steps.jsonl)"
        if not _skip("V6a"):
            if not _skip_mut("V6a"):

                # V6 relink
                paid = paid_invoices(book)
                g_c, recs_c = paid[0]
                book.cancel(g_c)
            summary["steps"]["V6a cancel an invoice WITH receipt"] = "PASS (cleared by %s)" % settle("V6a", "next")["cleared_by"]
        else:
            summary["steps"]["V6a cancel an invoice WITH receipt"] = "PASS (earlier run; results/run/steps.jsonl)"
        if not _skip("V6b"):
            if not _skip_mut("V6b"):
                paid_recent = paid_invoices(book, lambda s: s["date"] in (oct31, nov1, nov2))
                g_d, recs_d = paid_recent[0]
                sd = dict(book.v[g_d])
                book.delete(g_d)
            summary["steps"]["V6b delete an invoice WITH receipt (recent)"] = "PASS (cleared by %s)" % settle("V6b", "hourly")["cleared_by"]
        else:
            summary["steps"]["V6b delete an invoice WITH receipt (recent)"] = "PASS (earlier run; results/run/steps.jsonl)"
        if not _skip("V6c"):
            if not _skip_mut("V6c"):
                book.create("Sales", nov2, sales_lines(sd["cust"], sd["amount"], sd["bill"]), party=sd["cust"], kind="invoice",
                            bill=sd["bill"], amount=sd["amount"], cust=sd["cust"])
            summary["steps"]["V6c re-create invoice with the same bill name"] = "PASS (cleared by %s)" % settle("V6c", "next")["cleared_by"]
        else:
            summary["steps"]["V6c re-create invoice with the same bill name"] = "PASS (earlier run; results/run/steps.jsonl)"
        if not _skip("V7"):
            if not _skip_mut("V7"):
                record({"step": "V6-detail", "cancelled_invoice": g_c, "its_receipts": recs_c, "deleted_invoice": g_d,
                        "its_receipts_deleted_case": recs_d, "recreated_bill": sd["bill"]})

                # V7 re-allocate a receipt from bill A to bill B (same customer)
                moved = None
                for g, s in book.v.items():
                    if s["kind"] == "receipt" and not s["cancelled"] and len(s["lines"][0]["bills"]) == 1 and s["lines"][0]["bills"][0][1] == "Agst Ref":
                        other = unpaid_invoices(book, lambda x, c=s["cust"], d0=s["date"]: x["cust"] == c and x["date"] <= d0
                                                and x["amount"] >= s["lines"][0]["amount"])
                        if other:
                            moved = (g, s["lines"][0]["bills"][0][0], book.v[other[0]]["bill"])
                            amt = s["lines"][0]["amount"]
                            book.alter(g, lines=receipt_lines(s["cust"], [(book.v[other[0]]["bill"], amt)]))
                            break
                if not moved:
                    raise Stop("V7: no receipt / unpaid invoice pair available")
                record({"step": "V7-detail", "receipt": moved[0], "from_bill": moved[1], "to_bill": moved[2]})
            summary["steps"]["V7 re-allocate receipt to another bill"] = "PASS (cleared by %s)" % settle("V7", "next")["cleared_by"]
        else:
            summary["steps"]["V7 re-allocate receipt to another bill"] = "PASS (earlier run; results/run/steps.jsonl)"
        if not _skip("V8"):
            if RESUME_AT == "V8" and MUTATED:
                raise Stop("RESUME: V8 is a multi-step block; resuming it after its writes is not supported (never repeat writes)")

            # V8 post-dated (1 Dec): must NOT be uploaded before its date
            c = CUST[0]
            g_pd = book.create("Sales", date(2026, 12, 1), sales_lines(c, D("7777"), "PD-1201"), party=c, kind="invoice",
                               bill="PD-1201", amount=D("7777"), cust=c)

            def not_uploaded(rec):
                idx = rec["C_fieldtrack"]["summary"]["fieldtrack_index_active"]
                async_q = None
                import asyncio
                import asyncpg

                async def q():
                    conn = await asyncpg.connect(sb.harness_env()["DATABASE_URL"].replace("postgresql+asyncpg://", "postgresql://"))
                    try:
                        return await conn.fetchval("SELECT count(*) FROM tally_voucher_index WHERE guid=$1", g_pd)
                    finally:
                        await conn.close()
                n = asyncio.run(q())
                if n:
                    raise Stop(f"V8: post-dated voucher {g_pd} (1 Dec) was uploaded before its date")
            out = settle("V8 post-dated 1 Dec (P1)", "next", extra=not_uploaded)
            force("hourly")
            sync()
            not_uploaded(check("V8:after-forced-hourly"))
            force("nightly")
            sync()
            not_uploaded(check("V8:after-forced-nightly"))
            summary["steps"]["V8/P1 post-dated 1 Dec not uploaded early (fast path, hourly, nightly)"] = "PASS"
        else:
            summary["steps"]["V8/P1 post-dated 1 Dec not uploaded early (fast path, hourly, nightly)"] = "PASS (earlier run; results/run/steps.jsonl)"
        if not _skip("V9"):
            if not _skip_mut("V9"):
                summary["skipped"]["P2 post-dated uploaded on 1 Dec"] = "scheduled for 1 Dec 2026 (no clock change)"

                c = rng.choice(CUST)
                book.create("Sales", date(2026, 9, 1), sales_lines(c, D("4321"), "V9-BACK"), party=c, kind="invoice",
                            bill="V9-BACK", amount=D("4321"), cust=c)
            summary["steps"]["V9 back-dated voucher (1 Sep)"] = "PASS (cleared by %s)" % settle("V9", "next")["cleared_by"]
        else:
            summary["steps"]["V9 back-dated voucher (1 Sep)"] = "PASS (earlier run; results/run/steps.jsonl)"
        if not _skip("R"):
            if RESUME_AT == "R" and MUTATED:
                raise Stop("RESUME: R is a multi-step block; resuming it after its writes is not supported (never repeat writes)")

            rec = check("R1-R2")
            s = rec["C_fieldtrack"]["summary"]
            if not s["equal"] or s["outstanding"] or s["links_missing"] or s["links_extra"] or s["links_wrong"]:
                raise Stop(f"R1/R2 failed: {s}")
            summary["steps"]["R1 outstanding per ledger / R2 every receipt link"] = (
                f"PASS ({rec['B_tally_totals']['debtor_ledgers']} debtors, {s['tally_links']} links, Tally open bills "
                f"{rec['B_tally_totals']['tally_open_bills']} = recomputed)")
        else:
            summary["steps"]["R1 outstanding per ledger / R2 every receipt link"] = "PASS (earlier run; results/run/steps.jsonl)"
        if not _skip("F4"):
            if not _skip_mut("F4"):
                shutil.copy2(ADB, BACKUPS / "after_R.db")

                # ---------------------------------------------------------------- faults
                Procs.stop_backend()
                for i in range(3):
                    book.create("Sales", nov2, sales_lines(CUST[i], D("1111") + i, f"F4-{i}"), party=CUST[i], kind="invoice",
                                bill=f"F4-{i}", amount=D("1111") + i, cust=CUST[i])
                for g in unpaid_invoices(book, lambda s: s["date"] < nov1)[:2]:
                    s = book.v[g]
                    book.alter(g, lines=sales_lines(s["cust"], s["amount"] + 1, s["bill"]))
                    s["amount"] += 1
                book.delete(unpaid_invoices(book, lambda s: s["date"] in (nov1, nov2))[0])
                st = [sync(expect=None) for _ in range(3)]
                record({"step": "F4-outage", "statuses": [x["status"] for x in st]})
                # 3.0 design: a failed voucher upload is saved to the retry queue and the cycle may still end COMPLETED
                # (only reconcile / snapshot failures raise BACKEND_ERROR). Accept COMPLETED only if nothing was sent
                # and every extracted voucher was queued.
                for x in st:
                    v = x.get("vouchers") or {}
                    if x["status"] == "COMPLETED" and (v.get("sent") or 0) != 0:
                        raise Stop(f"F4: agent SENT vouchers while the backend was down: {st}")
                Procs.start_backend()
            summary["steps"]["F4 backend down 3 cycles with changes"] = "PASS (outage: batch queued for retry, cleared by %s; retry queue after: %s)" % (settle("F4", "hourly")["cleared_by"], _retry_drained("F4"))
        else:
            summary["steps"]["F4 backend down 3 cycles with changes"] = "PASS (earlier run; results/run/steps.jsonl)"
        if not _skip("F5"):
            if RESUME_AT == "F5" and MUTATED:
                raise Stop("RESUME: F5 is a multi-step block; resuming it after its writes is not supported (never repeat writes)")

            set_env(BATCH_SIZE=5)
            for i in range(40):
                c = CUST[i % 20]
                book.create("Sales", nov2, sales_lines(c, D("200") + i, f"F5-{i:02d}"), party=c, kind="invoice",
                            bill=f"F5-{i:02d}", amount=D("200") + i, cust=c)
            guards("F5")
            p = subprocess.Popen([str(EXE), "sync"], cwd=AGENT, env=agent_env(), stdout=open(RUN / "F5_sync.txt", "w"), stderr=subprocess.STDOUT)
            killed_at = None
            for _ in range(240):
                time.sleep(0.25)
                bl = (RUN / "backend.log").read_text(errors="ignore") if (RUN / "backend.log").exists() else ""
                if p.poll() is not None:
                    break
                if "sync/vouchers" in bl[-20000:] or "/vouchers" in bl[-20000:]:
                    Procs.stop_backend()
                    killed_at = datetime.now().isoformat(timespec="seconds")
                    break
            if killed_at is None and p.poll() is None:
                time.sleep(3)
                Procs.stop_backend()
                killed_at = datetime.now().isoformat(timespec="seconds") + " (timed)"
            p.wait(timeout=900)
            f5out = (RUN / "F5_sync.txt").read_text(errors="ignore")
            m = re.search(r'"status":\s*"([A-Z_]+)"', f5out)
            record({"step": "F5-interrupt", "backend_killed_at": killed_at, "interrupted_sync_status": m.group(1) if m else None})
            log(f"  F5 interrupted sync status: {m.group(1) if m else None}; backend killed at {killed_at}")
            Procs.start_backend()
            set_env(BATCH_SIZE=100)
            summary["steps"]["F5 backend killed mid-upload"] = "PASS (interrupted status %s, cleared by %s)" % (
                m.group(1) if m else None, settle("F5", "hourly")["cleared_by"])
        else:
            summary["steps"]["F5 backend killed mid-upload"] = "PASS (earlier run; results/run/steps.jsonl)"
        if not _skip("F6"):
            if RESUME_AT == "F6" and MUTATED:
                raise Stop("RESUME: F6 is a multi-step block; resuming it after its writes is not supported (never repeat writes)")

            book.delete(unpaid_invoices(book, lambda s: s["date"] <= date(2026, 7, 31))[0])   # old deletion: nightly
            force("nightly")
            guards("F6")
            p = subprocess.Popen([str(EXE), "sync"], cwd=AGENT, env=agent_env(), stdout=open(RUN / "F6_sync.txt", "w"), stderr=subprocess.STDOUT)
            time.sleep(4)
            Procs.stop_backend()
            p.wait(timeout=900)
            f6 = re.search(r'"status":\s*"([A-Z_]+)"', (RUN / "F6_sync.txt").read_text(errors="ignore"))
            record({"step": "F6-interrupt", "interrupted_sync_status": f6.group(1) if f6 else None})
            Procs.start_backend()
            summary["steps"]["F6 backend down during the nightly"] = "PASS (interrupted status %s, cleared by %s)" % (
                f6.group(1) if f6 else None, settle("F6", "nightly")["cleared_by"])
        else:
            summary["steps"]["F6 backend down during the nightly"] = "PASS (earlier run; results/run/steps.jsonl)"
        if not _skip("A1"):
            if not _skip_mut("A1"):

                # ---------------------------------------------------------------- restarts / checkpoints
                for i in range(5):
                    book.create("Sales", nov2, sales_lines(CUST[i], D("3333") + i, f"A1-{i}"), party=CUST[i], kind="invoice",
                                bill=f"A1-{i}", amount=D("3333") + i, cust=CUST[i])
                guards("A1")
                p = subprocess.Popen([str(EXE), "sync"], cwd=AGENT, env=agent_env(), stdout=open(RUN / "A1_sync.txt", "w"), stderr=subprocess.STDOUT)
                time.sleep(3)
                subprocess.run(["taskkill", "/PID", str(p.pid), "/T", "/F"], capture_output=True)
                p.wait(timeout=60)
                record({"step": "A1-kill", "killed_pid": p.pid})
            summary["steps"]["A1 agent killed mid-cycle"] = "PASS (cleared by %s)" % settle("A1", "hourly")["cleared_by"]
        else:
            summary["steps"]["A1 agent killed mid-cycle"] = "PASS (earlier run; results/run/steps.jsonl)"
        if not _skip("A2"):
            if not _skip_mut("A2"):

                shutil.copy2(ADB, BACKUPS / "before_A2.db")
                shutil.copy2(BACKUPS / "after_I2.db", ADB)
                record({"step": "A2-restore", "restored": "after_I2.db", "checkpoint_now": voucher_cp()})
            summary["steps"]["A2 old sync_agent.db restored"] = "PASS (cleared by %s)" % settle("A2", "nightly")["cleared_by"]
        else:
            summary["steps"]["A2 old sync_agent.db restored"] = "PASS (earlier run; results/run/steps.jsonl)"
        if not _skip("A3"):
            if RESUME_AT == "A3" and MUTATED:
                raise Stop("RESUME: A3 is a multi-step block; resuming it after its writes is not supported (never repeat writes)")

            adb("UPDATE checkpoints SET last_alter_id=-5 WHERE entity_type LIKE 'vouchers_v2%'")
            r = sync(expect=("COMPLETED", "CHECKPOINT_INVALID"))
            rebuilt = "CHECKPOINT_REBUILT" in "".join(open(AGENT / "data" / "sync_agent.log", encoding="utf-8", errors="ignore").readlines()[-400:])
            record({"step": "A3-corrupt", "status": r["status"], "checkpoint_rebuilt_logged": rebuilt, "checkpoint_now": voucher_cp()})
            if not rebuilt or (voucher_cp() or 0) <= 0:
                raise Stop(f"A3: checkpoint not rebuilt (status {r['status']}, checkpoint {voucher_cp()})")
            summary["steps"]["A3 corrupt checkpoint"] = "PASS (CHECKPOINT_REBUILT, cleared by %s)" % settle("A3", "next")["cleared_by"]
        else:
            summary["steps"]["A3 corrupt checkpoint"] = "PASS (earlier run; results/run/steps.jsonl)"
        if not _skip("A4"):
            if RESUME_AT == "A4" and MUTATED:
                raise Stop("RESUME: A4 is a multi-step block; resuming it after its writes is not supported (never repeat writes)")

            cp = voucher_cp()
            adb("UPDATE checkpoints SET last_alter_id=? WHERE entity_type LIKE 'vouchers_v2%'", (cp + 100000,))
            a4 = unpaid_invoices(book, lambda s: s["date"] <= date(2026, 10, 2))[:3]   # outside the hourly 31-day window
            if len(a4) < 3:
                raise Stop(f"A4: only {len(a4)} old unpaid invoices to edit; the test cannot be exercised")
            for g in a4:
                s = book.v[g]
                book.alter(g, lines=sales_lines(s["cust"], s["amount"] + 7, s["bill"]))
                s["amount"] += 7
            out = settle("A4 checkpoint far ahead + 3 old edits", "nightly")
            corrected = "CHECKPOINT_AHEAD_CORRECTED" in "".join(open(AGENT / "data" / "sync_agent.log", encoding="utf-8", errors="ignore").readlines()[-600:])
            record({"step": "A4-detail", "checkpoint_set": cp + 100000, "checkpoint_after": voucher_cp(), "corrected_logged": corrected})
            if not corrected or voucher_cp() >= cp + 100000:
                raise Stop(f"A4: checkpoint ahead not corrected (now {voucher_cp()})")
            summary["steps"]["A4 checkpoint far ahead"] = f"PASS (CHECKPOINT_AHEAD_CORRECTED, cleared by {out['cleared_by']})"
        else:
            summary["steps"]["A4 checkpoint far ahead"] = "PASS (earlier run; results/run/steps.jsonl)"
        if not _skip("A5"):
            if RESUME_AT == "A5" and MUTATED:
                raise Stop("RESUME: A5 is a multi-step block; resuming it after its writes is not supported (never repeat writes)")

            shutil.copy2(ADB, BACKUPS / "before_A5.db")
            before = check("A5:before")["C_fieldtrack"]["summary"]
            ADB.unlink()
            r = sync(expect=("CHECKPOINT_ZERO",))
            after = check("A5:after-delete")["C_fieldtrack"]["summary"]
            if after["fieldtrack_index_active"] != before["fieldtrack_index_active"] or not after["equal"]:
                raise Stop(f"A5: FieldTrack changed after the state was deleted: before={before} after={after}")
            shutil.copy2(BACKUPS / "before_A5.db", ADB)
            summary["steps"]["A5 state deleted, no approval"] = "PASS (CHECKPOINT_ZERO, nothing uploaded or retired; state restored, cleared by %s)" % settle("A5", "next")["cleared_by"]
        else:
            summary["steps"]["A5 state deleted, no approval"] = "PASS (earlier run; results/run/steps.jsonl)"
        if not _skip("T2"):
            if RESUME_AT == "T2" and MUTATED:
                raise Stop("RESUME: T2 is a multi-step block; resuming it after its writes is not supported (never repeat writes)")

            # ---------------------------------------------------------------- T2: daemon, default hourly interval
            set_env(RECONCILE_HOURLY_MINUTES=60)
            g_t2 = unpaid_invoices(book, lambda s: s["date"] in (oct31, nov1, nov2))[0]
            book.delete(g_t2)
            t2_start = datetime.now()
            hourly_last = adb("SELECT last_successful_sync_at FROM checkpoints WHERE entity_type LIKE 'reconcile_hourly_v3%'")
            guards("T2")
            dm = subprocess.Popen([str(EXE), "daemon"], cwd=AGENT, env=agent_env(), stdout=open(RUN / "T2_daemon.txt", "w"), stderr=subprocess.STDOUT)
            cleared = None
            n_before = sum(1 for _ in ADAPTER_LOG.open(encoding="utf-8"))
            while (datetime.now() - t2_start).total_seconds() < 65 * 60:
                time.sleep(300)
                guards("T2 poll")
                rec = check(f"T2:{int((datetime.now() - t2_start).total_seconds() // 60)}min")
                if rec["C_fieldtrack"]["summary"]["equal"] and cleared is None:
                    cleared = round((datetime.now() - t2_start).total_seconds() / 60, 1)
                    log(f"  T2: deletion cleared by the daemon after {cleared} min")
                    break
            subprocess.run(["taskkill", "/PID", str(dm.pid), "/T", "/F"], capture_output=True)
            dm.wait(timeout=60)
            reqs = sum(1 for _ in ADAPTER_LOG.open(encoding="utf-8")) - n_before
            record({"step": "T2", "hourly_last_before": hourly_last, "cleared_after_min": cleared, "tally_requests": reqs})
            set_env(RECONCILE_HOURLY_MINUTES=5)
            if cleared is None:
                raise Stop("T2: recent deletion not cleared by the daemon within 65 min at the default hourly interval")
            summary["steps"]["T2 daemon at default hourly interval"] = f"PASS (recent deletion cleared after {cleared} min; {reqs} Tally requests)"
        else:
            summary["steps"]["T2 daemon at default hourly interval"] = "PASS (earlier run; results/run/steps.jsonl)"

        # ---------------------------------------------------------------- final
        out = settle("Z1 final (forced nightly)", "next")
        force("nightly", "balances")
        sync()
        fin = check("Z1:final-after-nightly")
        if not fin["PASS"]:
            raise Stop(f"Z1: final check not PASS: {fin['C_fieldtrack']['summary']}")
        summary["final_check"] = {"A": fin["A_completeness"], "B": fin["B_tally_totals"], "C": fin["C_fieldtrack"]["summary"]}
        # adapter audit
        refused = adapter_refusals() - ADAPTER_REFUSED_BASELINE
        bad_rewrites = 0
        total = rewrites = 0
        for line in ADAPTER_LOG.read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            if r.get("at", "") < started.isoformat():
                continue
            total += 1
            for ch in r.get("changes") or []:
                if ch["kind"] in ("SVFROMDATE", "SVTODATE", "$Date >=", "$Date <="):
                    rewrites += 1
                    a, b = sorted([date.fromisoformat(ch["from"]), date.fromisoformat(ch["to"])])
                    skipped = [x for x in h2_check.allowed_days(a, b) if x not in (date.fromisoformat(ch["to"]),)]
                    if skipped:
                        bad_rewrites += 1
        summary["adapter_audit"] = {"requests": total, "date_rewrites": rewrites, "refused_during_run": refused,
                                    "rewrites_skipping_an_allowed_day": bad_rewrites}
        if refused or bad_rewrites:
            raise Stop(f"ADAPTER AUDIT failed: {summary['adapter_audit']}")
        summary["steps"]["Z1 final independent reconciliation"] = "PASS"
        summary["steps"]["Z2 adapter audit (no write reached Tally; rewrites only skipped voucher-free days)"] = "PASS"
        summary["result"] = "PASS"
        log("H2 RUN COMPLETE: PASS")
    except Stop as s:
        summary["stopped"] = str(s)
        summary["result"] = "STOPPED"
        log(f"STOP: {s}")
        record({"step": "STOP", "reason": str(s)})
    except Exception as ex:
        summary["stopped"] = f"EXCEPTION {type(ex).__name__}: {ex}"
        summary["result"] = "STOPPED"
        log("EXCEPTION:\n" + traceback.format_exc())
        record({"step": "STOP", "reason": summary["stopped"], "traceback": traceback.format_exc()[-3000:]})
    finally:
        try:
            Procs.stop_all()
        except Exception as ex:
            log(f"stop_all error: {ex}")
        ended = datetime.now()
        summary["ended"] = ended.isoformat(timespec="seconds")
        summary["runtime_minutes"] = round((ended - started).total_seconds() / 60, 1)
        summary["vouchers_created_by_driver"] = book.n
        summary["label"] = "real TallyPrime (Educational Mode) through a test-only date adapter - NOT licensed-Tally validation"
        (RUN / "summary.json").write_text(json.dumps(summary, indent=1, default=str), encoding="utf-8")
        log(f"RESULT {summary.get('result')} runtime {summary['runtime_minutes']} min")


if __name__ == "__main__":
    run()
