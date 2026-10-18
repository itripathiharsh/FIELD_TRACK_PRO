"""
READ-ONLY pre-migration inspector: which Alembic revision is this database on, and what would `alembic upgrade head` do?

Run it against a database BEFORE migrating it (production included). It never writes: the whole session is a
READ ONLY transaction, it issues SELECTs only, and it refuses to run if the connection is not read-only.

    # URL comes from the environment (never from the command line, never printed):
    CHECK_DATABASE_URL='<sqlalchemy/psycopg2 url of the database to inspect>'  python scripts/preflight_db_revision.py
    # (falls back to MIGRATION_DATABASE_URL, then DATABASE_URL, from the app settings / .env)

It reports:
  * the revision(s) stored in `alembic_version` and whether this repository knows them;
  * the pending migrations, in order, up to the repository head;
  * whether the demo-data purge migration `k4l5m6n7o8p9` has ALREADY run (applied) or is still PENDING, and if pending,
    a preview (row counts only) of what its predicates match in this database;
  * a schema fingerprint (milestone tables present/absent) to catch a stamped-but-not-really-migrated database;
  * row counts of the key business tables (so you know what is at stake).
Exit codes: 0 = ok / informational, 1 = problem found (unknown revision, schema mismatch, pending purge that matches rows),
2 = could not inspect.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

PURGE_REVISION = "k4l5m6n7o8p9"

#: revision -> a table (or table.column) that exists once that revision has been applied. Used only as a cross-check.
MILESTONES: list[tuple[str, str]] = [
    ("z5a6b7c8d9e0", "tally_audit_logs"),
    ("a6b7c8d9e0f1", "requirement_items"),
    ("b7c8d9e0f1a2", "payment_invoice_allocations"),
    ("e0f1a2b3c4d5", "refresh_tokens.rotated_at"),
    ("f1a2b3c4d5e6", "customer_prospects"),
    ("a7b8c9d0e1f2", "outlet_proofs"),
    ("b9c0d1e2f3a4", "security_audit_logs"),
]

KEY_TABLES = ["users", "employees", "customers", "invoices", "payments", "visits", "territories", "areas"]


def load_chain():
    """(ordered list of revisions oldest->head, {rev: down_revision}) from alembic/versions, no DB needed."""
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    backend = Path(__file__).resolve().parent.parent
    cfg = Config(str(backend / "alembic.ini"))
    cfg.set_main_option("script_location", str(backend / "alembic"))
    script = ScriptDirectory.from_config(cfg)
    heads = script.get_heads()
    if len(heads) != 1:
        raise SystemExit(f"repository has {len(heads)} Alembic heads {heads}; resolve before migrating")
    order = [r.revision for r in script.walk_revisions(base="base", head=heads[0])][::-1]
    return order, {r: script.get_revision(r).down_revision for r in order}


def pending_after(order: list[str], current: str | None) -> list[str]:
    if current is None:
        return list(order)
    if current not in order:
        raise ValueError(current)
    return order[order.index(current) + 1:]


def classify_purge(order: list[str], current: str | None) -> str:
    """'applied' if the purge revision is at or below `current`, else 'pending' ('n/a' if the repo lacks it)."""
    if PURGE_REVISION not in order:
        return "n/a"
    if current is None or current not in order:
        return "pending"
    return "applied" if order.index(current) >= order.index(PURGE_REVISION) else "pending"


def _masked(url: str) -> str:
    u = urlparse(url.replace("postgresql+asyncpg://", "postgresql://"))
    return f"{u.hostname}:{u.port or 5432}/{u.path.lstrip('/')} (user {u.username})"


def main() -> int:
    from sqlalchemy import create_engine, text
    from sqlalchemy.exc import SQLAlchemyError

    raw = os.environ.get("CHECK_DATABASE_URL")
    if not raw:
        from app.config import settings

        raw = settings.migration_database_url or settings.database_url
    url = raw.replace("postgresql+asyncpg://", "postgresql://")

    order, _ = load_chain()
    head = order[-1]
    print(f"Repository: {len(order)} migrations, head = {head}")
    print(f"Database  : {_masked(url)}")

    try:
        engine = create_engine(url, connect_args={"connect_timeout": 10, "options": "-c default_transaction_read_only=on -c statement_timeout=30000"})
        conn = engine.connect()
    except SQLAlchemyError as exc:
        print(f"CANNOT CONNECT: {type(exc).__name__}")
        return 2

    problems = 0
    with conn:
        conn.execute(text("SET TRANSACTION READ ONLY"))
        if conn.execute(text("SHOW transaction_read_only")).scalar() != "on":
            print("REFUSING: session is not read-only")
            return 2

        def has_table(name: str) -> bool:
            return bool(conn.execute(text("SELECT to_regclass(:t) IS NOT NULL"), {"t": f"public.{name}"}).scalar())

        def has_column(table: str, col: str) -> bool:
            return bool(conn.execute(text("SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name=:t AND column_name=:c"),
                                     {"t": table, "c": col}).first())

        if not has_table("alembic_version"):
            print("alembic_version: MISSING - this database has never been migrated by Alembic (empty or hand-built).")
            tables = conn.execute(text(
                "SELECT count(*) FROM information_schema.tables WHERE table_schema='public' AND table_type='BASE TABLE' "
                "AND table_name NOT IN ('spatial_ref_sys')")).scalar()   # spatial_ref_sys belongs to the PostGIS extension
            print(f"public tables present: {tables}")
            current = None
            if tables:
                print("PROBLEM: tables exist but no alembic_version - do NOT run `alembic upgrade head` blindly.")
                problems += 1
        else:
            versions = [r[0] for r in conn.execute(text("SELECT version_num FROM alembic_version"))]
            print(f"alembic_version: {versions}")
            if len(versions) != 1:
                print("PROBLEM: expected exactly one stored revision")
                problems += 1
            current = versions[0] if versions else None
            if current and current not in order:
                print(f"PROBLEM: revision {current} is not in this repository - the database is ahead of / unrelated to this code.")
                print("         Do NOT migrate. Deploy the code that contains that revision, or investigate.")
                return 1

        pend = pending_after(order, current)
        print(f"\nStored revision : {current or '(none)'}")
        print(f"Pending to head : {len(pend)}" + ("" if not pend else "  ->  " + " -> ".join(pend)))
        purge = classify_purge(order, current)
        print(f"Demo-data purge ({PURGE_REVISION}): {purge.upper()}")

        # schema fingerprint cross-check
        print("\nSchema fingerprint (revision claims vs. what actually exists):")
        for rev, what in MILESTONES:
            if rev not in order:
                continue
            exists = has_column(*what.split(".")) if "." in what else has_table(what)
            should = current is not None and current in order and order.index(current) >= order.index(rev)
            flag = "ok" if exists == should else "MISMATCH"
            if flag == "MISMATCH":
                problems += 1
            print(f"   {rev}  {what:34s} exists={exists!s:5s} expected={should!s:5s} {flag}")

        # row counts
        print("\nRow counts (what is at stake):")
        for t in KEY_TABLES:
            if has_table(t):
                print(f"   {t:14s} {conn.execute(text(f'SELECT count(*) FROM {t}')).scalar()}")

        # preview of the purge, only when it has NOT run yet
        if purge == "pending":
            print("\nPREVIEW of what the pending purge migration would delete here (counts only; nothing is deleted):")
            probes = {
                "payments with demo id (77777777-*)": "SELECT count(*) FROM payments WHERE id::text LIKE '77777777-%'",
                "invoices with demo id (66666666-*)": "SELECT count(*) FROM invoices WHERE id::text LIKE '66666666-%'",
                "visits with demo id (44444444-*)": "SELECT count(*) FROM visits WHERE id::text LIKE '44444444-%'",
                "customers with demo id (33333333-*)": "SELECT count(*) FROM customers WHERE id::text LIKE '33333333-%'",
                "employees whose code is NOT between 11001 and 11030": "SELECT count(*) FROM employees WHERE employee_code NOT BETWEEN '11001' AND '11030'",
                "users: non-sgrgservices, non-admin, no employee profile": (
                    "SELECT count(*) FROM users WHERE email NOT LIKE '%@sgrgservices.com' AND email != 'admin@fieldtrack.test' "
                    "AND role::text != 'ADMIN' AND id NOT IN (SELECT user_id FROM employees WHERE user_id IS NOT NULL)"),
                "territories (demo ids / names)": "SELECT count(*) FROM territories WHERE id::text LIKE '11111111-%'",
            }
            matched = 0
            for label, sql in probes.items():
                table = sql.split("FROM ")[1].split()[0]
                if not has_table(table):
                    print(f"   {label:62s} (table absent)")
                    continue
                n = conn.execute(text(sql)).scalar()
                matched += int(n or 0)
                print(f"   {label:62s} {n}")
            if matched:
                print("\n   >>> The purge WOULD delete rows here. If any are real data, do not run it: stamp past it deliberately or fix the data first.")
                problems += 1
            else:
                print("\n   (matches nothing - safe to run on this database)")

    print("\nRESULT:", "OK to proceed (review the lists above)" if not problems else f"{problems} problem(s) - resolve before migrating")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
