"""
Shared helpers for the operational scripts in this folder.

Scripts must NEVER embed credentials or connection strings. Everything comes
from the environment (or the app settings, which read .env):

  SCRIPT_ADMIN_PASSWORD     password of the admin account a script logs in as
  SCRIPT_EMPLOYEE_PASSWORD  password of the employee/test account a script uses
  SCRIPT_HARSH_PASSWORD     password of the personal test account some scripts use
  DATABASE_URL / MIGRATION_DATABASE_URL   handled by app.config.settings
"""
from __future__ import annotations

import os
import secrets
import sys


def env(name: str) -> str:
    """Return a required environment variable or exit with a clear message (never prints the value)."""
    value = os.environ.get(name)
    if not value:
        sys.exit(f"ERROR: environment variable {name} is required for this script.")
    return value


def api_url() -> str:
    """Backend base URL for scripts that call the HTTP API. Required: no live hostname is baked in."""
    return env("SCRIPT_API_URL").rstrip("/")


def optional_env(name: str) -> str:
    return os.environ.get(name, "").rstrip("/")


def db_url(sync: bool = True) -> str:
    """Database URL from app settings (DATABASE_URL), as a sync (psycopg2/asyncpg) or asyncpg-SQLAlchemy URL."""
    from app.config import settings

    url = settings.database_url
    if sync:
        return url.replace("postgresql+asyncpg://", "postgresql://")
    return url


def random_password(length: int = 14) -> str:
    """A random password that satisfies typical complexity rules (upper, lower, digit, symbol)."""
    return secrets.token_urlsafe(length)[:length] + "aA1!"


def guard_write_script(script_name: str, argv=None) -> None:
    """
    Gate for scripts that write to the database but cannot run inside a roll-back-able
    transaction (async/pool based or API driven). Same safety model as
    destructive_script_main:

      * default: print what the script is, make NO change, exit 0 (dry-run);
      * `--execute` additionally needs env CONFIRM_PURGE_DATABASE=<exact database name>;
      * ENVIRONMENT=production additionally needs `--i-understand-production`.

    Returns only when the script may really write; otherwise it exits.
    """
    import argparse
    from urllib.parse import urlparse

    parser = argparse.ArgumentParser(description=f"{script_name} (dry-run by default).")
    parser.add_argument("--execute", action="store_true", help="really write (default: dry-run, no changes)")
    parser.add_argument("--i-understand-production", action="store_true", help="required when ENVIRONMENT=production")
    args, _ = parser.parse_known_args(argv if argv is not None else sys.argv[1:])

    from app.config import settings

    db_name = urlparse(db_url()).path.lstrip("/")
    if settings.environment == "production" and not args.i_understand_production:
        sys.exit("REFUSING: ENVIRONMENT=production requires --i-understand-production.")
    if not args.execute:
        print(f"{script_name}: DRY-RUN (database={db_name}). Nothing was changed.")
        print("Re-run with --execute and env CONFIRM_PURGE_DATABASE=<database name> to apply.")
        sys.exit(0)
    if os.environ.get("CONFIRM_PURGE_DATABASE") != db_name:
        sys.exit(f"REFUSING: --execute requires env CONFIRM_PURGE_DATABASE set to the exact database name ({db_name!r}).")
    print(f"{script_name}: EXECUTE against database={db_name}")


def destructive_script_main(script_name: str, run_fn, argv=None) -> int:
    """
    Standard entry point for a destructive cleanup script, matching the
    safety model `purge_all_test_data.py` established:

      * DEFAULT IS DRY-RUN: `run_fn(cur)` executes inside a transaction that
        is ROLLED BACK; row counts it prints reflect exactly what WOULD be
        deleted.
      * Real execution needs ALL of: --execute, and env CONFIRM_PURGE_DATABASE
        set to the exact database name being targeted.
      * ENVIRONMENT=production additionally needs --i-understand-production.

    `run_fn` receives an open psycopg2 cursor and performs the deletes
    (no commit/rollback of its own - that's handled here).
    """
    import argparse
    from urllib.parse import urlparse

    import psycopg2

    parser = argparse.ArgumentParser(description=f"{script_name} (dry-run by default).")
    parser.add_argument("--execute", action="store_true", help="really commit (default: dry-run + rollback)")
    parser.add_argument("--i-understand-production", action="store_true", help="required when ENVIRONMENT=production")
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    from app.config import settings

    url = db_url()
    db_name = urlparse(url).path.lstrip("/")

    if settings.environment == "production" and not args.i_understand_production:
        print("REFUSING: ENVIRONMENT=production requires --i-understand-production.")
        return 2
    if args.execute and os.environ.get("CONFIRM_PURGE_DATABASE") != db_name:
        print(f"REFUSING: --execute requires env CONFIRM_PURGE_DATABASE set to the exact database name ({db_name!r}).")
        return 2

    mode = "EXECUTE (will COMMIT)" if args.execute else "DRY-RUN (will ROLL BACK)"
    print("=" * 65)
    print(f"{script_name} - database={db_name} - {mode}")
    print("=" * 65)

    conn = psycopg2.connect(url)
    conn.autocommit = False
    cur = conn.cursor()
    try:
        run_fn(cur)
        if args.execute:
            conn.commit()
            print("COMMITTED: changes applied.")
        else:
            conn.rollback()
            print("DRY-RUN complete: everything rolled back, nothing was changed.")
        return 0
    except Exception as exc:  # noqa: BLE001
        conn.rollback()
        print("ERROR, rolled back:", type(exc).__name__, exc)
        return 1
    finally:
        cur.close()
        conn.close()
