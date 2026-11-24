"""
Per-outlet FOS change made by an admin in FieldTrack (release 3.3), and its relation to Tally.

Tally stays the system of record: the FOS of an outlet is the parent group of its customer ledger. An admin
change in FieldTrack therefore:
  1. replaces the outlet's employee assignment at once (source ADMIN), audited with who / when / old / new;
  2. records a FosLedgerMove: the ledger, the group it is in now (from_group) and the group of the new FOS that
     it should move to (to_group, when that can be determined without guessing);
  3. is PROTECTED from the Tally FOS sync until Tally agrees:
       - Tally still shows the old group        -> the admin assignment is kept (held, "awaiting Tally");
       - Tally now gives the outlet the new FOS -> CONFIRMED, the sync takes ownership again;
       - Tally moved the ledger elsewhere        -> CONFLICT, flagged in the Change Log, nothing overwritten.
The ledger move itself is done by the accountant in Tally, or - only when TALLY_FOS_WRITEBACK_ENABLED and an agent
that can alter ledger masters is installed - offered to the Tally agent. Vouchers and amounts are never touched.
"""
from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.customer import Customer
from app.models.employee_customer_assignment import EmployeeCustomerAssignment
from app.models.tally_debtor_ledger import TallyDebtorLedger
from app.models.tally_fos import (
    GROUP_MAPPED, MOVE_CANCELLED, MOVE_CONFIRMED, MOVE_CONFLICT, MOVE_PENDING, MOVE_SUPERSEDED, OPEN_MOVE_STATUSES,
    SRC_ADMIN, ST_ADMIN_PENDING_TALLY, ST_ASSIGNED, WB_NOT_SENT, WB_QUEUED,
    FosAssignmentAudit, FosLedgerMove, TallyFosGroup,
)
from app.models.user import User
from app.services import fos_logic as L

log = logging.getLogger(__name__)

#: Brand -> words that name it inside a Tally group name ("Raunak ZBR", "Sahil Gautam (Usha)").
BRAND_GROUP_TOKENS = {
    "usha": {"usha"}, "zebronics": {"zbr", "zebronics", "zebronic"}, "vu": {"vu"}, "rr": {"rr"},
    "singer": {"singer"}, "oppo": {"oppo"}, "philips": {"ph", "philips"}, "samsung": {"samsung"},
}


class FosEditError(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _tokens(name: str) -> set[str]:
    import re
    return set(re.findall(r"[a-z]+", (name or "").lower()))


def groups_label(ledgers: list) -> str:
    return ", ".join(sorted({(l.parent_group or "").strip() or "(no group)" for l in ledgers}))


def pick_target_group(employee_groups: list[str], ledger_brand: Optional[str]) -> Optional[str]:
    """The Tally group the ledger should move to, or None when it cannot be told without guessing:
    the employee's only mapped group, or the one of their groups that names the ledger's brand."""
    if len(employee_groups) == 1:
        return employee_groups[0]
    if not ledger_brand:
        return None
    toks = BRAND_GROUP_TOKENS.get(ledger_brand.strip().lower(), {ledger_brand.strip().lower()})
    hits = [g for g in employee_groups if _tokens(g) & toks]
    return hits[0] if len(hits) == 1 else None


async def _ledgers(session: AsyncSession, customer_id: uuid.UUID) -> list[TallyDebtorLedger]:
    from app.models.tally_debtor_ledger import SCOPE_DISTRIBUTION
    from sqlalchemy import or_
    return list((await session.execute(
        select(TallyDebtorLedger).where(
            TallyDebtorLedger.customer_id == customer_id,
            TallyDebtorLedger.is_debtor.is_not(False),
            or_(TallyDebtorLedger.business_scope.is_(None), TallyDebtorLedger.business_scope == SCOPE_DISTRIBUTION),
        ).order_by(TallyDebtorLedger.is_primary.desc(), TallyDebtorLedger.name)
    )).scalars().all())


async def open_move(session: AsyncSession, customer_id: uuid.UUID) -> Optional[FosLedgerMove]:
    return (await session.execute(
        select(FosLedgerMove).where(FosLedgerMove.customer_id == customer_id, FosLedgerMove.status.in_(OPEN_MOVE_STATUSES))
    )).scalar_one_or_none()


async def change_outlet_fos(
    session: AsyncSession, customer_id: uuid.UUID, employee_id: uuid.UUID, user: User, *,
    expected_employee_ids: Optional[list[uuid.UUID]] = None, note: Optional[str] = None,
    idempotency_key: Optional[str] = None,
) -> FosLedgerMove:
    """Assign `employee_id` as the outlet's only FOS. The caller commits. See module docstring."""
    from app.services.fos_sync_service import _employees, assignable_employees, _names

    customer = (await session.execute(
        select(Customer).where(Customer.id == customer_id).with_for_update(of=Customer.__table__))).unique().scalar_one_or_none()
    if customer is None:
        raise FosEditError(404, "OUTLET_NOT_FOUND", "Outlet not found")
    emps = await _employees(session)
    if employee_id not in {i for i, _ in assignable_employees(emps)}:
        raise FosEditError(422, "EMPLOYEE_NOT_ASSIGNABLE", "Choose an active field employee")

    rows = list((await session.execute(
        select(EmployeeCustomerAssignment).where(EmployeeCustomerAssignment.customer_id == customer_id)
    )).scalars().all())
    current = sorted({r.employee_id for r in rows}, key=str)
    key = idempotency_key or hashlib.sha256(
        f"{customer_id}|{employee_id}|{','.join(map(str, current))}".encode()).hexdigest()[:64]
    existing = (await session.execute(select(FosLedgerMove).where(FosLedgerMove.idempotency_key == key))).scalar_one_or_none()
    if existing is not None:
        return existing  # a retry of the same request: nothing is changed twice
    if expected_employee_ids is not None and set(expected_employee_ids) != set(current):
        raise FosEditError(409, "FOS_CHANGED_MEANWHILE",
                           "The FOS of this outlet changed since the page was loaded. Reload and try again.")
    if current == [employee_id]:
        raise FosEditError(409, "FOS_UNCHANGED", "This employee is already the outlet's FOS")

    ledgers = await _ledgers(session, customer_id)
    led = ledgers[0] if ledgers else None
    emp_groups = sorted(g for (g,) in (await session.execute(
        select(TallyFosGroup.group_name).where(TallyFosGroup.status == GROUP_MAPPED, TallyFosGroup.employee_id == employee_id)
    )).all())
    to_group = pick_target_group(emp_groups, led.effective_brand if led else None) if len(ledgers) == 1 else None

    now = _now()
    prev = await open_move(session, customer_id)
    if prev is not None:
        prev.status, prev.resolved_at = MOVE_SUPERSEDED, now
        await session.flush()

    for r in rows:
        await session.delete(r)
    await session.flush()
    session.add(EmployeeCustomerAssignment(
        employee_id=employee_id, customer_id=customer_id, created_by=user.id, source=SRC_ADMIN,
        tally_group=to_group, tally_ledger_guid=led.tally_guid if led else None, synced_at=None))

    if not ledgers:
        status, wb, detail_tally = MOVE_CONFIRMED, WB_NOT_SENT, "outlet has no Tally ledger: nothing to move in Tally"
    else:
        status = MOVE_PENDING
        wb = WB_QUEUED if (settings.tally_fos_writeback_enabled and to_group and len(ledgers) == 1) else WB_NOT_SENT
        where = f'to "{to_group}"' if to_group else "to a group of the new FOS (the group could not be chosen without guessing)"
        how = "offered to the Tally agent" if wb == WB_QUEUED else "to be done by the accountant in Tally"
        detail_tally = (f'Tally ledger "{led.name}" ({len(ledgers)} ledger(s)) must move from "{groups_label(ledgers)}" '
                        f"{where}: {how}")
    move = FosLedgerMove(
        customer_id=customer_id, ledger_id=led.id if led else None, tally_ledger_guid=led.tally_guid if led else None,
        ledger_name=led.name if led else None, from_group=groups_label(ledgers) if ledgers else None, to_group=to_group,
        previous_employee_ids=[str(i) for i in current], employee_id=employee_id, status=status, writeback_status=wb,
        idempotency_key=key, requested_by=user.id, note=(note or None) and note[:300],
        resolved_at=now if status == MOVE_CONFIRMED else None,
    )
    session.add(move)
    customer.fos_status = ST_ADMIN_PENDING_TALLY if ledgers else ST_ASSIGNED
    session.add(FosAssignmentAudit(
        customer_id=customer_id, customer_name=customer.name[:150],
        previous_employee_id=current[0] if len(current) == 1 else None, previous_fos=_names(current, emps) or None,
        new_employee_id=employee_id, new_fos=_names([employee_id], emps) or None,
        action="ADMIN_CHANGE", source="ADMIN", tally_group=to_group, tally_ledger_guid=led.tally_guid if led else None,
        result="APPLIED", detail=(f"by {user.email}" + (f": {note}" if note else "") + f". {detail_tally}")[:900]))
    await session.flush()

    # Android access follows the assignment rows; tell both employees (best effort, never undoes the change).
    session.info.setdefault("fos_post_commit_notes", []).extend(
        [(employee_id, "Outlet assigned to you", f"{customer.name} is now in your outlet list.")]
        + [(eid, "Outlet moved to another FOS", f"{customer.name} is no longer in your outlet list.")
           for eid in current if eid != employee_id])
    return move


async def send_post_commit_notes(session: AsyncSession) -> None:
    from app.models.employee import Employee
    from app.models.notification import NotificationType
    from app.services.notification_service import notification_service
    notes = session.info.pop("fos_post_commit_notes", [])
    for emp_id, title, message in notes:
        try:
            uid = (await session.execute(select(Employee.user_id).where(Employee.id == emp_id))).scalar_one_or_none()
            if uid:
                await notification_service.create_notification(
                    user_id=uid, notification_type=NotificationType.REMINDER, title=title, message=message, session=session)
        except Exception:  # noqa: BLE001
            log.warning("FOS change notification failed for employee %s", emp_id, exc_info=True)


def evaluate_open_move(move: FosLedgerMove, ledgers: list[L.LedgerRef], plan: L.OutletPlan) -> str:
    """What the Tally sync should do for an outlet with an open admin move:
    'confirm' (Tally now gives the outlet the new FOS), 'hold' (Tally still shows the old group) or 'conflict'."""
    wanted = set(plan.wanted.keys())
    if move.employee_id is not None and wanted == {move.employee_id} and not plan.unmapped_groups:
        return "confirm"
    current = ", ".join(sorted({l.group_name for l in ledgers})) if ledgers else None
    if (current or None) == (move.from_group or None):
        return "hold"
    return "conflict"


async def resolve_conflict(session: AsyncSession, move_id: uuid.UUID, keep: str, user: User) -> FosLedgerMove:
    """Admin decision on an open move: keep='ADMIN' waits for Tally again from the ledger's current group;
    keep='TALLY' cancels the admin change and lets the next sync apply Tally's FOS. Audited. Caller commits."""
    move = await session.get(FosLedgerMove, move_id)
    if move is None or move.status not in OPEN_MOVE_STATUSES:
        raise FosEditError(404, "MOVE_NOT_OPEN", "There is no open FOS change to resolve")
    customer = await session.get(Customer, move.customer_id)
    ledgers = await _ledgers(session, move.customer_id)
    now = _now()
    if keep == "ADMIN":
        move.status, move.from_group = MOVE_PENDING, groups_label(ledgers) if ledgers else None
        detail = "kept the FieldTrack FOS; waiting for the ledger move in Tally from its current group"
    elif keep == "TALLY":
        move.status, move.resolved_at = MOVE_CANCELLED, now
        for r in (await session.execute(select(EmployeeCustomerAssignment).where(
                EmployeeCustomerAssignment.customer_id == move.customer_id,
                EmployeeCustomerAssignment.source == SRC_ADMIN))).scalars().all():
            await session.delete(r)
        detail = "cancelled the FieldTrack change; Tally's FOS applies"
    else:
        raise FosEditError(422, "BAD_DECISION", "keep must be ADMIN or TALLY")
    session.add(FosAssignmentAudit(
        customer_id=move.customer_id, customer_name=(customer.name if customer else None),
        action="CONFLICT_RESOLVED", source="ADMIN", tally_group=move.to_group, tally_ledger_guid=move.tally_ledger_guid,
        result="APPLIED", detail=f"by {user.email}: {detail}"))
    await session.flush()
    return move
