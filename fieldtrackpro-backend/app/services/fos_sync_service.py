"""
Tally -> FieldTrack FOS assignment synchronisation (database layer). Rules live in fos_logic.py.

Tally is the source of truth: an outlet's FOS is the employee its ledger group is mapped to. This module
  * discovers the ledger groups (tally_fos_groups) and suggests an employee for each - suggestions only,
  * plans / applies the per-outlet changes to employee_customer_assignments (idempotent: a second run changes nothing),
  * writes an audit row for every change and a run row for every run,
  * builds the reconciliation report (what would change, what conflicts) without writing anything.

Nothing here is called with writes enabled unless settings.tally_fos_sync_enabled is true (see apply_enabled);
group discovery and the dry-run report always work.
"""
from __future__ import annotations

import logging
import uuid
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any, Iterable, Optional

from sqlalchemy import and_, false as sa_false, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.customer import Customer
from app.models.employee import Employee
from app.models.employee_customer_assignment import EmployeeCustomerAssignment
from app.models.tally_debtor_ledger import SCOPE_DISTRIBUTION, TallyDebtorLedger
from app.models.tally_fos import (
    GROUP_MAPPED, GROUP_NOT_FOS, GROUP_UNMAPPED, SRC_TALLY,
    ST_ASSIGNED, ST_CONFLICT, ST_MULTIPLE, ST_NO_TALLY, ST_UNASSIGNED, ST_UNMAPPED_GROUP,
    FosAssignmentAudit, FosSyncRun, TallyFosGroup,
)
from app.models.user import Role, User
from app.services import fos_logic as L

log = logging.getLogger(__name__)

NO_GROUP = "(no group)"
REPORT_ROW_CAP = 3000


def _now() -> datetime:
    return datetime.now(timezone.utc)


def apply_enabled() -> bool:
    return bool(settings.tally_fos_sync_enabled)


def legacy_policy() -> str:
    p = (settings.tally_fos_legacy_policy or "").strip().upper()
    return p if p in (L.POLICY_REPORT_ONLY, L.POLICY_TALLY_WINS) else L.POLICY_REPORT_ONLY


# ---------------------------------------------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------------------------------------------

def _outlet_visible():
    """Same visibility as every outlet list: not a non-debtor, not merged into another outlet."""
    return and_(Customer.tally_is_debtor.is_not(False), Customer.merged_into_customer_id.is_(None))


async def _employees(session: AsyncSession) -> dict[uuid.UUID, dict]:
    rows = (await session.execute(
        select(Employee.id, Employee.full_name, User.role, User.is_active).join(User, User.id == Employee.user_id)
    )).all()
    return {r.id: {"name": r.full_name, "role": r.role, "active": bool(r.is_active)} for r in rows}


def assignable_employees(emps: dict[uuid.UUID, dict]) -> list[tuple[uuid.UUID, str]]:
    """Employees an admin may map a Tally group to: active field staff and admins who also work outlets."""
    ok = (Role.EMPLOYEE, Role.ADMIN, Role.SUPER_ADMIN)
    return [(eid, e["name"]) for eid, e in emps.items() if e["active"] and e["role"] in ok]


async def _ledgers_by_customer(session: AsyncSession, customer_ids: Optional[Iterable[uuid.UUID]] = None) -> dict[uuid.UUID, list[L.LedgerRef]]:
    """In-scope Tally debtor ledgers per outlet (hidden / retired / non-debtor ledgers do not carry a FOS)."""
    stmt = select(TallyDebtorLedger.customer_id, TallyDebtorLedger.tally_guid, TallyDebtorLedger.parent_group,
                  TallyDebtorLedger.is_primary).where(
        TallyDebtorLedger.is_debtor.is_not(False),
        or_(TallyDebtorLedger.business_scope.is_(None), TallyDebtorLedger.business_scope == SCOPE_DISTRIBUTION),
    )
    if customer_ids is not None:
        ids = list(customer_ids)
        if not ids:
            return {}
        stmt = stmt.where(TallyDebtorLedger.customer_id.in_(ids))
    out: dict[uuid.UUID, list[L.LedgerRef]] = defaultdict(list)
    for cid, guid, grp, primary in (await session.execute(stmt.order_by(TallyDebtorLedger.is_primary.desc(), TallyDebtorLedger.name))).all():
        out[cid].append(L.LedgerRef(guid=guid, group_name=(grp or "").strip() or NO_GROUP))
    return out


async def _rules(session: AsyncSession) -> tuple[dict[str, L.GroupRule], dict[str, TallyFosGroup]]:
    groups = (await session.execute(select(TallyFosGroup))).scalars().all()
    rules = {g.group_key: L.GroupRule(g.status, g.employee_id) for g in groups}
    return rules, {g.group_key: g for g in groups}


# ---------------------------------------------------------------------------------------------------------------
# Group discovery and mapping
# ---------------------------------------------------------------------------------------------------------------

async def discover_groups(session: AsyncSession) -> int:
    """Register every ledger group that holds in-scope debtor ledgers. New ones start UNMAPPED with a suggestion;
    UNMAPPED ones get their suggestion refreshed. A decided group (MAPPED / NOT_FOS) is never altered here."""
    names = (await session.execute(
        select(func.coalesce(func.nullif(func.trim(TallyDebtorLedger.parent_group), ""), NO_GROUP)).where(
            TallyDebtorLedger.is_debtor.is_not(False),
            or_(TallyDebtorLedger.business_scope.is_(None), TallyDebtorLedger.business_scope == SCOPE_DISTRIBUTION),
        ).distinct()
    )).scalars().all()
    existing = {g.group_key: g for g in (await session.execute(select(TallyFosGroup))).scalars().all()}
    cands = assignable_employees(await _employees(session))
    created = 0
    for name in sorted(set(names)):
        key = L.normalize_group_key(name)
        if not key:
            continue
        sugg_id, basis = L.suggest_employee(name, cands)
        g = existing.get(key)
        if g is None:
            # ON CONFLICT DO NOTHING: two ledger batches discovering the same new group at once must not fail.
            res = await session.execute(pg_insert(TallyFosGroup).values(
                id=uuid.uuid4(), group_key=key, group_name=name[:150], status=GROUP_UNMAPPED,
                suggested_employee_id=sugg_id, suggestion_basis=basis).on_conflict_do_nothing(index_elements=["group_key"]))
            created += res.rowcount or 0
        elif g.status == GROUP_UNMAPPED and (g.suggested_employee_id != sugg_id or g.suggestion_basis != basis):
            g.suggested_employee_id, g.suggestion_basis = sugg_id, basis
    await session.flush()
    return created


class MappingError(ValueError):
    pass


async def set_group_mapping(
    session: AsyncSession, group_id: uuid.UUID, user: User, *, employee_id: Optional[uuid.UUID] = None,
    not_fos: bool = False, note: Optional[str] = None,
) -> TallyFosGroup:
    """Admin decision for one group: an employee, NOT_FOS, or (both empty) back to UNMAPPED. Audited."""
    g = await session.get(TallyFosGroup, group_id)
    if g is None:
        raise MappingError("Tally group not found")
    if employee_id is not None and not_fos:
        raise MappingError("Choose an employee or 'not a FOS group', not both")
    emps = await _employees(session)
    if employee_id is not None:
        e = emps.get(employee_id)
        if e is None:
            raise MappingError("Employee not found")
        if employee_id not in {i for i, _ in assignable_employees(emps)}:
            raise MappingError("This employee is inactive or cannot be assigned outlets")
    before = {"status": g.status, "employee_id": g.employee_id}
    if employee_id is not None:
        g.status, g.employee_id = GROUP_MAPPED, employee_id
    elif not_fos:
        g.status, g.employee_id = GROUP_NOT_FOS, None
    else:
        g.status, g.employee_id = GROUP_UNMAPPED, None
    g.decided_by, g.decided_at, g.note = user.id, _now(), (note or None)
    def label(status, eid):
        return (f"mapped to {emps.get(eid, {}).get('name', eid)}" if status == GROUP_MAPPED else
                "not a FOS group" if status == GROUP_NOT_FOS else "unmapped")
    session.add(FosAssignmentAudit(
        customer_id=None, action="GROUP_MAPPING", source="ADMIN", tally_group=g.group_name, result="APPLIED",
        previous_employee_id=before["employee_id"], previous_fos=label(before["status"], before["employee_id"]),
        new_employee_id=g.employee_id, new_fos=label(g.status, g.employee_id),
        detail=f"by {user.email}" + (f": {note}" if note else "")))
    await session.flush()
    return g


# ---------------------------------------------------------------------------------------------------------------
# Synchronisation
# ---------------------------------------------------------------------------------------------------------------

def _names(ids: Iterable[uuid.UUID], emps: dict) -> str:
    return ", ".join(sorted(emps.get(i, {}).get("name", str(i)) for i in ids))


async def run_sync(
    session: AsyncSession, *, trigger: str, dry_run: bool, customer_ids: Optional[Iterable[uuid.UUID]] = None,
    user_id: Optional[uuid.UUID] = None, policy: Optional[str] = None, collect_report: bool = False,
) -> tuple[FosSyncRun, dict[str, Any]]:
    """
    Evaluate (customer_ids=None: every visible outlet) and, unless dry_run, apply. The caller commits.
    Idempotent: when nothing differs from Tally nothing is written except customers.fos_synced_at.
    """
    policy = policy or legacy_policy()
    run = FosSyncRun(trigger=trigger, dry_run=dry_run, legacy_policy=policy, status="RUNNING", triggered_by=user_id)
    session.add(run)
    await session.flush()

    await discover_groups(session)
    emps = await _employees(session)
    rules, group_rows = await _rules(session)

    if customer_ids is None:
        cust_stmt = select(Customer).where(_outlet_visible())
    else:
        ids = list(customer_ids)
        cust_stmt = select(Customer).where(Customer.id.in_(ids)) if ids else select(Customer).where(sa_false())
    customers = (await session.execute(cust_stmt)).scalars().all()
    cids = [c.id for c in customers]
    ledgers = await _ledgers_by_customer(session, cids)
    rows_by_cust: dict[uuid.UUID, list[EmployeeCustomerAssignment]] = defaultdict(list)
    if cids:
        for r in (await session.execute(select(EmployeeCustomerAssignment).where(EmployeeCustomerAssignment.customer_id.in_(cids)))).scalars().all():
            rows_by_cust[r.customer_id].append(r)
    system_uid = None

    counts: Counter = Counter()
    status_counts: Counter = Counter()
    report: dict[str, list] = defaultdict(list)
    now = _now()
    touched: list[uuid.UUID] = []

    def add_report(kind: str, c: Customer, current_rows, plan: L.OutletPlan, extra: Optional[dict] = None):
        if not collect_report or len(report[kind]) >= REPORT_ROW_CAP:
            return
        item = {
            "customer_id": str(c.id), "outlet": c.name, "outlet_code": c.outlet_code,
            "tally_group": ", ".join(sorted({l.group_name for l in ledgers.get(c.id, [])})),
            "existing_fos": _names([r.employee_id for r in current_rows], emps) or None,
            "tally_fos": _names(plan.wanted.keys(), emps) or None,
        }
        if extra:
            item.update(extra)
        report[kind].append(item)

    for c in customers:
        cur_rows = rows_by_cust.get(c.id, [])
        current = [L.CurrentRow(r.id, r.employee_id, r.source or "LEGACY") for r in cur_rows]
        plan = L.plan_outlet(ledgers.get(c.id, []), rules, current, policy)
        counts["evaluated"] += 1
        status_counts[plan.status] += 1

        # ---- report categories (always computed from the plan, applied or not)
        kinds = {ch.kind for ch in plan.changes}
        if plan.status == ST_CONFLICT:
            add_report("conflicting" if plan.wanted else "assigned_here_blank_in_tally", c, cur_rows, plan)
        elif plan.status == ST_UNMAPPED_GROUP:
            add_report("missing_employee_mapping", c, cur_rows, plan, {"unmapped_groups": plan.unmapped_groups})
        elif plan.status in (ST_ASSIGNED, ST_MULTIPLE):
            if "ADOPTED" in kinds and "ASSIGNED" not in kinds and "REMOVED" not in kinds and "REPLACED_LEGACY" not in kinds:
                add_report("matching", c, cur_rows, plan)
            elif "ASSIGNED" in kinds and not cur_rows:
                add_report("new_from_tally", c, cur_rows, plan)
            elif plan.changes:
                add_report("changed", c, cur_rows, plan)
            else:
                add_report("matching", c, cur_rows, plan, {"already_synced": True})
        elif plan.status == ST_UNASSIGNED and cur_rows:
            add_report("assigned_here_blank_in_tally", c, cur_rows, plan)

        if dry_run:
            for ch in plan.changes:
                counts[f"would_{ch.kind.lower()}"] += 1
            continue

        # ---- apply
        before_ids = {r.employee_id for r in cur_rows}
        if plan.changes:
            if system_uid is None:
                from app.services.tally_sync_service import _get_system_user_id
                system_uid = await _get_system_user_id(session)
            by_id = {r.id: r for r in cur_rows}
            for ch in plan.changes:
                if ch.kind in ("REMOVED", "REPLACED_LEGACY"):
                    row = by_id.get(ch.row_id)
                    if row is not None:
                        await session.delete(row)
                elif ch.kind == "ADOPTED":
                    row = by_id.get(ch.row_id)
                    if row is not None:
                        row.source, row.tally_group, row.tally_ledger_guid, row.synced_at = SRC_TALLY, ch.group_name, ch.ledger_guid, now
                elif ch.kind == "ASSIGNED":
                    session.add(EmployeeCustomerAssignment(
                        employee_id=ch.employee_id, customer_id=c.id, created_by=system_uid, source=SRC_TALLY,
                        tally_group=ch.group_name, tally_ledger_guid=ch.ledger_guid, synced_at=now))
                counts[ch.kind.lower()] += 1
            # keep the stamp fresh on rows that did not change but are still confirmed by Tally
            for r in cur_rows:
                if r.source == SRC_TALLY and r.employee_id in plan.wanted:
                    r.synced_at = now
            after_ids = set(plan.wanted.keys()) if plan.status in (ST_ASSIGNED, ST_MULTIPLE, ST_UNASSIGNED) else before_ids
            only_adopt = kinds == {"ADOPTED"}
            action = ("ADOPTED" if only_adopt else "ASSIGNED" if not before_ids else "REMOVED" if not after_ids else "CHANGED")
            led0 = ledgers.get(c.id, [None])[0]
            wanted_g = next(iter(plan.wanted.values()), (None, None))
            session.add(FosAssignmentAudit(
                run_id=run.id, customer_id=c.id, customer_name=c.name[:150],
                previous_employee_id=next(iter(before_ids), None) if len(before_ids) == 1 else None,
                previous_fos=_names(before_ids, emps) or None,
                new_employee_id=next(iter(after_ids), None) if len(after_ids) == 1 else None,
                new_fos=_names(after_ids, emps) or None,
                action=action, source="TALLY", tally_group=wanted_g[0] or (led0.group_name if led0 else None),
                tally_ledger_guid=wanted_g[1] or (led0.guid if led0 else None), result="APPLIED",
                detail="; ".join(f"{ch.kind.lower()}: {emps.get(ch.employee_id, {}).get('name', ch.employee_id)}"
                                 + (f" ({ch.detail})" if ch.detail else "") for ch in plan.changes)[:900]))
        else:
            for r in cur_rows:
                if r.source == SRC_TALLY and r.employee_id in plan.wanted:
                    r.synced_at = now
            counts["unchanged"] += 1
        # A conflict / unmapped group is recorded once, when the outlet enters that state.
        if plan.status in (ST_CONFLICT, ST_UNMAPPED_GROUP) and c.fos_status != plan.status:
            led0 = ledgers.get(c.id, [None])[0]
            session.add(FosAssignmentAudit(
                run_id=run.id, customer_id=c.id, customer_name=c.name[:150],
                previous_fos=_names(before_ids, emps) or None,
                new_fos=_names(plan.wanted.keys(), emps) or None,
                action=plan.status, source="TALLY", tally_group=(", ".join(plan.unmapped_groups) if plan.unmapped_groups
                                                                  else (led0.group_name if led0 else None)),
                tally_ledger_guid=led0.guid if led0 else None, result="FLAGGED",
                detail=("existing assignment kept: it differs from Tally" if plan.status == ST_CONFLICT
                        else "Tally group is not mapped to an employee yet: existing assignment kept")))
            counts["flagged"] += 1
        if c.fos_status != plan.status:
            c.fos_status = plan.status
        touched.append(c.id)

    if not dry_run and touched:
        await session.execute(update(Customer).where(Customer.id.in_(touched)).values(fos_synced_at=now))
    await session.flush()

    group_stats = Counter(g.status for g in group_rows.values())
    run.summary = {"counts": dict(counts), "outlet_status": dict(status_counts), "groups": dict(group_stats),
                   "scope": "all outlets" if customer_ids is None else f"{len(cids)} outlets"}
    run.status, run.finished_at = "COMPLETE", _now()
    await session.flush()
    return run, dict(report)


async def sync_after_ledger_batch(session: AsyncSession, guids: list[str], full: bool) -> None:
    """Hook for the Tally ledger sync. Never raises: the ledger sync must not fail because of the FOS sync.
    Always keeps the group list current; writes assignments only when settings.tally_fos_sync_enabled."""
    try:
        async with session.begin_nested():
            await discover_groups(session)
            if not apply_enabled():
                return
            if full:
                await run_sync(session, trigger="LEDGER_SYNC", dry_run=False)
            elif guids:
                ids = (await session.execute(
                    select(TallyDebtorLedger.customer_id).where(TallyDebtorLedger.tally_guid.in_(guids)).distinct()
                )).scalars().all()
                if ids:
                    await run_sync(session, trigger="LEDGER_SYNC", dry_run=False, customer_ids=ids)
    except Exception:  # noqa: BLE001
        log.exception("FOS synchronisation after a ledger batch failed; the ledger sync itself is unaffected")


# ---------------------------------------------------------------------------------------------------------------
# Reconciliation report (read-only)
# ---------------------------------------------------------------------------------------------------------------

async def proposed_mappings_from_assignments(session: AsyncSession) -> list[dict]:
    """For every group, the employee the EXISTING (pre-sync) assignments of its outlets point to, when they all agree.
    A proposal for the admin only - these assignments were made by hand and may not match Tally's intent."""
    rows = (await session.execute(
        select(Customer.tally_parent_group, EmployeeCustomerAssignment.employee_id, func.count())
        .join(EmployeeCustomerAssignment, EmployeeCustomerAssignment.customer_id == Customer.id)
        .where(Customer.tally_parent_group.is_not(None), EmployeeCustomerAssignment.source != SRC_TALLY)
        .group_by(Customer.tally_parent_group, EmployeeCustomerAssignment.employee_id)
    )).all()
    emps = await _employees(session)
    per_group: dict[str, dict[uuid.UUID, int]] = defaultdict(dict)
    names: dict[str, str] = {}
    for grp, eid, n in rows:
        key = L.normalize_group_key(grp)
        per_group[key][eid] = per_group[key].get(eid, 0) + n
        names.setdefault(key, grp)
    out = []
    for key, by_emp in sorted(per_group.items()):
        if len(by_emp) == 1:
            eid, n = next(iter(by_emp.items()))
            out.append({"group": names[key], "employee_id": str(eid), "employee": emps.get(eid, {}).get("name"),
                        "existing_assignments": n})
        else:
            out.append({"group": names[key], "employee_id": None, "employee": None,
                        "existing_assignments": sum(by_emp.values()),
                        "note": "existing assignments disagree: " + _names(by_emp.keys(), emps)})
    return out


async def reconciliation_report(session: AsyncSession) -> dict[str, Any]:
    """What a sync would do right now, with the current group mappings, without writing anything.
    (discover_groups is NOT called: this is a pure read.)"""
    emps = await _employees(session)
    rules, group_rows = await _rules(session)
    ledgers = await _ledgers_by_customer(session)
    customers = (await session.execute(select(Customer).where(_outlet_visible()))).scalars().all()
    rows_by_cust: dict[uuid.UUID, list[EmployeeCustomerAssignment]] = defaultdict(list)
    for r in (await session.execute(select(EmployeeCustomerAssignment))).scalars().all():
        rows_by_cust[r.customer_id].append(r)

    buckets: dict[str, list] = defaultdict(list)
    status_counts: Counter = Counter()
    group_counts: Counter = Counter()
    for c in customers:
        cur_rows = rows_by_cust.get(c.id, [])
        plan = L.plan_outlet(ledgers.get(c.id, []), rules,
                             [L.CurrentRow(r.id, r.employee_id, r.source or "LEGACY") for r in cur_rows], L.POLICY_REPORT_ONLY)
        status_counts[plan.status] += 1
        for led in ledgers.get(c.id, []):
            group_counts[led.group_name] += 1
        kinds = {ch.kind for ch in plan.changes}
        item = {"customer_id": str(c.id), "outlet": c.name, "outlet_code": c.outlet_code,
                "tally_group": ", ".join(sorted({l.group_name for l in ledgers.get(c.id, [])})) or None,
                "existing_fos": _names([r.employee_id for r in cur_rows], emps) or None,
                "tally_fos": _names(plan.wanted.keys(), emps) or None}
        if plan.status == ST_CONFLICT:
            buckets["conflicting" if plan.wanted else "assigned_here_blank_in_tally"].append(item)
        elif plan.status == ST_UNMAPPED_GROUP:
            buckets["missing_employee_mapping"].append({**item, "unmapped_groups": plan.unmapped_groups})
        elif plan.status in (ST_ASSIGNED, ST_MULTIPLE):
            if "ASSIGNED" in kinds and not cur_rows:
                buckets["new_from_tally"].append(item)
            elif kinds - {"ADOPTED"}:
                buckets["changed"].append(item)
            else:
                buckets["matching"].append(item)
        elif plan.status == ST_UNASSIGNED:
            buckets["assigned_here_blank_in_tally" if cur_rows else "unassigned_in_both"].append(item)
        elif plan.status == ST_NO_TALLY and cur_rows:
            buckets["no_tally_ledger_with_assignment"].append(item)

    groups = []
    for g in sorted(group_rows.values(), key=lambda x: x.group_name.lower()):
        groups.append({"group": g.group_name, "status": g.status,
                       "employee": emps.get(g.employee_id, {}).get("name") if g.employee_id else None,
                       "suggestion": emps.get(g.suggested_employee_id, {}).get("name") if g.suggested_employee_id else None,
                       "outlets": group_counts.get(g.group_name, 0)})
    unmapped_names = [g["group"] for g in groups if g["status"] == GROUP_UNMAPPED]
    return {
        "generated_at": _now().isoformat(),
        "sync_enabled": apply_enabled(), "legacy_policy": legacy_policy(),
        "outlets_evaluated": len(customers),
        "outlet_status": dict(status_counts),
        "counts": {k: len(v) for k, v in buckets.items()},
        "unmatched_salesperson_groups": unmapped_names,
        "groups": groups,
        "proposed_mappings": await proposed_mappings_from_assignments(session),
        "rows": {k: v[:REPORT_ROW_CAP] for k, v in buckets.items()},
    }
