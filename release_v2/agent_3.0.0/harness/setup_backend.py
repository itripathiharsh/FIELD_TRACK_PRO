"""Harness backend: an ISOLATED local PostgreSQL database for the replay (never staging, never production).

  python setup_backend.py create  <data_dir>   drop + create database fieldtrackpro_harness3 (local server), migrate
                                               to head, create a harness admin and register the harness agent
                                               (credentials written to <data_dir>/agent.json, never printed)
  python setup_backend.py env                  print the environment for uvicorn / alembic (URLs masked)
  python setup_backend.py drop                 drop the harness database

The local server's credentials come from the backend's own .env (the migration role is used only to create / drop
this one database). Nothing in the developer database fieldtrackpro_dev is read or written.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import subprocess
import sys
from pathlib import Path

BACKEND = Path(r"F:\Field track pro v2 for test\field track pro\fieldtrackpro-backend")
HARNESS_DB = "fieldtrackpro_harness3"


def _dotenv() -> dict:
    out = {}
    for line in (BACKEND / ".env").read_text(encoding="utf-8-sig").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip().strip("\"'")
    return out


def harness_env() -> dict:
    env = _dotenv()
    app = env["DATABASE_URL"]
    mig = env.get("MIGRATION_DATABASE_URL") or app
    for u in (app, mig):
        host = re.search(r"@([^/]+)/", u).group(1)
        if not host.startswith(("127.0.0.1", "localhost")):
            raise SystemExit(f"refusing: the backend .env points at {host}, not a local server")
    sub = lambda u: u.rsplit("/", 1)[0] + "/" + HARNESS_DB
    return {"DATABASE_URL": sub(app), "MIGRATION_DATABASE_URL": sub(mig), "_ADMIN_URL": mig}


async def _create_db():
    import asyncpg
    env = harness_env()
    admin = env["_ADMIN_URL"].replace("postgresql+asyncpg://", "postgresql://")
    owner = re.match(r"postgresql\+asyncpg://([^:]+):", _dotenv()["DATABASE_URL"]).group(1)
    conn = await asyncpg.connect(admin)
    try:
        await conn.execute(f"SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '{HARNESS_DB}'")
        await conn.execute(f"DROP DATABASE IF EXISTS {HARNESS_DB}")
        await conn.execute(f'CREATE DATABASE {HARNESS_DB} OWNER "{owner}"')
    finally:
        await conn.close()


async def _grant():
    """The migration role created the tables; the application role gets the same rights it has on the dev database."""
    import asyncpg
    env = harness_env()
    owner = re.match(r"postgresql\+asyncpg://([^:]+):", _dotenv()["DATABASE_URL"]).group(1)
    conn = await asyncpg.connect(env["MIGRATION_DATABASE_URL"].replace("postgresql+asyncpg://", "postgresql://"))
    try:
        await conn.execute(f'GRANT ALL ON ALL TABLES IN SCHEMA public TO "{owner}"')
        await conn.execute(f'GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO "{owner}"')
    finally:
        await conn.close()


async def _drop_db():
    import asyncpg
    env = harness_env()
    conn = await asyncpg.connect(env["_ADMIN_URL"].replace("postgresql+asyncpg://", "postgresql://"))
    try:
        await conn.execute(f"SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '{HARNESS_DB}'")
        await conn.execute(f"DROP DATABASE IF EXISTS {HARNESS_DB}")
    finally:
        await conn.close()


REGISTER = r'''
import asyncio, json, sys, uuid
sys.path.insert(0, ".")
from httpx import ASGITransport, AsyncClient
from app.main import app
from app.database import AsyncSessionLocal
from app.models.user import User, Role
from app.core.security import hash_password, create_access_token

async def main(out):
    async with AsyncSessionLocal() as s:
        admin = User(email=f"harness_admin_{uuid.uuid4().hex[:6]}@fieldtrack.test", password_hash=hash_password(uuid.uuid4().hex),
                     role=Role.ADMIN, is_active=True)
        s.add(admin); await s.commit(); aid = admin.id
    h = {"Authorization": f"Bearer {create_access_token(subject=str(aid), role=Role.ADMIN.value)}"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://harness") as c:
        r = await c.post("/api/v1/integrations/tally/agents", json={"name": "HARNESS3", "organization_id": "harness"}, headers=h)
        assert r.status_code == 201, r.text
        json.dump({"agent_id": r.json()["agent"]["id"], "agent_key": r.json()["api_key"], "admin_id": str(aid)},
                  open(out, "w"))
asyncio.run(main(sys.argv[1]))
'''


def create(data_dir: Path) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    asyncio.run(_create_db())
    env = {**os.environ, **{k: v for k, v in harness_env().items() if not k.startswith("_")}}
    r = subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=BACKEND, env=env, capture_output=True, text=True)
    if r.returncode:
        raise SystemExit("alembic failed:\n" + r.stderr[-3000:])
    print("migrated:", [l for l in r.stderr.splitlines() if "Running upgrade" in l][-1:])
    asyncio.run(_grant())
    script = data_dir / "_register.py"
    script.write_text(REGISTER, encoding="utf-8")
    r = subprocess.run([sys.executable, str(script), str(data_dir / "agent.json")], cwd=BACKEND, env=env,
                       capture_output=True, text=True)
    script.unlink()
    if r.returncode:
        raise SystemExit("agent registration failed:\n" + r.stderr[-3000:])
    print("harness agent registered (credentials in agent.json, not printed)")


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "create":
        create(Path(sys.argv[2]))
    elif cmd == "drop":
        asyncio.run(_drop_db())
        print("dropped", HARNESS_DB)
    elif cmd == "env":
        for k, v in harness_env().items():
            print(k, re.sub(r":[^:@/]+@", ":***@", v))
