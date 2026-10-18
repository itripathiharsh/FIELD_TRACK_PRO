"""
Establish the FIRST Super Admin (one-time, deliberate, run on the server - never exposed as an API).

A Super Admin is an Admin who can additionally manage roles. This script promotes ONE existing,
active ADMIN account that you name explicitly. It never creates accounts, never sets or prints
passwords, and never promotes anybody implicitly.

Rules (all enforced inside one locked transaction):
  * The account is identified by SUPER_ADMIN_BOOTSTRAP_IDENTIFIER (email or mobile number, from the
    environment) AND the same value must be repeated with --confirm-identifier (typo guard).
  * The account must already exist, be active and currently hold the ADMIN role.
    (Create the first admin with scripts/bootstrap_admin.py if none exists yet.)
  * If ANY Super Admin already exists the script refuses. The only exception is the documented
    recovery path: --recovery, env SUPER_ADMIN_RECOVERY_CONFIRM=RESTORE-SUPER-ADMIN-ACCESS, and it is
    still refused while an ACTIVE Super Admin exists (use the Role Management UI for that case).
  * Dry-run by default (repo convention for scripts that write): nothing changes unless --execute is passed.
  * ENVIRONMENT=production additionally requires --i-understand-production.
  * Existing sessions of the promoted account are ended, so it signs in again with its new role.
  * A SUPER_ADMIN_BOOTSTRAP row (no secrets) is written to security_audit_logs.

Usage:
    SUPER_ADMIN_BOOTSTRAP_IDENTIFIER='owner@example.com' \\
        python scripts/bootstrap_super_admin.py --confirm-identifier 'owner@example.com' \\
        --execute [--i-understand-production]

    # recovery (no active Super Admin left):
    SUPER_ADMIN_BOOTSTRAP_IDENTIFIER=... SUPER_ADMIN_RECOVERY_CONFIRM=RESTORE-SUPER-ADMIN-ACCESS \\
        python scripts/bootstrap_super_admin.py --confirm-identifier ... --recovery --execute
"""
from __future__ import annotations

import argparse
import os
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

RECOVERY_PHRASE = "RESTORE-SUPER-ADMIN-ACCESS"
ADVISORY_LOCK_KEY = 7_319_204_551_017  # same key as app.services.admin_security_service.ROLE_ADMIN_ADVISORY_LOCK_KEY


class BootstrapRefused(Exception):
    """The safety rules forbid the promotion. `code` is a stable machine-readable reason."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _mask(identifier: str) -> str:
    ident = identifier.strip()
    if "@" in ident:
        local, domain = ident.split("@", 1)
        return f"{local[:1]}***@{domain}"
    return f"{'*' * max(len(ident) - 4, 0)}{ident[-4:]}"


def bootstrap_super_admin(identifier: str, engine=None, recovery: bool = False, execute: bool = True) -> str:
    """
    Promote the named ADMIN to SUPER_ADMIN. Returns 'promoted', or 'dry-run' when execute=False (every check
    and lock runs, then the transaction is rolled back: nothing is written). Raises BootstrapRefused otherwise.
    """
    from sqlalchemy import create_engine, text

    from app.config import settings

    identifier = identifier.strip()
    if not identifier:
        raise BootstrapRefused("IDENTIFIER_REQUIRED", "An explicit account identifier (email or mobile) is required.")

    if engine is None:
        url = settings.migration_database_url or settings.database_url
        engine = create_engine(url.replace("postgresql+asyncpg://", "postgresql://"))

    is_email = "@" in identifier
    try:
        _promote(engine, text, identifier, is_email, recovery, execute)
    except _DryRun:
        return "dry-run"
    return "promoted"


class _DryRun(Exception):
    pass


def _promote(engine, text, identifier: str, is_email: bool, recovery: bool, execute: bool) -> None:
    with engine.begin() as conn:
        conn.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": ADVISORY_LOCK_KEY})

        super_admins = conn.execute(
            text("SELECT id, is_active FROM users WHERE role::text = 'SUPER_ADMIN' ORDER BY id FOR UPDATE")
        ).all()
        active_super_admins = [r for r in super_admins if r.is_active]
        if super_admins and not recovery:
            raise BootstrapRefused(
                "SUPER_ADMIN_EXISTS",
                "A Super Admin already exists. Use the Role Management screen (as a Super Admin) to promote "
                "others. If every Super Admin is locked out, use --recovery (see --help).",
            )
        if recovery and active_super_admins:
            raise BootstrapRefused(
                "ACTIVE_SUPER_ADMIN_EXISTS",
                "Recovery refused: an ACTIVE Super Admin still exists. Use the Role Management screen instead.",
            )

        if is_email:
            row = conn.execute(
                text("SELECT id, role::text AS role, is_active FROM users WHERE lower(email) = :v FOR UPDATE"),
                {"v": identifier.lower()},
            ).first()
        else:
            row = conn.execute(
                text("SELECT id, role::text AS role, is_active FROM users WHERE mobile_number = :v FOR UPDATE"),
                {"v": identifier},
            ).first()
        if row is None:
            raise BootstrapRefused("ACCOUNT_NOT_FOUND", "No account matches that identifier. Nothing was changed.")
        if not row.is_active:
            raise BootstrapRefused("ACCOUNT_INACTIVE", "The account is disabled. Activate it first. Nothing was changed.")
        if row.role != "ADMIN":
            raise BootstrapRefused(
                "ACCOUNT_NOT_ELIGIBLE",
                f"The account has role {row.role}; only an existing ADMIN can be promoted. Nothing was changed.",
            )

        if not execute:
            raise _DryRun()  # leaves the `with engine.begin()` block -> the transaction is rolled back
        conn.execute(
            text(
                "UPDATE users SET role = 'SUPER_ADMIN', token_version = token_version + 1, updated_at = now() "
                "WHERE id = :id"
            ),
            {"id": row.id},
        )
        conn.execute(
            text("UPDATE refresh_tokens SET revoked = true WHERE user_id = :id AND revoked = false"), {"id": row.id}
        )
        conn.execute(
            text(
                "INSERT INTO security_audit_logs "
                "(id, created_at, event_type, outcome, actor_user_id, target_user_id, previous_role, new_role, reason_code, details) "
                "VALUES (:id, now(), 'SUPER_ADMIN_BOOTSTRAP', 'SUCCESS', NULL, :target, 'ADMIN', 'SUPER_ADMIN', :reason, "
                "CAST(:details AS json))"
            ),
            {
                "id": str(uuid.uuid4()),
                "target": row.id,
                "reason": "RECOVERY" if recovery else "FIRST_SUPER_ADMIN",
                "details": '{"method": "bootstrap_script", "recovery": %s}' % ("true" if recovery else "false"),
            },
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Promote ONE named, existing ADMIN account to SUPER_ADMIN.")
    parser.add_argument("--confirm-identifier", required=True,
                        help="repeat the account email/mobile exactly (must equal SUPER_ADMIN_BOOTSTRAP_IDENTIFIER)")
    parser.add_argument("--execute", action="store_true",
                        help="actually perform the promotion (default is a dry run that only validates)")
    parser.add_argument("--i-understand-production", action="store_true", help="allow running with ENVIRONMENT=production")
    parser.add_argument("--recovery", action="store_true",
                        help="recovery path when NO active Super Admin remains (also needs SUPER_ADMIN_RECOVERY_CONFIRM)")
    args = parser.parse_args(argv)

    from app.config import settings

    if settings.environment == "production" and not args.i_understand_production:
        print("REFUSING: ENVIRONMENT=production. Re-run with --i-understand-production if you really mean it.")
        return 2

    identifier = os.environ.get("SUPER_ADMIN_BOOTSTRAP_IDENTIFIER", "").strip()
    if not identifier:
        print("ERROR: set SUPER_ADMIN_BOOTSTRAP_IDENTIFIER to the email or mobile number of the ADMIN to promote.")
        return 2
    if args.confirm_identifier.strip() != identifier:
        print("ERROR: --confirm-identifier does not match SUPER_ADMIN_BOOTSTRAP_IDENTIFIER. Nothing was changed.")
        return 2
    if args.recovery and os.environ.get("SUPER_ADMIN_RECOVERY_CONFIRM", "") != RECOVERY_PHRASE:
        print(f"ERROR: recovery requires SUPER_ADMIN_RECOVERY_CONFIRM={RECOVERY_PHRASE}. Nothing was changed.")
        return 2

    try:
        outcome = bootstrap_super_admin(identifier, recovery=args.recovery, execute=args.execute)
    except BootstrapRefused as exc:
        print(f"REFUSED [{exc.code}]: {exc}")
        return 1
    if outcome == "dry-run":
        print(f"DRY RUN: {_mask(identifier)} is eligible and would be promoted. Nothing was changed; re-run with --execute.")
        return 0
    print(f"Super Admin established: {_mask(identifier)}. Their existing sessions were ended; they must sign in again.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
