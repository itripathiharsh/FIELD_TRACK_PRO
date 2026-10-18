"""
READ-ONLY production readiness check. Prints PASS/FAIL per check, exits 1 if any FAIL.

Never prints secret values or connection strings - only variable NAMES and counts.
All database access runs inside a READ ONLY transaction.

Usage (against the database named by DATABASE_URL / .env):
    python scripts/verify_production_readiness.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

EXPECTED_STAFF = 30
EXPECTED_TERRITORIES = 55
EXPECTED_AREAS = 465
MIN_OUTLETS = 1631

BASE_REQUIRED_VARS = [
    "ENVIRONMENT",
    "DATABASE_URL",
    "JWT_SECRET",
    "MEDIA_SIGNING_SECRET",
    "CORS_ALLOWED_ORIGINS",
    "STORAGE_PROVIDER",
    "SMS_PROVIDER",
    "SMTP_HOST",
]
MINIO_REQUIRED_VARS = ["MINIO_ENDPOINT", "MINIO_ACCESS_KEY", "MINIO_SECRET_KEY", "MINIO_BUCKET"]


class Report:
    def __init__(self) -> None:
        self.failed = 0

    def check(self, name: str, ok: bool, detail: str = "") -> None:
        if not ok:
            self.failed += 1
        print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" - {detail}" if detail else ""))


def _present(name: str, settings) -> bool:
    """A variable is present if it is in the process environment or was loaded from .env (names only)."""
    return name in os.environ or name.lower() in settings.model_fields_set


def run_checks(settings, conn_exec, head_revision: str | None) -> Report:
    """
    conn_exec(sql, params=None) -> list[tuple]; separated out so the checks are unit-testable.
    """
    r = Report()
    env = (settings.environment or "").lower()
    r.check("ENVIRONMENT is 'production'", env == "production", f"ENVIRONMENT={env!r}")

    required = list(BASE_REQUIRED_VARS)
    if (settings.storage_provider or "").upper() == "MINIO":
        required += MINIO_REQUIRED_VARS
    missing = [v for v in required if not _present(v, settings)]
    r.check("required environment variables present", not missing, f"missing: {', '.join(missing)}" if missing else "")

    r.check(
        "storage provider is not LOCAL (ephemeral disk on Render)",
        (settings.storage_provider or "").upper() != "LOCAL",
        f"STORAGE_PROVIDER={(settings.storage_provider or '').upper()}",
    )
    r.check(
        "SMS provider is not mock",
        (settings.sms_provider or "").lower() != "mock",
        f"SMS_PROVIDER={(settings.sms_provider or '').lower()}",
    )

    rows = conn_exec("SELECT version_num FROM alembic_version")
    current = {x[0] for x in rows}
    r.check(
        "alembic current == head",
        head_revision is not None and current == {head_revision},
        f"current={sorted(current)} head={head_revision}",
    )

    labels = {x[0] for x in conn_exec(
        "SELECT e.enumlabel FROM pg_enum e JOIN pg_type t ON t.oid = e.enumtypid WHERE t.typname = 'role_enum'"
    )}
    r.check("role_enum values == {ADMIN, EMPLOYEE}", labels == {"ADMIN", "EMPLOYEE"}, f"found={sorted(labels)}")

    n = conn_exec("SELECT count(*) FROM users WHERE email ILIKE '%@fieldtrack.test' OR email ILIKE 'emp_wb_%'")[0][0]
    r.check("no automated/test users (*@fieldtrack.test, emp_wb_*)", n == 0, f"found={n}")

    n = conn_exec("SELECT count(*) FROM employees WHERE employee_code ILIKE 'REP-%'")[0][0]
    r.check("no automated REP-* employees", n == 0, f"found={n}")

    n = conn_exec("SELECT count(*) FROM customers WHERE outlet_code = 'CURR-GPS-001'")[0][0]
    r.check("no CURR-GPS-001 mock outlet", n == 0, f"found={n}")

    staff = conn_exec("SELECT count(*) FROM employees WHERE employee_code ~ '^110(0[1-9]|[12][0-9]|30)$'")[0][0]
    total_emp = conn_exec("SELECT count(*) FROM employees")[0][0]
    r.check(f"real staff 11001-11030 == {EXPECTED_STAFF}", staff == EXPECTED_STAFF and total_emp == EXPECTED_STAFF,
            f"real={staff} total_employees={total_emp}")

    outlets = conn_exec("SELECT count(*) FROM customers")[0][0]
    r.check(f"outlets >= {MIN_OUTLETS}", outlets >= MIN_OUTLETS, f"found={outlets}")

    terr = conn_exec("SELECT count(*) FROM territories")[0][0]
    r.check(f"territories == {EXPECTED_TERRITORIES}", terr == EXPECTED_TERRITORIES, f"found={terr}")

    areas = conn_exec("SELECT count(*) FROM areas")[0][0]
    r.check(f"areas == {EXPECTED_AREAS}", areas == EXPECTED_AREAS, f"found={areas}")
    return r


def _alembic_head() -> str | None:
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    cfg = Config(str(Path(__file__).resolve().parent.parent / "alembic.ini"))
    cfg.set_main_option("script_location", str(Path(__file__).resolve().parent.parent / "alembic"))
    heads = ScriptDirectory.from_config(cfg).get_heads()
    return heads[0] if len(heads) == 1 else None


def main() -> int:
    import psycopg2

    from app.config import settings

    url = settings.database_url.replace("postgresql+asyncpg://", "postgresql://")
    conn = psycopg2.connect(url)
    try:
        conn.set_session(readonly=True, autocommit=False)
        cur = conn.cursor()

        def conn_exec(sql, params=None):
            cur.execute(sql, params)
            return cur.fetchall()

        report = run_checks(settings, conn_exec, _alembic_head())
    finally:
        conn.rollback()
        conn.close()

    print("-" * 60)
    print("RESULT:", "ALL CHECKS PASSED" if report.failed == 0 else f"{report.failed} CHECK(S) FAILED")
    return 0 if report.failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
