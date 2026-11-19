"""
Administrative security operations: admin-initiated password reset and Super Admin role management.

Permission model (enforced here, in the backend, against CURRENT database state - never trusting the
caller's token claims or anything the client sends about roles):

    SUPER_ADMIN  may reset EMPLOYEE and ADMIN passwords, change roles, promote/demote Super Admins
                 (with re-authentication + explicit confirmation), deactivate any account except the
                 last active Super Admin.
    ADMIN        may reset EMPLOYEE passwords only, create EMPLOYEE accounts only; can never change roles
                 or touch a Super Admin account.
    EMPLOYEE     none of the above.

Concurrency: every operation that can change who holds privileged roles takes a transaction-scoped
Postgres advisory lock (`ROLE_ADMIN_ADVISORY_LOCK_KEY`) and then row locks (`FOR UPDATE`, ordered by id)
on the affected users plus every active Super Admin, so two simultaneous requests cannot both pass the
"is there still another Super Admin?" check.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import delete, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.rate_limiter import LoginRateLimiter, login_rate_limiter, throttle_key
from app.core.security import generate_temporary_password, hash_password, verify_password
from app.exceptions.custom import BaseAPIException
from app.models.employee import Employee
from app.models.login_attempt import LoginAttempt
from app.models.user import ADMIN_ROLES, Role, User
from app.repositories.token_repo import TokenRepository
from app.services import security_audit_service as audit

logger = logging.getLogger("fieldtrackpro")

#: Serialises every operation that can change which accounts hold ADMIN / SUPER_ADMIN.
ROLE_ADMIN_ADVISORY_LOCK_KEY = 7_319_204_551_017

#: Admin password resets issued per acting administrator per 15 minutes (abuse / runaway-UI guard).
admin_reset_limiter = LoginRateLimiter(max_attempts=30)

#: Allowed role transitions. EMPLOYEE <-> ADMIN <-> SUPER_ADMIN, one step at a time: nobody jumps
#: straight from EMPLOYEE to SUPER_ADMIN or back.
ALLOWED_ROLE_TRANSITIONS: set[tuple[Role, Role]] = {
    (Role.EMPLOYEE, Role.ADMIN),
    (Role.ADMIN, Role.EMPLOYEE),
    (Role.ADMIN, Role.SUPER_ADMIN),
    (Role.SUPER_ADMIN, Role.ADMIN),
}


def _forbidden(detail: str, code: str) -> BaseAPIException:
    return BaseAPIException(status_code=403, detail=detail, error_code=code)


async def _deny(
    session: AsyncSession,
    event_type: str,
    exc: BaseAPIException,
    *,
    actor_user_id: uuid.UUID | None,
    target_user_id: uuid.UUID | None,
    previous_role: str | None = None,
    new_role: str | None = None,
    client_ip: str | None = None,
    outcome: str = "DENIED",
) -> BaseAPIException:
    """Roll back the business transaction, persist an audit row for the refusal, return the exception to raise."""
    await session.rollback()
    await audit.record_denied(
        session,
        event_type,
        exc.error_code,
        outcome=outcome,
        actor_user_id=actor_user_id,
        target_user_id=target_user_id,
        previous_role=previous_role,
        new_role=new_role,
        client_ip=client_ip,
    )
    return exc


async def _lock_users(session: AsyncSession, ids: list[uuid.UUID], include_active_super_admins: bool) -> dict[uuid.UUID, User]:
    """Take the advisory lock, then row-lock the given users (+ every active Super Admin), ordered by id."""
    await session.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": ROLE_ADMIN_ADVISORY_LOCK_KEY})
    cond = User.id.in_(ids)
    if include_active_super_admins:
        cond = or_(cond, (User.role == Role.SUPER_ADMIN) & (User.is_active.is_(True)))
    rows = (
        await session.execute(
            select(User).where(cond).order_by(User.id).with_for_update().execution_options(populate_existing=True)
        )
    ).scalars().all()
    return {u.id: u for u in rows}


# ---------------------------------------------------------------------------
# Account creation guard
# ---------------------------------------------------------------------------

async def assert_may_assign_role_on_create(actor: User, role: Role, session: AsyncSession, client_ip: str | None = None) -> None:
    """
    Creating an account with a privileged role is itself a grant of privilege:
      * SUPER_ADMIN can never be created through the API (bootstrap script / role-change workflow only);
      * ADMIN may only be created by a Super Admin;
      * ACCOUNTANT (read-only finance access) may only be created by a Super Admin.
    """
    if role == Role.SUPER_ADMIN:
        exc = _forbidden(
            "Super Admin accounts cannot be created directly. Create an Admin, then promote it.",
            "ROLE_ASSIGNMENT_FORBIDDEN",
        )
    elif role == Role.ADMIN and not actor.is_super_admin:
        exc = _forbidden("Only a Super Admin can create an Admin account.", "ROLE_ASSIGNMENT_FORBIDDEN")
    elif role == Role.ACCOUNTANT and not actor.is_super_admin:
        exc = _forbidden("Only a Super Admin can create an Accountant account.", "ROLE_ASSIGNMENT_FORBIDDEN")
    else:
        return
    raise await _deny(
        session, "USER_CREATE_PRIVILEGED", exc,
        actor_user_id=actor.id, target_user_id=None, new_role=role.value, client_ip=client_ip,
    )


# ---------------------------------------------------------------------------
# Admin-initiated password reset
# ---------------------------------------------------------------------------

async def admin_reset_employee_password(
    actor: User, employee_id: uuid.UUID, session: AsyncSession, client_ip: str | None = None
) -> dict[str, Any]:
    """
    Generate a single-use temporary password for an employee's account.

    The plaintext is returned ONCE in the result (to be shown to the acting admin) and is never
    persisted or logged: only its bcrypt hash and an expiry are stored. Every existing session of the
    target is killed (refresh tokens revoked, token_version bumped) and the account is put in the
    forced-password-change state, which is enforced server-side until a new password is chosen.
    """
    actor_id = actor.id
    # Throttle first (commits its own bookkeeping row, so it must precede the row locks below).
    await admin_reset_limiter.hit(throttle_key("adminreset", "actor", str(actor_id)), session)

    employee = (await session.execute(select(Employee).where(Employee.id == employee_id))).scalar_one_or_none()
    if employee is None:
        raise BaseAPIException(status_code=404, detail="Employee profile not found", error_code="EMPLOYEE_NOT_FOUND")

    locked = await _lock_users(session, [actor_id, employee.user_id], include_active_super_admins=False)
    fresh_actor = locked.get(actor_id)
    target = locked.get(employee.user_id)
    if target is None:
        await session.rollback()
        raise BaseAPIException(status_code=404, detail="Employee profile not found", error_code="EMPLOYEE_NOT_FOUND")
    target_id = target.id
    target_role = target.role

    # Authorise against the CURRENT database state of the actor.
    if fresh_actor is None or not fresh_actor.is_active or not fresh_actor.is_admin:
        raise await _deny(
            session, "ADMIN_PASSWORD_RESET",
            _forbidden("Insufficient permissions", "FORBIDDEN"),
            actor_user_id=actor_id, target_user_id=target_id, client_ip=client_ip,
        )
    if target_id == actor_id:
        raise await _deny(
            session, "ADMIN_PASSWORD_RESET",
            _forbidden("You cannot reset your own password here. Use Change Password.", "SELF_PASSWORD_RESET_FORBIDDEN"),
            actor_user_id=actor_id, target_user_id=target_id, client_ip=client_ip,
        )
    if target_role == Role.SUPER_ADMIN:
        raise await _deny(
            session, "ADMIN_PASSWORD_RESET",
            _forbidden("A Super Admin password cannot be reset by another account.", "TARGET_PRIVILEGE_TOO_HIGH"),
            actor_user_id=actor_id, target_user_id=target_id, client_ip=client_ip,
        )
    if target_role == Role.ADMIN and not fresh_actor.is_super_admin:
        raise await _deny(
            session, "ADMIN_PASSWORD_RESET",
            _forbidden("Only a Super Admin can reset an Admin's password.", "TARGET_PRIVILEGE_TOO_HIGH"),
            actor_user_id=actor_id, target_user_id=target_id, client_ip=client_ip,
        )
    if not target.is_active:
        raise await _deny(
            session, "ADMIN_PASSWORD_RESET",
            BaseAPIException(status_code=409, detail="This account is disabled. Activate it before resetting the password.",
                             error_code="ACCOUNT_INACTIVE"),
            actor_user_id=actor_id, target_user_id=target_id, client_ip=client_ip, outcome="FAILED",
        )

    temp_password = generate_temporary_password()
    expires_at = datetime.now(tz=timezone.utc) + timedelta(minutes=settings.temp_password_expiry_minutes)

    target.password_hash = hash_password(temp_password)
    target.temp_password_expires_at = expires_at
    target.token_version = int(target.token_version or 0) + 1
    session.add(target)

    # Re-fetch the employee under lock so the flag write cannot interleave with a concurrent change.
    emp_locked = (
        await session.execute(
            select(Employee).where(Employee.id == employee_id).with_for_update().execution_options(populate_existing=True)
        )
    ).scalar_one()
    emp_locked.must_change_password = True
    session.add(emp_locked)

    sessions_revoked = await TokenRepository(session).revoke_all_for_user(target_id)
    # An admin reset must also lift a sign-in lockout on the account (the whole point of a reset).
    identifiers = [i.strip().lower() for i in (target.email, target.mobile_number) if i]
    if identifiers:
        await session.execute(delete(LoginAttempt).where(LoginAttempt.identifier.in_(identifiers)))

    audit.record(
        session, "ADMIN_PASSWORD_RESET", "SUCCESS",
        actor_user_id=actor_id, target_user_id=target_id, client_ip=client_ip,
        details={
            "target_role": target_role.value,
            "sessions_revoked": int(sessions_revoked or 0),
            "access_tokens_invalidated": True,
            "expires_in_minutes": settings.temp_password_expiry_minutes,
        },
    )
    await session.commit()

    return {
        "employee_id": employee_id,
        "user_id": target_id,
        "temporary_password": temp_password,
        "expires_at": expires_at,
        "expires_in_minutes": settings.temp_password_expiry_minutes,
    }


# ---------------------------------------------------------------------------
# Role management (Super Admin)
# ---------------------------------------------------------------------------

async def _reauthenticate(actor: User, password: str, session: AsyncSession) -> bool:
    """
    Re-verify the acting Super Admin's own password for a sensitive operation. Wrong attempts share a
    rate-limit budget (5 / 15 min). Returns False on a wrong password (caller audits + raises).
    """
    key = throttle_key("rolechange", "user", str(actor.id))
    try:
        await login_rate_limiter.check_allowed(key, session)
    except BaseAPIException:
        await session.rollback()
        raise
    if not verify_password(password, actor.password_hash):
        await session.rollback()
        await login_rate_limiter.record_failure(key, session)
        return False
    await login_rate_limiter.record_success(key, session)
    return True


async def change_user_role(
    actor: User,
    target_user_id: uuid.UUID,
    new_role: Role,
    current_password: str,
    confirm_privileged: bool,
    session: AsyncSession,
    client_ip: str | None = None,
) -> User:
    """
    Change an account's role. Super Admin only; every rule below is enforced against locked,
    current database state inside one transaction.
    """
    actor_id = actor.id
    actor_hash_user = actor  # for password verification (hash already loaded this request)

    # Cheap authority check up front so an Admin/Employee never reaches re-auth or locks.
    if not actor.is_super_admin:
        raise await _deny(
            session, "ROLE_CHANGE",
            _forbidden("Only a Super Admin can change roles.", "SUPER_ADMIN_REQUIRED"),
            actor_user_id=actor_id, target_user_id=target_user_id, new_role=new_role.value, client_ip=client_ip,
        )

    if not await _reauthenticate(actor_hash_user, current_password, session):
        await audit.record_denied(
            session, "ROLE_CHANGE", "AUTH_INVALID_PASSWORD",
            actor_user_id=actor_id, target_user_id=target_user_id, new_role=new_role.value, client_ip=client_ip,
        )
        raise BaseAPIException(status_code=401, detail="Incorrect password.", error_code="AUTH_INVALID_PASSWORD")

    locked = await _lock_users(session, [actor_id, target_user_id], include_active_super_admins=True)
    fresh_actor = locked.get(actor_id)
    target = locked.get(target_user_id)

    if fresh_actor is None or not fresh_actor.is_active or fresh_actor.role != Role.SUPER_ADMIN:
        raise await _deny(
            session, "ROLE_CHANGE",
            _forbidden("Only a Super Admin can change roles.", "SUPER_ADMIN_REQUIRED"),
            actor_user_id=actor_id, target_user_id=target_user_id, new_role=new_role.value, client_ip=client_ip,
        )
    if target is None:
        await session.rollback()
        raise BaseAPIException(status_code=404, detail="User not found", error_code="USER_NOT_FOUND")

    previous_role = target.role

    def deny(exc: BaseAPIException, outcome: str = "DENIED"):
        return _deny(
            session, "ROLE_CHANGE", exc,
            actor_user_id=actor_id, target_user_id=target_user_id,
            previous_role=previous_role.value, new_role=new_role.value, client_ip=client_ip, outcome=outcome,
        )

    if new_role == previous_role:
        raise await deny(BaseAPIException(status_code=409, detail=f"The account already has the {new_role.value} role.",
                                          error_code="ROLE_UNCHANGED"), outcome="FAILED")
    if (previous_role, new_role) not in ALLOWED_ROLE_TRANSITIONS:
        raise await deny(BaseAPIException(
            status_code=422,
            detail=f"Changing {previous_role.value} to {new_role.value} directly is not allowed. "
                   "Roles change one step at a time: Employee ↔ Admin ↔ Super Admin.",
            error_code="INVALID_ROLE_TRANSITION"))

    involves_super_admin = Role.SUPER_ADMIN in (previous_role, new_role)
    if involves_super_admin and not confirm_privileged:
        raise await deny(BaseAPIException(
            status_code=422,
            detail="Changing Super Admin privileges requires explicit confirmation.",
            error_code="CONFIRMATION_REQUIRED"))

    if new_role in ADMIN_ROLES and not target.is_active:
        raise await deny(BaseAPIException(status_code=409, detail="Activate this account before promoting it.",
                                          error_code="ACCOUNT_INACTIVE"), outcome="FAILED")

    if previous_role == Role.SUPER_ADMIN and target.is_active:
        remaining = sum(1 for u in locked.values() if u.role == Role.SUPER_ADMIN and u.is_active and u.id != target.id)
        if remaining == 0:
            raise await deny(BaseAPIException(
                status_code=409,
                detail="This is the last active Super Admin. Promote another Super Admin before demoting this one.",
                error_code="LAST_SUPER_ADMIN"))

    target.role = new_role
    target.token_version = int(target.token_version or 0) + 1
    session.add(target)
    revoked = await TokenRepository(session).revoke_all_for_user(target.id)

    audit.record(
        session, "ROLE_CHANGE", "SUCCESS",
        actor_user_id=actor_id, target_user_id=target.id,
        previous_role=previous_role.value, new_role=new_role.value, client_ip=client_ip,
        details={"self_change": actor_id == target.id, "sessions_revoked": int(revoked or 0), "privileged": involves_super_admin},
    )
    await session.commit()
    await session.refresh(target)  # server-side updated_at is expired by the UPDATE; reload before serialising
    return target


# ---------------------------------------------------------------------------
# Deactivation / activation guard
# ---------------------------------------------------------------------------

async def set_user_active(
    actor: User, user_id: uuid.UUID, active: bool, session: AsyncSession, client_ip: str | None = None
) -> User:
    """
    Enable/disable an account with Super Admin protections:
      * only a Super Admin may deactivate/activate a Super Admin account;
      * the last active Super Admin can never be deactivated.
    """
    actor_id = actor.id
    event = "ACCOUNT_ACTIVATED" if active else "ACCOUNT_DEACTIVATED"
    locked = await _lock_users(session, [actor_id, user_id], include_active_super_admins=True)
    fresh_actor = locked.get(actor_id)
    target = locked.get(user_id)
    if target is None:
        await session.rollback()
        raise BaseAPIException(status_code=404, detail="User not found", error_code="USER_NOT_FOUND")
    if fresh_actor is None or not fresh_actor.is_active or not fresh_actor.is_admin:
        raise await _deny(session, event, _forbidden("Insufficient permissions", "FORBIDDEN"),
                          actor_user_id=actor_id, target_user_id=user_id, client_ip=client_ip)

    target_role = target.role
    if target_role == Role.SUPER_ADMIN:
        if not fresh_actor.is_super_admin:
            raise await _deny(
                session, event, _forbidden("Only a Super Admin can change a Super Admin account.", "SUPER_ADMIN_REQUIRED"),
                actor_user_id=actor_id, target_user_id=user_id, previous_role=target_role.value, client_ip=client_ip,
            )
        if not active and target.is_active:
            remaining = sum(1 for u in locked.values() if u.role == Role.SUPER_ADMIN and u.is_active and u.id != target.id)
            if remaining == 0:
                raise await _deny(
                    session, event,
                    BaseAPIException(status_code=409,
                                     detail="This is the last active Super Admin and cannot be deactivated.",
                                     error_code="LAST_SUPER_ADMIN"),
                    actor_user_id=actor_id, target_user_id=user_id, previous_role=target_role.value, client_ip=client_ip,
                )

    changed = target.is_active != active
    target.is_active = active
    session.add(target)
    revoked = 0
    if not active:
        target.token_version = int(target.token_version or 0) + 1
        revoked = await TokenRepository(session).revoke_all_for_user(target.id)

    if changed and target_role in ADMIN_ROLES:
        audit.record(
            session, event, "SUCCESS",
            actor_user_id=actor_id, target_user_id=target.id, previous_role=target_role.value, client_ip=client_ip,
            details={"sessions_revoked": int(revoked or 0)},
        )
    await session.commit()
    await session.refresh(target)
    return target
