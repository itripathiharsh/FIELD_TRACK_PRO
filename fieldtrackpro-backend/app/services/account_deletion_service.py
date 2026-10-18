"""
Self-service account deletion (Google Play "account deletion" requirement).

Policy: the login identity and personal contact/identity data are removed or
anonymised; business and financial records (visits, payments, invoices,
orders, requirements, audit logs) are RETAINED for legal / accounting
retention, linked to the now anonymised, inactive employee profile. The
departing employee's own visit photos and signatures are also deleted from
storage (personally-identifying images) - GPS check-in timestamps, visit
counts and payment amounts stay intact.
"""
from __future__ import annotations

import logging
import secrets
import uuid

from sqlalchemy import delete, func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import get_current_request_id
from app.core.datetime_utils import get_ist_now, get_ist_today_range
from app.core.rate_limiter import login_rate_limiter, throttle_key
from app.core.security import hash_password, verify_password
from app.exceptions.custom import BaseAPIException
from app.models.employee import Employee
from app.models.monthly_visit_plan import PlannedVisit, PlannedVisitStatus
from app.models.notification import Notification, NotificationType
from app.models.user import Role, User, ADMIN_ROLES
from app.models.user_device import UserDevice
from app.models.visit import Visit, VisitStatus
from app.models.visit_media import VisitMedia
from app.models.visit_signature import VisitSignature
from app.repositories.token_repo import TokenRepository
from app.services.storage_service import storage_service

logger = logging.getLogger("fieldtrackpro")

ANONYMISED_NAME = "Deleted User"

# Constant key for the transaction-scoped advisory lock that serialises admin self-deletions.
# Row locks alone are not enough: the count of OTHER active admins is derived from rows that a
# concurrent transaction may be about to deactivate. With this lock, two simultaneous admin
# deletions run strictly one after the other and the second one re-counts after the first commits.
ADMIN_DELETE_ADVISORY_LOCK_KEY = 7_319_204_551_002


async def _verify_reauth_password(user: User, password: str, session: AsyncSession) -> None:
    """
    Re-authentication for the destructive action. Wrong attempts share the login failure
    budget (5 / 15 min per account) so a stolen unlocked session cannot brute-force the
    password through this endpoint; the lock releases with a correct password.
    """
    key = throttle_key("acctdelete", "user", str(user.id))
    try:
        await login_rate_limiter.check_allowed(key, session)
    except BaseAPIException:
        await session.rollback()
        raise
    if not verify_password(password, user.password_hash):
        await session.rollback()
        await login_rate_limiter.record_failure(key, session)
        raise BaseAPIException(
            status_code=401,
            detail="Incorrect password.",
            error_code="AUTH_INVALID_PASSWORD",
        )
    await login_rate_limiter.record_success(key, session)


async def delete_own_account(
    current_user: User, reason: str | None, password: str, session: AsyncSession
) -> None:
    # Re-authentication first (rate-limited; commits its own bookkeeping row), THEN the locks:
    # the advisory/row locks below are transaction-scoped and must not be released by that commit.
    await _verify_reauth_password(current_user, password, session)

    if current_user.is_admin:
        # A Super Admin deleting themselves must leave another active SUPER_ADMIN behind; an Admin
        # must leave another active administrator (ADMIN or SUPER_ADMIN) behind.
        protected_roles = (
            (Role.SUPER_ADMIN,) if current_user.role == Role.SUPER_ADMIN else ADMIN_ROLES
        )
        last_admin_detail = (
            "You are the last active Super Admin. Promote another Super Admin before deleting this account."
            if current_user.role == Role.SUPER_ADMIN
            else "You are the last active administrator. Create or activate another admin before deleting this account."
        )
        last_admin_code = (
            "LAST_SUPER_ADMIN_CANNOT_DELETE" if current_user.role == Role.SUPER_ADMIN else "LAST_ADMIN_CANNOT_DELETE"
        )
        # Serialise ALL admin self-deletions (released automatically at commit/rollback).
        await session.execute(
            text("SELECT pg_advisory_xact_lock(:k)"), {"k": ADMIN_DELETE_ADVISORY_LOCK_KEY}
        )
        # Role changes / deactivations of privileged accounts use their own advisory lock; take it too so
        # a concurrent demotion cannot slip between this count and the commit.
        from app.services.admin_security_service import ROLE_ADMIN_ADVISORY_LOCK_KEY

        await session.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": ROLE_ADMIN_ADVISORY_LOCK_KEY})
        # Lock every active admin row, in one statement, in a stable order (by id), then count
        # the OTHERS under the lock. The loser of a race blocks on the advisory lock until the
        # winner commits and then re-counts against the post-commit active-admin set - closing
        # the TOCTOU race where both could see "someone else is still active" and both proceed.
        admin_rows = (
            await session.execute(
                select(User)
                .where(User.role.in_(protected_roles), User.is_active.is_(True))
                .order_by(User.id)
                .with_for_update()
            )
        ).scalars().all()
        user = next((u for u in admin_rows if u.id == current_user.id), None)
        if user is None:
            await session.rollback()
            raise BaseAPIException(
                status_code=409,
                detail="Account is already inactive.",
                error_code="ACCOUNT_ALREADY_INACTIVE",
            )
        other_admins = sum(1 for u2 in admin_rows if u2.id != user.id)
        if other_admins == 0:
            await session.rollback()
            raise BaseAPIException(
                status_code=409,
                detail=last_admin_detail,
                error_code=last_admin_code,
            )
    else:
        # Re-load inside this session and lock the row so concurrent calls serialise.
        user = (
            await session.execute(
                select(User).where(User.id == current_user.id).with_for_update()
            )
        ).scalar_one()

    # 1. Revoke every session and device so the account is unusable immediately
    #    (inactive users are also rejected on every authenticated request).
    revoked = await TokenRepository(session).revoke_all_for_user(user.id)
    devices = (
        await session.execute(delete(UserDevice).where(UserDevice.user_id == user.id))
    ).rowcount or 0
    await session.execute(delete(Notification).where(Notification.user_id == user.id))

    # 2. Anonymise personal data; keep the rows (FK targets for retained records).
    anon = uuid.uuid4().hex[:12]
    employee = (
        await session.execute(select(Employee).where(Employee.user_id == user.id))
    ).scalar_one_or_none()
    deleted_employee_name = employee.full_name if employee is not None else None
    pending_visits = 0
    cancelled_planned = 0
    if employee is not None:
        # Follow-up work for admins. `visits` has no CANCELLED status (and
        # employee_id is NOT NULL), so future PENDING visits are left in place
        # and reported to admins for reassignment. Future PLANNED planned-visits
        # do have a CANCELLED status and are cancelled.
        start_utc, _ = get_ist_today_range()
        pending_visits = (
            await session.execute(
                select(func.count(Visit.id)).where(
                    Visit.employee_id == employee.id,
                    Visit.status == VisitStatus.PENDING,
                    Visit.scheduled_at >= start_utc,
                )
            )
        ).scalar_one()
        cancelled_planned = (
            await session.execute(
                update(PlannedVisit)
                .where(
                    PlannedVisit.employee_id == employee.id,
                    PlannedVisit.status == PlannedVisitStatus.PLANNED,
                    PlannedVisit.planned_date >= get_ist_now().date(),
                )
                .values(status=PlannedVisitStatus.CANCELLED)
            )
        ).rowcount or 0

    if employee is not None:
        employee.full_name = ANONYMISED_NAME
        employee.cug = None
        employee.date_of_birth = None
        employee.address = None
        employee.father_name = None
        employee.mother_name = None
        employee.aadhaar_no = None
        employee.pan_no = None

    user.is_active = False
    user.email = f"deleted-{anon}@deleted.invalid"
    user.mobile_number = None
    user.password_hash = hash_password(secrets.token_urlsafe(32))

    await session.commit()

    # 2b. Delete the departing employee's own visit photos/signatures from
    # storage (personally-identifying images). Visit rows, GPS timestamps,
    # and payment amounts are untouched - only the image bytes go.
    media_files_deleted = 0
    if employee is not None:
        media_files_deleted = await _purge_employee_visit_media(employee.id, session)

    # 2c. Tell active admins to reassign the deleted employee's open visits.
    total_open = pending_visits + cancelled_planned
    if employee is not None and total_open > 0:
        await _notify_admins_reassign(
            employee, deleted_employee_name or "Employee", pending_visits, cancelled_planned, session
        )

    # 3. Structured audit event (no PII: ids only; reason is free text, truncated).
    clean_reason = " ".join((reason or "").split())[:200] or "-"
    logger.info(
        "event=account_deleted request_id=%s user_id=%s role=%s employee_id=%s "
        "refresh_tokens_revoked=%s devices_removed=%s media_files_deleted=%s reason=%r",
        get_current_request_id(),
        user.id,
        user.role.value,
        employee.id if employee else "-",
        revoked,
        devices,
        media_files_deleted,
        clean_reason,
    )


async def _purge_employee_visit_media(employee_id: uuid.UUID, session: AsyncSession) -> int:
    """
    Best-effort delete of the departing employee's own visit photos/signatures
    from storage. The data rows (and their GPS/visit timestamps) are kept -
    only the personally-identifying image bytes are removed, so the storage
    key is overwritten with a redacted sentinel either way. Never raises.
    """
    deleted = 0
    media_rows = (
        await session.execute(
            select(VisitMedia)
            .join(Visit, Visit.id == VisitMedia.visit_id)
            .where(Visit.employee_id == employee_id)
        )
    ).scalars().all()
    sig_rows = (
        await session.execute(
            select(VisitSignature)
            .join(Visit, Visit.id == VisitSignature.visit_id)
            .where(Visit.employee_id == employee_id)
        )
    ).scalars().all()

    for media in media_rows:
        try:
            await storage_service.delete(media.storage_key)
        except Exception:
            logger.warning(
                "event=account_deleted_media_purge_failed media_id=%s storage_key=%s",
                media.id,
                media.storage_key,
                exc_info=True,
            )
        media.storage_key = f"deleted/visit_media/{media.id}"
        media.original_filename = None
        deleted += 1

    for sig in sig_rows:
        try:
            await storage_service.delete(sig.storage_key)
        except Exception:
            logger.warning(
                "event=account_deleted_media_purge_failed signature_id=%s storage_key=%s",
                sig.id,
                sig.storage_key,
                exc_info=True,
            )
        sig.storage_key = f"deleted/visit_signature/{sig.id}"
        deleted += 1

    if media_rows or sig_rows:
        await session.commit()
    return deleted


async def _notify_admins_reassign(
    employee: Employee,
    employee_name: str,
    pending_visits: int,
    cancelled_planned: int,
    session: AsyncSession,
) -> None:
    """In-app notification for every active admin; never fails the deletion."""
    from app.services.notification_service import notification_service

    total = pending_visits + cancelled_planned
    message = (
        f"Reassign visits of deleted employee {employee_name}: {total} visits "
        f"({pending_visits} scheduled, {cancelled_planned} planned visits cancelled)"
    )
    try:
        admin_ids = list(
            (
                await session.execute(
                    select(User.id).where(User.role.in_(ADMIN_ROLES), User.is_active.is_(True))
                )
            ).scalars().all()
        )
        for admin_id in admin_ids:
            await notification_service.create_notification(
                user_id=admin_id,
                notification_type=NotificationType.EMPLOYEE_SCHEDULE_CHANGED,
                title="Reassign visits of deleted employee",
                message=message,
                session=session,
            )
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("event=account_deleted_admin_notify_failed employee_id=%s error=%s", employee.id, exc)
