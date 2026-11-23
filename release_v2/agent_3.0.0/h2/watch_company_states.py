"""Records how the released agent exe responds to each Tally company state while the user switches companies.

Read-only towards Tally (Export only). Polls the loaded companies every 5 s; on every NEW state it runs
`test-tally`, and, only when the state is NOT exactly the locked test company, also `sync` (which must refuse).
In the correct state, `sync` is NOT run (no first-load approval exists; that is H2 step I1, not tonight).
If the SGRG GUID ever appears, nothing is run; an ALERT is logged.
After each refused sync, the H2 database is checked to hold no Tally data.

    python watch_company_states.py <minutes>       -> results/company_states.jsonl (+ stdout)
"""
import asyncio
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "harness"))
import h2_safety as hs  # noqa: E402
import h2_agentenv  # noqa: E402
import setup_backend as sb  # noqa: E402

sb.HARNESS_DB = hs.LOCK["backend_db"]
AGENT = Path(r"F:\FT_H2\agent")
OUT = HERE / "results" / "company_states.jsonl"
SGRG = set(hs.LOCK["rejected_company_guids"])


def run(cmd):
    p = subprocess.run([str(AGENT / "FieldTrackTallyAgent.exe"), cmd], cwd=AGENT, capture_output=True, text=True, timeout=600,
                       env=h2_agentenv.agent_env())
    out = (p.stdout + p.stderr)
    keep = [l for l in out.splitlines() if any(w in l for w in ("STATUS", "Company", "GUID", "WRONG", "MULTIPLE",
            "NO_COMPANY", "Not syncing", "status", "refus", "ERROR", "error", "approve"))]
    return {"exit": p.returncode, "lines": [l[:300] for l in keep][-15:]}


async def db_counts():
    import asyncpg
    c = await asyncpg.connect(sb.harness_env()["DATABASE_URL"].replace("postgresql+asyncpg://", "postgresql://"))
    try:
        out = {}
        for t in ("tally_voucher_index", "invoices", "payments", "tally_ledger_adjustments", "tally_debtor_ledgers"):
            out[t] = await c.fetchval(f"SELECT count(*) FROM {t}")
        return out
    finally:
        await c.close()


def main(minutes: float):
    OUT.parent.mkdir(exist_ok=True)
    seen, end = set(), time.time() + minutes * 60
    while time.time() < end:
        try:
            cs = hs.loaded_companies()
        except Exception as ex:
            cs = None
            key = ("TALLY_UNREACHABLE", type(ex).__name__)
        else:
            key = tuple(sorted((c["name"], c["guid"]) for c in cs))
        if key not in seen:
            seen.add(key)
            rec = {"at": datetime.now().isoformat(timespec="seconds"), "companies": cs}
            if cs is None:
                rec["note"] = "Tally not reachable"
            elif any(c["guid"] in SGRG for c in cs):
                rec["ALERT"] = "SGRG company loaded - nothing run"
            else:
                correct = len(cs) == 1 and cs[0]["guid"] == hs.LOCK["company_guid"]
                rec["state"] = "CORRECT (test company only)" if correct else \
                    ("NONE" if not cs else "MULTIPLE" if len(cs) > 1 else "OTHER COMPANY ONLY")
                try:
                    hs.assert_test_company()
                    rec["driver_lock"] = "ALLOW"
                except hs.LockViolation as e:
                    rec["driver_lock"] = f"REFUSE: {e}"
                rec["test_tally"] = run("test-tally")
                if not correct:
                    rec["sync"] = run("sync")
                    rec["h2_db_after"] = asyncio.run(db_counts())
            print(json.dumps(rec, default=str), flush=True)
            with OUT.open("a", encoding="utf-8") as f:
                f.write(json.dumps(rec, default=str) + "\n")
        time.sleep(5)
    print("WATCH END", flush=True)


if __name__ == "__main__":
    main(float(sys.argv[1]))
