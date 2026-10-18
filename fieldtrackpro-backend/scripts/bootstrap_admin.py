"""
Safe, env-driven admin bootstrap (replaces the old seed_demo_data.py).

Creates the FIRST admin account only. Behaviour:
  * ADMIN_BOOTSTRAP_EMAIL and ADMIN_BOOTSTRAP_PASSWORD come from the environment.
  * If a user with that email already exists the script does NOTHING (it never
    resets an existing admin's password and never re-activates/modifies a user).
  * Refuses to run when ENVIRONMENT=production unless --i-understand-production
    is passed (production admins should be created once, deliberately).
  * The password is never printed or logged.

Usage:
    ADMIN_BOOTSTRAP_EMAIL=you@example.com ADMIN_BOOTSTRAP_PASSWORD='...' \\
        python scripts/bootstrap_admin.py [--i-understand-production]
"""
from __future__ import annotations

import argparse
import os
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

MIN_PASSWORD_LENGTH = 12


def bootstrap(email: str, password: str, engine=None) -> str:
    """Create the admin if absent. Returns 'created' or 'exists'. Never modifies an existing user."""
    from sqlalchemy import create_engine, text

    from app.config import settings
    from app.core.security import hash_password

    email = email.strip().lower()
    if engine is None:
        engine = create_engine(settings.database_url.replace("postgresql+asyncpg://", "postgresql://"))
    with engine.begin() as conn:
        existing = conn.execute(text("SELECT 1 FROM users WHERE lower(email) = :e"), {"e": email}).first()
        if existing:
            return "exists"
        conn.execute(
            text(
                "INSERT INTO users (id, email, password_hash, role, is_active, created_at, updated_at) "
                "VALUES (:id, :email, :pw, 'ADMIN', true, now(), now())"
            ),
            {"id": str(uuid.uuid4()), "email": email, "pw": hash_password(password)},
        )
    return "created"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create the initial admin account from environment variables.")
    parser.add_argument("--i-understand-production", action="store_true", help="allow running with ENVIRONMENT=production")
    args = parser.parse_args(argv)

    from app.config import settings

    if settings.environment == "production" and not args.i_understand_production:
        print("REFUSING: ENVIRONMENT=production. Re-run with --i-understand-production if you really mean it.")
        return 2

    email = os.environ.get("ADMIN_BOOTSTRAP_EMAIL", "").strip()
    password = os.environ.get("ADMIN_BOOTSTRAP_PASSWORD", "")
    if not email or "@" not in email:
        print("ERROR: ADMIN_BOOTSTRAP_EMAIL must be set to a valid email address.")
        return 2
    if len(password) < MIN_PASSWORD_LENGTH:
        print(f"ERROR: ADMIN_BOOTSTRAP_PASSWORD must be set and at least {MIN_PASSWORD_LENGTH} characters.")
        return 2

    result = bootstrap(email, password)
    if result == "exists":
        print("Admin already exists - nothing changed (existing passwords are never reset by this script).")
    else:
        print("Admin account created.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
