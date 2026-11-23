"""
Admin view of the Tally-synchronised FOS assignments.

Tally is the source of truth: the accountant moves a customer ledger into a FOS's group in Tally and the next
ledger sync updates FieldTrack. There is deliberately NO endpoint that sets or changes the FOS of an outlet here.
Admins only maintain the MAPPING of Tally groups to employees (a group is a Tally concept, an employee a
FieldTrack one) and can review / trigger the synchronisation.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import and_, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps.auth import CurrentUser, require_role
from app.database import get_async_session
from app.models.customer import Customer
from app.models.employee import Employee
from app.models.employee_customer_assignment import EmployeeCustomerAssignment
from app.models.tally_fos import (
    ALL_STATUSES, FosAssignmentAudit, FosSyncRun, TallyFosGroup,
)
from app.models.user import Role
from app.services import fos_sync_service as svc

DbSession = Annotated[AsyncSession, Depends(get_async_session)]
router = APIRouter(prefix="/fos-assignments", tags=["fos-assignments"])
AdminOnly = Depends(require_role(Role.ADMIN))


class FosRef(BaseModel):
    employee_id: uuid.UUID
    name: str
    source: str


class OutletFosRead(BaseModel):
    id: uuid.UUID
    name: str
    outlet_code: Optional[str] = None
    tally_group: Optional[str] = None
    fos: list[FosRef] = []
    fos_status: Optional[str] = None
    fos_synced_at: Optional[datetime] = None


class OutletFosPage(BaseModel):
    items: list[OutletFosRead]
    total: int


class GroupRead(BaseModel):
    id: uuid.UUID
    group_name: str
    status: str
    employee_id: Optional[uuid.UUID] = None
    employee_name: Optional[str] = None
    suggested_employee_id: Optional[uuid.UUID] = None
    suggested_employee_name: Optional[str] = None
    suggestion_basis: Optional[str] = None
    outlets: int = 0
    assigned_outlets: int = 0
    decided_at: Optional[datetime] = None
    note: Optional[str] = None


class GroupMappingBody(BaseModel):
    employee_id: Optional[uuid.UUID] = None
    not_fos: bool = False
    note: Optional[str] = Field(default=None, max_length=300)


class BulkMappingItem(GroupMappingBody):
    group_id: uuid.UUID


class SyncBody(BaseModel):
    dry_run: bool = True


class AuditRead(BaseModel):
    id: uuid.UUID
    run_id: Optional[uuid.UUID] = None
    customer_id: Optional[uuid.UUID] = None
    customer_name: Optional[str] = None
    previous_fos: Optional[str] = None
    new_fos: Optional[str] = None
    action: str
    source: str
    tally_group: Optional[str] = None
    tally_ledger_guid: Optional[str] = None
    result: str
    detail: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


def _gkey(col=None):
    """SQL twin of fos_logic.normalize_group_key (lower-case, whitespace collapsed)."""
    col = Customer.tally_parent_group if col is None else col
    return func.regexp_replace(func.lower(func.trim(col)), r"\s+", " ", "g")


def _visible():
    return and_(Customer.tally_is_debtor.is_not(False), Customer.merged_into_customer_id.is_(None))


def _filters(assignment: str, status: Optional[str], employee_id: Optional[uuid.UUID], group: Optional[str], search: Optional[str]):
    f = [_visible()]
    has_row = exists().where(EmployeeCustomerAssignment.customer_id == Customer.id)
    if assignment == "assigned":
        f.append(has_row)
    elif assignment == "unassigned":
        f.append(~has_row)
    if status:
        if status == "NOT_SYNCED":
            f.append(Customer.fos_status.is_(None))
        else:
            f.append(Customer.fos_status == status)
    if employee_id:
        f.append(exists().where(EmployeeCustomerAssignment.customer_id == Customer.id,
                                EmployeeCustomerAssignment.employee_id == employee_id))
    if group:
        f.append(_gkey() == " ".join(group.lower().split()))
    if search and search.strip():
        like = f"%{search.strip()}%"
        f.append(or_(Customer.name.ilike(like), Customer.outlet_code.ilike(like)))
    return f


@router.get("/summary", dependencies=[AdminOnly])
async def summary(session: DbSession):
    vis = _visible()
    total = (await session.execute(select(func.count(Customer.id)).where(vis))).scalar_one()
    with_fos = (await session.execute(select(func.count(Customer.id)).where(
        vis, exists().where(EmployeeCustomerAssignment.customer_id == Customer.id)))).scalar_one()
    status_expr = func.coalesce(Customer.fos_status, "NOT_SYNCED")
    by_status = dict((await session.execute(select(status_expr, func.count()).where(vis).group_by(status_expr))).all())
    groups = dict((await session.execute(select(TallyFosGroup.status, func.count()).group_by(TallyFosGroup.status))).all())
    last = (await session.execute(select(FosSyncRun).where(FosSyncRun.dry_run.is_(False), FosSyncRun.status == "COMPLETE")
                                  .order_by(FosSyncRun.started_at.desc()).limit(1))).scalar_one_or_none()
    last_synced = (await session.execute(select(func.max(Customer.fos_synced_at)))).scalar_one()
    return {
        "total_outlets": total, "outlets_with_fos": with_fos, "outlets_without_fos": total - with_fos,
        "by_status": by_status, "groups": groups,
        "sync_enabled": svc.apply_enabled(), "legacy_policy": svc.legacy_policy(),
        "last_run_at": last.finished_at if last else None, "last_run_trigger": last.trigger if last else None,
        "last_run_summary": last.summary if last else None, "last_synced_at": last_synced,
        "statuses": list(ALL_STATUSES),
    }


@router.get("/outlets", response_model=OutletFosPage, dependencies=[AdminOnly])
async def list_outlets(
    session: DbSession,
    assignment: str = Query(default="all", pattern="^(all|assigned|unassigned)$"),
    status: Optional[str] = Query(default=None, pattern="^(" + "|".join(ALL_STATUSES) + "|NOT_SYNCED)$"),
    employee_id: Optional[uuid.UUID] = None,
    group: Optional[str] = Query(default=None, max_length=150),
    search: Optional[str] = Query(default=None, max_length=100),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    f = _filters(assignment, status, employee_id, group, search)
    total = (await session.execute(select(func.count(Customer.id)).where(*f))).scalar_one()
    custs = (await session.execute(select(Customer).where(*f).order_by(Customer.name.asc()).offset(offset).limit(limit))).scalars().all()
    ids = [c.id for c in custs]
    fos: dict[uuid.UUID, list[FosRef]] = {}
    if ids:
        rows = (await session.execute(
            select(EmployeeCustomerAssignment.customer_id, Employee.id, Employee.full_name, EmployeeCustomerAssignment.source)
            .join(Employee, Employee.id == EmployeeCustomerAssignment.employee_id)
            .where(EmployeeCustomerAssignment.customer_id.in_(ids)).order_by(Employee.full_name))).all()
        for cid, eid, name, src in rows:
            fos.setdefault(cid, []).append(FosRef(employee_id=eid, name=name, source=src))
    return OutletFosPage(total=total, items=[
        OutletFosRead(id=c.id, name=c.name, outlet_code=c.outlet_code, tally_group=c.tally_parent_group,
                      fos=fos.get(c.id, []), fos_status=c.fos_status, fos_synced_at=c.fos_synced_at) for c in custs])


@router.get("/groups", response_model=list[GroupRead], dependencies=[AdminOnly])
async def list_groups(session: DbSession, status: Optional[str] = Query(default=None, pattern="^(UNMAPPED|MAPPED|NOT_FOS)$")):
    """Every Tally ledger group that holds outlets, with its mapping (the admin's decision) and a suggestion."""
    return await _groups_read(session, status)


async def _groups_read(session: AsyncSession, status: Optional[str] = None) -> list[GroupRead]:
    await svc.discover_groups(session)
    await session.commit()
    stmt = select(TallyFosGroup)
    if status:
        stmt = stmt.where(TallyFosGroup.status == status)
    groups = (await session.execute(stmt.order_by(TallyFosGroup.group_name))).scalars().all()
    names = dict((await session.execute(select(Employee.id, Employee.full_name))).all())
    gk = _gkey()
    counts = dict((await session.execute(select(gk, func.count()).where(_visible()).group_by(gk))).all())
    assigned = dict((await session.execute(
        select(gk, func.count(func.distinct(Customer.id)))
        .join(EmployeeCustomerAssignment, EmployeeCustomerAssignment.customer_id == Customer.id)
        .where(_visible()).group_by(gk))).all())
    out = []
    for g in groups:
        out.append(GroupRead(
            id=g.id, group_name=g.group_name, status=g.status, employee_id=g.employee_id,
            employee_name=names.get(g.employee_id) if g.employee_id else None,
            suggested_employee_id=g.suggested_employee_id,
            suggested_employee_name=names.get(g.suggested_employee_id) if g.suggested_employee_id else None,
            suggestion_basis=g.suggestion_basis, outlets=counts.get(g.group_key, 0),
            assigned_outlets=assigned.get(g.group_key, 0), decided_at=g.decided_at, note=g.note))
    return sorted(out, key=lambda x: (-x.outlets, x.group_name.lower()))


async def _apply_mapping(session, group_id, body: GroupMappingBody, user):
    try:
        return await svc.set_group_mapping(session, group_id, user, employee_id=body.employee_id,
                                           not_fos=body.not_fos, note=body.note)
    except svc.MappingError as ex:
        raise HTTPException(status_code=422, detail=str(ex))


async def _resync_group(session, group_name_key: str, user_id):
    """After a mapping decision, bring that group's outlets up to date (only when the sync is enabled)."""
    if not svc.apply_enabled():
        return None
    ids = (await session.execute(select(Customer.id).where(_gkey() == group_name_key))).scalars().all()
    if not ids:
        return None
    run, _ = await svc.run_sync(session, trigger="GROUP_MAPPING", dry_run=False, customer_ids=ids, user_id=user_id)
    return run.summary


@router.put("/groups/{group_id}", response_model=GroupRead, dependencies=[AdminOnly])
async def map_group(group_id: uuid.UUID, body: GroupMappingBody, current_user: CurrentUser, session: DbSession):
    g = await _apply_mapping(session, group_id, body, current_user)
    await _resync_group(session, g.group_key, current_user.id)
    await session.commit()
    return next(x for x in await _groups_read(session) if x.id == group_id)


@router.post("/groups/bulk", dependencies=[AdminOnly])
async def map_groups_bulk(items: list[BulkMappingItem], current_user: CurrentUser, session: DbSession):
    """Apply several mapping decisions at once (e.g. the proposals of the reconciliation report)."""
    if not items or len(items) > 200:
        raise HTTPException(status_code=422, detail="Send between 1 and 200 mapping decisions")
    done = 0
    keys = []
    for it in items:
        g = await _apply_mapping(session, it.group_id, it, current_user)
        keys.append(g.group_key)
        done += 1
    for key in sorted(set(keys)):
        await _resync_group(session, key, current_user.id)
    await session.commit()
    return {"mapped": done, "sync_enabled": svc.apply_enabled()}


@router.get("/reconciliation", dependencies=[AdminOnly])
async def reconciliation(session: DbSession):
    """Read-only: what the synchronisation would do now (matching / conflicting / unassigned in Tally / unmapped)."""
    return await svc.reconciliation_report(session)


@router.post("/sync", dependencies=[AdminOnly])
async def run_now(body: SyncBody, current_user: CurrentUser, session: DbSession):
    """Dry run (default) reports without writing; an applying run needs TALLY_FOS_SYNC_ENABLED=true."""
    if not body.dry_run and not svc.apply_enabled():
        raise HTTPException(status_code=409, detail="FOS synchronisation is not enabled on this server (TALLY_FOS_SYNC_ENABLED)")
    run, report = await svc.run_sync(session, trigger="ADMIN", dry_run=body.dry_run, user_id=current_user.id, collect_report=body.dry_run)
    await session.commit()
    return {"run_id": run.id, "dry_run": run.dry_run, "legacy_policy": run.legacy_policy, "summary": run.summary,
            "report": {k: v[:200] for k, v in report.items()} if body.dry_run else None}


@router.get("/audit", response_model=list[AuditRead], dependencies=[AdminOnly])
async def audit_log(
    session: DbSession, customer_id: Optional[uuid.UUID] = None, action: Optional[str] = Query(default=None, max_length=24),
    limit: int = Query(default=100, ge=1, le=500), offset: int = Query(default=0, ge=0),
):
    stmt = select(FosAssignmentAudit).order_by(FosAssignmentAudit.created_at.desc())
    if customer_id:
        stmt = stmt.where(FosAssignmentAudit.customer_id == customer_id)
    if action:
        stmt = stmt.where(FosAssignmentAudit.action == action)
    return (await session.execute(stmt.offset(offset).limit(limit))).scalars().all()
