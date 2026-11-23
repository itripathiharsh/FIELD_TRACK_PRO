"""Version-rollback leg of the harness: run the RELEASED agent 2.2.3 source for a few cycles on the same agent folder
and the same replay Tally, then hand back (the main harness upgrades to 3.0 again and must recover).

  python rollback_223.py <dir containing tally_sync_agent 2.2.3> <tally.pkl> <agent_dir> <data_dir> <iso sim times...>

2.2.3 has no clock hooks: its checkpoint / due-time clock (datetime.now) is replaced in its modules by the simulated
time, so its schedule follows the replay. Nothing else of 2.2.3 is changed.
"""
from __future__ import annotations

import json
import os
import pickle
import sys
from datetime import datetime, timezone
from pathlib import Path

src, tally_pkl, agent_dir, data_dir = sys.argv[1:5]
times = [datetime.fromisoformat(x) for x in sys.argv[5:]]
sys.path.insert(0, src)
sys.path.insert(1, str(Path(__file__).resolve().parent))
cred = json.loads((Path(data_dir) / "agent.json").read_text())
os.environ.update({
    "BACKEND_URL": "http://127.0.0.1:8765", "AGENT_ID": cred["agent_id"], "AGENT_KEY": cred["agent_key"],
    "EXPECTED_COMPANY_GUID": "19a03e17-e1ab-44f2-8e7f-1bff56f20ebe", "FINANCIAL_YEARS": "2024-25,2025-26,2026-27",
    "SYNC_FROM_DATE": "2026-04-01", "HISTORY_UPLOAD": "2025-26", "TALLY_MIN_PAUSE_SECONDS": "0", "TALLY_DUTY_FACTOR": "0",
    "BALANCE_INTERVAL_MINUTES": "60", "MANIFEST_INTERVAL_HOURS": "24", "AGENT_INSTANCE_NAME": "",
})

import logging  # noqa: E402

from tally_sync_agent.config.settings import AGENT_VERSION  # noqa: E402
from tally_sync_agent.core import checkpoint_manager as CM  # noqa: E402
from tally_sync_agent.core import logger as L  # noqa: E402
from tally_sync_agent.core.backend_client import BackendClient  # noqa: E402
from tally_sync_agent.core.quarantine_store import QuarantineStore  # noqa: E402
from tally_sync_agent.core.retry_queue import RetryQueue  # noqa: E402
from tally_sync_agent.engine import multi_fy as MF  # noqa: E402
from tally_sync_agent.engine import sync_engine_v2 as E  # noqa: E402

assert AGENT_VERSION == "2.2.3", AGENT_VERSION
for h in list(L.logger.handlers):
    L.logger.removeHandler(h)
fh = logging.FileHandler(Path(agent_dir).parent / "agent_223.log", encoding="utf-8")
L.logger.addHandler(fh)

with open(tally_pkl, "rb") as f:
    tally = pickle.load(f)
SIM = {"now": times[0]}


class SimDatetime(datetime):
    @classmethod
    def now(cls, tz=None):
        n = SIM["now"]
        return n.astimezone(tz) if tz else n.replace(tzinfo=None)


CM.datetime = SimDatetime
E.datetime = SimDatetime
db = Path(agent_dir) / "sync_agent.db"
out = []
for t in times:
    SIM["now"] = t
    tally.now = t
    from tally_sync_agent.core import tally_guard as G
    G._GUARDS.clear()
    mf = MF.MultiFySync(state=None, today=lambda: tally.now.date(), tally_client=tally, backend_client=BackendClient(),
                        checkpoint_manager=CM.CheckpointManager(db), retry_queue=RetryQueue(db),
                        quarantine_store=QuarantineStore(db), data_dir=Path(agent_dir))
    for e in [mf.live] + mf.history:
        g = getattr(e.src, "guard", None)
        if g is not None:
            g.breaker.clock = lambda: SIM["now"].astimezone(timezone.utc).timestamp()
    res = mf.run_cycle()
    out.append({"sim": t.isoformat(), "version": AGENT_VERSION, "status": res.get("status"),
                "vouchers": {k: (res.get("vouchers") or {}).get(k) for k in ("changed_headers", "validated", "checkpoint")},
                "post_dated": (res.get("vouchers") or {}).get("post_dated"), "manifest": bool(res.get("manifest"))})
with open(tally_pkl, "wb") as f:
    pickle.dump(tally, f, protocol=pickle.HIGHEST_PROTOCOL)
print(json.dumps(out))
