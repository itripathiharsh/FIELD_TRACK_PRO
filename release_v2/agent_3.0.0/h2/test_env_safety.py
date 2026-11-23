"""Polluted-environment safety tests for H2 agent launches. Nothing here can reach a remote host:
remote targets used are only an .invalid hostname, a TEST-NET documentation address (192.0.2.10) and the production
URL (refused by the agent before any request) - and every agent process runs behind the dead-proxy barrier.
Uploads nothing (no sync / first load). -> results/env_safety_tests.json
"""
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.argv = [sys.argv[0]]
sys.path.insert(0, str(HERE))
import h2_run as r  # noqa: E402
import h2_agentenv  # noqa: E402

RESULTS = []


def rec(name, ok, detail):
    RESULTS.append({"test": name, "PASS": bool(ok), "detail": detail})
    print(f"{'PASS' if ok else 'FAIL'}  {name}: {detail}", flush=True)


def out_of(cmd):
    return sorted((r.RUN / "agent_outputs").glob(f"*{cmd}*"))[-1].read_text(encoding="utf-8", errors="ignore")


def main():
    r.RUN.mkdir(parents=True, exist_ok=True)
    r.ADAPTER_REFUSED_BASELINE = r.adapter_refusals()
    # ------------------------------------------------------------------ pollute the PARENT environment
    import replay_tally, oracle  # noqa: F401  (loads the developer .env into os.environ - the incident)
    os.environ.update({
        "AGENT_KEY": "polluted-key", "AGENT_ID": "00000000-polluted", "ORGANIZATION_ID": "polluted",
        "TALLY_URL": "http://127.0.0.1:9000", "EXPECTED_COMPANY_GUID": "19a03e17-e1ab-44f2-8e7f-1bff56f20ebe",
        "AGENT_INSTANCE_NAME": "", "ALLOW_NAMED_INSTANCE_ON_PRODUCTION": "true",
        "HTTPS_PROXY": "", "NO_PROXY": "*", "backend_timeout_seconds": "5"})
    polluted = {k: os.environ.get(k, "")[:45] for k in ("BACKEND_URL", "TALLY_URL", "EXPECTED_COMPANY_GUID", "AGENT_KEY", "NO_PROXY")}
    rec("P0 parent environment polluted (developer .env + injected values)",
        "onrender.com" in os.environ.get("BACKEND_URL", ""), polluted)

    env = r.agent_env()
    survivors = sorted(k for k in env if k.upper() in h2_agentenv.AGENT_KEYS - h2_agentenv.PROXY_KEYS)
    rec("T1 agent environment: every agent key stripped", not survivors, f"survivors={survivors}")
    rec("T1b agent environment: dead-proxy barrier set, only 127.0.0.1/localhost exempt",
        env.get("HTTP_PROXY") == env.get("HTTPS_PROXY") == env.get("ALL_PROXY") == "http://127.0.0.1:9" and env.get("NO_PROXY") == "127.0.0.1,localhost",
        {k: env.get(k) for k in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY")})
    lower = h2_agentenv.agent_env({"backend_url": "https://x.invalid", "Agent_Key": "k", "PATH": "p"})
    rec("T1c case variants (Windows names are case-insensitive) stripped", set(lower) - {"HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY"} == {"PATH"}, sorted(lower))

    r.Procs.start_backend()
    r.Procs.start_adapter()
    try:
        # ---------------------------------------------------------------- positive: polluted parent, real agent
        b0 = r._count(r.RUN / "backend.log")
        r.agent(["test-backend"])
        t = out_of("test-backend")
        rec("T2 test-backend with polluted parent -> local H2 backend only",
            "STATUS: PASS" in t and "http://127.0.0.1:8766" in t and r._count(r.RUN / "backend.log") > b0,
            [l.strip() for l in t.splitlines() if "Backend URL" in l or "organization_id" in l][:2])
        a0 = r._count(r.ADAPTER_LOG)
        r.agent(["test-tally"])
        t = out_of("test-tally")
        rec("T3 test-tally with polluted parent (TALLY_URL=:9000, SGRG GUID injected) -> adapter, test company",
            "STATUS: PASS" in t and "127.0.0.1:9001" in t and r.hs.LOCK["company_guid"] in t and r._count(r.ADAPTER_LOG) > a0,
            [l.strip() for l in t.splitlines() if "Endpoint" in l or "Company GUID" in l][:2])
        b0, a0 = r._count(r.RUN / "backend.log"), r._count(r.ADAPTER_LOG)
        r.agent(["health"])
        t = out_of("health")
        rec("T4 health (backend + Tally in one process) with polluted parent -> local backend + adapter",
            "FT H2 TEST 3.0" in t and r._count(r.RUN / "backend.log") > b0 and r._count(r.ADAPTER_LOG) > a0,
            [l.strip() for l in t.splitlines() if "Status" in l or "Active Company" in l][:4])

        # ---------------------------------------------------------------- receipt guard: a wrong target is caught
        real_env = r.agent_env
        try:
            r.agent_env = lambda: {**h2_agentenv.agent_env(), "BACKEND_URL": "http://127.0.0.1:9"}
            try:
                r.agent(["test-backend"])
                rec("T5 receipt guard: agent sent to a wrong backend is STOPPED", False, "no Stop raised")
            except r.Stop as s:
                rec("T5 receipt guard: agent sent to a wrong backend is STOPPED", "no request at the local H2 backend" in str(s), str(s)[:120])
            r.agent_env = lambda: {**h2_agentenv.agent_env(), "TALLY_URL": "http://127.0.0.1:9000"}
            try:
                r.agent(["test-tally"])
                rec("T6 receipt guard: agent reading Tally around the adapter is STOPPED", False, "no Stop raised")
            except r.Stop as s:
                rec("T6 receipt guard: agent reading Tally around the adapter is STOPPED", "through the adapter" in str(s), str(s)[:120])
        finally:
            r.agent_env = real_env
    finally:
        r.Procs.stop_all()

    # ---------------------------------------------------------------- barrier: a leaked REMOTE URL cannot leave the machine
    lc = Path(r"F:\FT_H2\lockcheck_env")
    shutil.rmtree(lc, ignore_errors=True)
    lc.mkdir(parents=True)
    shutil.copy2(r.EXE, lc / r.EXE.name)
    envtxt = (r.AGENT / ".env").read_text(encoding="utf-8-sig")
    import re
    envtxt = re.sub(r"^AGENT_KEY=.*$", "AGENT_KEY=invalid-lockcheck", envtxt, flags=re.M)
    envtxt = re.sub(r"^AGENT_ID=.*$", "AGENT_ID=00000000-0000-0000-0000-000000000000", envtxt, flags=re.M)
    (lc / ".env").write_text(envtxt, encoding="utf-8")
    for name, url in (("T7 .invalid host", "https://remote-backend.invalid"), ("T8 TEST-NET address", "https://192.0.2.10")):
        env = {**h2_agentenv.agent_env(), "BACKEND_URL": url}          # simulate a leak that survived the strip
        p = subprocess.run([str(lc / r.EXE.name), "test-backend"], cwd=lc, env=env, capture_output=True, text=True, timeout=120)
        o = p.stdout + p.stderr
        via_proxy = ("10061" in o or "refused" in o.lower() or "Tunnel" in o) and "getaddrinfo" not in o
        rec(f"{name}: leaked remote BACKEND_URL fails at the local dead proxy (no DNS, no packet out)",
            "STATUS: PASS" not in o and via_proxy, [l.strip()[:160] for l in o.splitlines() if "Error" in l or "FAIL" in l or "refused" in l.lower()][:2])
    env = {**h2_agentenv.agent_env(), "BACKEND_URL": "https://51-79-158-138.sslip.io"}
    p = subprocess.run([str(lc / r.EXE.name), "test-backend"], cwd=lc, env=env, capture_output=True, text=True, timeout=120)
    o = p.stdout + p.stderr
    rec("T9 leaked PRODUCTION URL: named instance refuses before any request (exit 2), behind the barrier as well",
        p.returncode == 2 and "INSTANCE_CONFIG_REFUSED" in o, [l.strip()[:160] for l in o.splitlines() if "refus" in l.lower()][:1])
    shutil.rmtree(lc, ignore_errors=True)

    ok = all(x["PASS"] for x in RESULTS)
    (HERE / "results" / "env_safety_tests.json").write_text(json.dumps(
        {"at": datetime.now().isoformat(timespec="seconds"), "PASS": ok, "tests": RESULTS}, indent=1), encoding="utf-8")
    print("ENV SAFETY TESTS:", "PASS" if ok else "FAIL", f"({sum(x['PASS'] for x in RESULTS)}/{len(RESULTS)})")
    return ok


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
