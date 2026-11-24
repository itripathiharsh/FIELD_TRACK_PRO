"""Throwaway LOCAL databases for the admin-dashboard audit fixes (never production, never fieldtrackpro_dev).

  python scripts/local_audit_db.py create <db>        drop + create <db> on the local server, migrate to head
  python scripts/local_audit_db.py clone <src> <db>   drop + create <db> as a copy of the local <src>, migrate to head
  python scripts/local_audit_db.py env <db>           print `export` lines for DATABASE_URL / MIGRATION_DATABASE_URL
  python scripts/local_audit_db.py drop <db>

Credentials are read from the main checkout's backend .env (local server only) and are never printed.
Allowed database names start with `fieldtrackpro_audit_` (or are the read-only clone source `fieldtrackpro_qa_build`).
"""
from __future__ import annotations

import asyncio
import os
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
DOTENV = Path(r"F:\Field track pro v2 for test\field track pro\fieldtrackpro-backend\.env")


def _dotenv() -> dict:
    out = {}
    for line in DOTENV.read_text(encoding="utf-8-sig").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip().strip("\"'")
    return out


def _check(db: str) -> str:
    if not re.fullmatch(r"fieldtrackpro_audit_[a-z0-9_]+", db):
        raise SystemExit(f"refusing: {db!r} is not a fieldtrackpro_audit_* database")
    return db


def urls(db: str) -> dict:
    env = _dotenv()
    app, mig = env["DATABASE_URL"], env.get("MIGRATION_DATABASE_URL") or env["DATABASE_URL"]
    for u in (app, mig):
        host = re.search(r"@([^/]+)/", u).group(1)
        if not host.startswith(("127.0.0.1", "localhost")):
            raise SystemExit(f"refusing: .env points at {host}, not a local server")
    sub = lambda u: u.rsplit("/", 1)[0] + "/" + db
    return {"DATABASE_URL": sub(app), "MIGRATION_DATABASE_URL": sub(mig), "_ADMIN": mig}


def _pg(u: str) -> str:
    return u.replace("postgresql+asyncpg://", "postgresql://")


async def _recreate(db: str, template: str | None) -> None:
    import asyncpg
    e = urls(db)
    owner = re.match(r"postgresql\+asyncpg://([^:]+):", _dotenv()["DATABASE_URL"]).group(1)
    c = await asyncpg.connect(_pg(e["_ADMIN"]))
    try:
        for name in filter(None, (db, template)):
            await c.execute(f"SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '{name}'")
        await c.execute(f"DROP DATABASE IF EXISTS {db}")
        tpl = f" TEMPLATE {template}" if template else ""
        await c.execute(f'CREATE DATABASE {db} OWNER "{owner}"{tpl}')
    finally:
        await c.close()
    c = await asyncpg.connect(_pg(e["MIGRATION_DATABASE_URL"]))
    try:
        await c.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    finally:
        await c.close()


async def _grant(db: str) -> None:
    import asyncpg
    e = urls(db)
    owner = re.match(r"postgresql\+asyncpg://([^:]+):", _dotenv()["DATABASE_URL"]).group(1)
    c = await asyncpg.connect(_pg(e["MIGRATION_DATABASE_URL"]))
    try:
        await c.execute(f'GRANT ALL ON ALL TABLES IN SCHEMA public TO "{owner}"')
        await c.execute(f'GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO "{owner}"')
    finally:
        await c.close()


async def _drop(db: str) -> None:
    import asyncpg
    c = await asyncpg.connect(_pg(urls(db)["_ADMIN"]))
    try:
        await c.execute(f"SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '{db}'")
        await c.execute(f"DROP DATABASE IF EXISTS {db}")
    finally:
        await c.close()


def _migrate(db: str) -> None:
    e = urls(db)
    env = {**os.environ, "DATABASE_URL": e["DATABASE_URL"], "MIGRATION_DATABASE_URL": e["MIGRATION_DATABASE_URL"],
           "ENVIRONMENT": "dev", "JWT_SECRET": os.environ.get("JWT_SECRET", "local-audit-only-jwt-secret-0123456789abcdef")}
    r = subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=HERE, env=env,
                       capture_output=True, text=True)
    print(r.stdout[-800:], r.stderr[-1500:])
    if r.returncode:
        raise SystemExit("migration failed")


def main() -> None:
    cmd = sys.argv[1]
    if cmd == "create":
        db = _check(sys.argv[2])
        asyncio.run(_recreate(db, None))
        _migrate(db)
        asyncio.run(_grant(db))
        print(f"created and migrated {db}")
    elif cmd == "clone":
        src, db = sys.argv[2], _check(sys.argv[3])
        if src != "fieldtrackpro_qa_build" and not src.startswith("fieldtrackpro_audit_"):
            raise SystemExit("refusing: clone source must be the fictional QA build database")
        asyncio.run(_recreate(db, src))
        _migrate(db)
        asyncio.run(_grant(db))
        print(f"cloned {src} -> {db} and migrated")
    elif cmd == "env":
        e = urls(_check(sys.argv[2]))
        print(f"export DATABASE_URL='{e['DATABASE_URL']}' MIGRATION_DATABASE_URL='{e['MIGRATION_DATABASE_URL']}'")
    elif cmd == "drop":
        db = _check(sys.argv[2])
        asyncio.run(_drop(db))
        print(f"dropped {db}")


if __name__ == "__main__":
    main()
