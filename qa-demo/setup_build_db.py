"""Isolated LOCAL test database for the release 3.1 (business scope) backend tests.
  python setup_test_db.py create   drop + create fieldtrackpro_qa_build on the local server, migrate to head
  python setup_test_db.py env      print the env override for pytest (URLs masked)
  python setup_test_db.py drop
Credentials come from the backend's own .env (local server only). fieldtrackpro_dev is never touched.
"""
from __future__ import annotations

import asyncio
import os
import re
import subprocess
import sys
from pathlib import Path

BACKEND = Path(r"F:\Field track pro v2 for test\field track pro\fieldtrackpro-backend")
DB = "fieldtrackpro_qa_build"


def _dotenv() -> dict:
    out = {}
    for line in (BACKEND / ".env").read_text(encoding="utf-8-sig").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip().strip("\"'")
    return out


def test_env() -> dict:
    env = _dotenv()
    app, mig = env["DATABASE_URL"], env.get("MIGRATION_DATABASE_URL") or env["DATABASE_URL"]
    for u in (app, mig):
        host = re.search(r"@([^/]+)/", u).group(1)
        if not host.startswith(("127.0.0.1", "localhost")):
            raise SystemExit(f"refusing: .env points at {host}, not a local server")
    sub = lambda u: u.rsplit("/", 1)[0] + "/" + DB
    return {"DATABASE_URL": sub(app), "MIGRATION_DATABASE_URL": sub(mig), "_ADMIN": mig}


async def _create():
    import asyncpg
    e = test_env()
    owner = re.match(r"postgresql\+asyncpg://([^:]+):", _dotenv()["DATABASE_URL"]).group(1)
    c = await asyncpg.connect(e["_ADMIN"].replace("postgresql+asyncpg://", "postgresql://"))
    try:
        await c.execute(f"SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '{DB}'")
        await c.execute(f"DROP DATABASE IF EXISTS {DB}")
        await c.execute(f'CREATE DATABASE {DB} OWNER "{owner}"')
    finally:
        await c.close()
    c = await asyncpg.connect(e["MIGRATION_DATABASE_URL"].replace("postgresql+asyncpg://", "postgresql://"))
    try:
        await c.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    finally:
        await c.close()


async def _grant():
    import asyncpg
    e = test_env()
    owner = re.match(r"postgresql\+asyncpg://([^:]+):", _dotenv()["DATABASE_URL"]).group(1)
    c = await asyncpg.connect(e["MIGRATION_DATABASE_URL"].replace("postgresql+asyncpg://", "postgresql://"))
    try:
        await c.execute(f'GRANT ALL ON ALL TABLES IN SCHEMA public TO "{owner}"')
        await c.execute(f'GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO "{owner}"')
    finally:
        await c.close()


async def _drop():
    import asyncpg
    e = test_env()
    c = await asyncpg.connect(e["_ADMIN"].replace("postgresql+asyncpg://", "postgresql://"))
    try:
        await c.execute(f"SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '{DB}'")
        await c.execute(f"DROP DATABASE IF EXISTS {DB}")
    finally:
        await c.close()


def main():
    cmd = sys.argv[1]
    if cmd == "create":
        asyncio.run(_create())
        e = test_env()
        env = {**os.environ, "DATABASE_URL": e["DATABASE_URL"], "MIGRATION_DATABASE_URL": e["MIGRATION_DATABASE_URL"],
               "ENVIRONMENT": "dev"}
        r = subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=BACKEND, env=env,
                           capture_output=True, text=True)
        print(r.stdout[-1500:], r.stderr[-3000:])
        if r.returncode:
            raise SystemExit("migration failed")
        asyncio.run(_grant())
        print(f"created and migrated {DB}")
    elif cmd == "env":
        e = test_env()
        for k in ("DATABASE_URL", "MIGRATION_DATABASE_URL"):
            print(k, re.sub(r"(://[^:]+:)[^@]+@", r"\1***@", e[k]))
    elif cmd == "drop":
        asyncio.run(_drop())
        print(f"dropped {DB}")


if __name__ == "__main__":
    main()
