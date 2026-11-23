"""The ONLY way H2 tooling builds the environment of an Agent 3.0.0 process.

Why (incident 22 Nov 03:00): the released settings loader copies .env keys into os.environ when absent, and
environment variables WIN over the .env file (tally_sync_agent/config/settings.py:96-109). Importing the
developer-checkout agent package in a parent process (the replay oracle does) planted the DEVELOPER .env
(legacy Render backend, developer agent key, Tally :9000) into the parent's environment, and every agent process
inherited it. Two layers stop that here:

  1. STRIP: every agent configuration key (any case; Windows names are case-insensitive) is removed, so the exe
     can only use its own H2 .env (which h2_safety.assert_agent_env pins to 127.0.0.1:8766 / adapter :9001 /
     the test company GUID).
  2. NO-REMOTE BARRIER: HTTP_PROXY / HTTPS_PROXY / ALL_PROXY point at a closed local port (127.0.0.1:9) and NO_PROXY
     exempts only 127.0.0.1 and localhost. The agent uses urllib, which honours these variables, so any request to a
     non-local host fails at the dead proxy on this machine (no DNS lookup, no packet leaves) instead of reaching
     Render, OVH or anything else.
"""
from __future__ import annotations

import os
from pathlib import Path

HERE = Path(__file__).resolve().parent
AGENT = Path(r"F:\FT_H2\agent")
DEAD_PROXY = "http://127.0.0.1:9"
LOCAL_ONLY = "127.0.0.1,localhost"
PROXY_KEYS = {"HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY", "FTP_PROXY"}


def agent_keys() -> set:
    keys = set()
    for p in (AGENT / "env.template", AGENT / ".env", HERE.parents[2] / "tally_sync_agent" / ".env"):
        if p.exists():
            for line in p.read_text(encoding="utf-8-sig").splitlines():
                if "=" in line and not line.lstrip().startswith("#"):
                    keys.add(line.split("=", 1)[0].strip().upper())
    return keys | {"BACKEND_URL", "TALLY_URL", "AGENT_ID", "AGENT_KEY", "ORGANIZATION_ID", "EXPECTED_COMPANY_GUID",
                   "AGENT_INSTANCE_NAME", "ALLOW_NAMED_INSTANCE_ON_PRODUCTION", "BACKEND_TIMEOUT_SECONDS",
                   "TALLY_TIMEOUT_SECONDS", "SYNC_FROM_DATE", "FINANCIAL_YEARS", "HISTORY_UPLOAD"} | PROXY_KEYS


AGENT_KEYS = agent_keys()


def agent_env(base: dict | None = None) -> dict:
    src = os.environ if base is None else base
    env = {k: v for k, v in src.items() if k.upper() not in AGENT_KEYS}
    env.update({"HTTP_PROXY": DEAD_PROXY, "HTTPS_PROXY": DEAD_PROXY, "ALL_PROXY": DEAD_PROXY, "NO_PROXY": LOCAL_ONLY})
    leaked = sorted(k for k in env if k.upper() in AGENT_KEYS - PROXY_KEYS)
    if leaked:
        raise RuntimeError(f"agent configuration keys survived the strip: {leaked}")
    return env
