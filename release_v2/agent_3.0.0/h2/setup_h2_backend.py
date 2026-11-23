"""H2 backend: the replay harness's isolated-database setup, pointed at fieldtrackpro_h2 (lock-checked) on port 8766.

    python setup_h2_backend.py create   create + migrate fieldtrackpro_h2, register agent "H2" (org h2);
                                        credentials -> F:\\FT_H2\\backend\\agent.json (never printed)
    python setup_h2_backend.py serve    run uvicorn of the backend checkout (must be 4d0d391) on 127.0.0.1:8766
    python setup_h2_backend.py drop     drop fieldtrackpro_h2 only
"""
import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "harness"))
sys.path.insert(0, str(HERE))
import setup_backend as sb  # noqa: E402
from h2_safety import LOCK, assert_backend_target  # noqa: E402

sb.HARNESS_DB = LOCK["backend_db"]
sb.REGISTER = sb.REGISTER.replace('"name": "HARNESS3", "organization_id": "harness"', '"name": "H2", "organization_id": "h2"') \
                         .replace("harness_admin_", "h2_admin_")
assert '"name": "H2"' in sb.REGISTER
OUT = Path(r"F:\FT_H2\backend")
RELEASE = "4d0d391a331b6db244d9c9668ea9f84c03dc265c"


def _checks():
    env = sb.harness_env()
    assert_backend_target(env["DATABASE_URL"], LOCK["backend_url"])
    assert_backend_target(env["MIGRATION_DATABASE_URL"], LOCK["backend_url"])
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=sb.BACKEND, capture_output=True, text=True).stdout.strip()
    dirty = subprocess.run(["git", "status", "--porcelain"], cwd=sb.BACKEND, capture_output=True, text=True).stdout.strip()
    if head != RELEASE or dirty:
        raise SystemExit(f"REFUSED: backend checkout is {head[:7]} dirty={bool(dirty)}, not a clean {RELEASE[:7]}")
    return env


if __name__ == "__main__":
    cmd = sys.argv[1]
    env = _checks()
    if cmd == "create":
        sb.create(OUT)
    elif cmd == "serve":
        e = {**os.environ, "DATABASE_URL": env["DATABASE_URL"], "MIGRATION_DATABASE_URL": env["MIGRATION_DATABASE_URL"],
             "ENVIRONMENT": "dev"}
        port = LOCK["backend_url"].rsplit(":", 1)[1]
        sys.exit(subprocess.call([sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", port,
                                  "--log-level", "warning"], cwd=sb.BACKEND, env=e))
    elif cmd == "drop":
        asyncio.run(sb._drop_db())
        print("dropped", sb.HARNESS_DB)
