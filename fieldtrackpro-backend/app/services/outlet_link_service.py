"""
Physical outlet <-> Tally ledger mapping (release 2.1.0, CONTRACTS_2.1.0 C4/C5).

`customers` is the physical outlet. A Tally debtor ledger is linked to another outlet only by
an explicit, audited action here - never by name similarity, never automatically:

  LINK      ledger L -> outlet T. L's own financial rows (by tally_debtor_ledger_id) move to T.
            When L's former customer S has no ledger left it is MERGED into T: kept, hidden,
            pointing to T; its operational rows move to T (ids recorded); unique clashes
            (an assignment / brand T already has) are recorded as superseded and left on S;
            outlet code, location, area and territory are copied to T only where T has none.
  UNLINK    exact reverse of the ledger's last LINK (or, without one, a new outlet from the ledger).
  SET_PRIMARY / BRAND_OVERRIDE / OUTLET_CODE / RENAME - audited single changes.
  BULK_APPLY / BULK_REVERT - a client-confirmed workbook (only rows answered Y), one transaction,
            one batch_id; reverted by batch.

Linking never changes a Tally fact (GUID, balances, bills, vouchers) of any ledger.
"""
from __future__ import annotations

import io
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions.custom import BaseAPIException
from app.models.customer import Customer
from app.models.outlet_link_event import OutletLinkEvent
from app.models.tally_debtor_ledger import MAPPING_CONFIRMED, MAPPING_NEW, MAPPING_REVIEW, TallyDebtorLedger
from app.models.user import User

ZERO = Decimal("0.00")

# Rows that belong to a LEDGER (moved with it on LINK / UNLINK).
FINANCIAL_TABLES = ("invoices", "payments", "tally_ledger_adjustments", "tally_open_bills")
# Rows that belong to the OUTLET (moved only when a customer is merged): (table, column).
OPERATIONAL = (
    ("visits", "customer_id"), ("planned_visits", "customer_id"), ("orders", "customer_id"),
    ("customer_requirements", "customer_id"), ("outlet_proofs", "customer_id"),
    ("customer_location_proposals", "customer_id"), ("customer_prospects", "resulting_customer_id"),
    ("field_exceptions", "customer_id"), ("outlet_financial_snapshots", "customer_id"),
    ("invoices", "customer_id"), ("payments", "customer_id"),
    ("tally_ledger_adjustments", "customer_id"), ("tally_open_bills", "customer_id"),
)
# Outlet rows with a uniqueness rule per outlet: (table, column, the other unique column).
UNIQUE_PER_OUTLET = (
    ("employee_customer_assignments", "customer_id", "employee_id"),
    ("customer_brands", "customer_id", "brand"),
)
COPY_IF_EMPTY = ("outlet_code", "location", "area_id", "territory_id")


def _conflict(detail: str, code: str = "OUTLET_MAPPING_CONFLICT") -> BaseAPIException:
    return BaseAPIException(status_code=409, detail=detail, error_code=code)


def _not_found(detail: str) -> BaseAPIException:
    return BaseAPIException(status_code=404, detail=detail, error_code="NOT_FOUND")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _ids(rows) -> list[str]:
    return [str(r) for r in rows]


# ---------------------------------------------------------------------------
# Read helpers (customers API)
# ---------------------------------------------------------------------------

async def enrich_ledger_summary(session: AsyncSession, reads: list, with_ledgers: bool = False) -> None:
    """Fill CustomerRead.ledger_count / tally_codes / brands (+ ledgers) in one query. Mutates in place."""
    from app.schemas.customer import LedgerRead

    ids = [r.id for r in reads]
    if not ids:
        return
    rows = (await session.execute(
        select(TallyDebtorLedger).where(TallyDebtorLedger.customer_id.in_(ids))
        .order_by(TallyDebtorLedger.is_primary.desc(), TallyDebtorLedger.name)
    )).scalars().all()
    by: dict[uuid.UUID, list[TallyDebtorLedger]] = {}
    for l in rows:
        by.setdefault(l.customer_id, []).append(l)
    for r in reads:
        ls = by.get(r.id, [])
        debtors = [l for l in ls if l.is_debtor is not False]
        r.ledger_count = len(ls)
        r.tally_codes = sorted({l.tally_outlet_code for l in ls if l.tally_outlet_code})
        r.brands = sorted(set(r.brands or []) | {l.effective_brand for l in debtors if l.effective_brand})
        if with_ledgers:
            r.ledgers = [LedgerRead.from_model(l) for l in ls]


async def _ledger(session: AsyncSession, ledger_id: uuid.UUID) -> TallyDebtorLedger:
    led = await session.get(TallyDebtorLedger, ledger_id)
    if led is None:
        raise _not_found("Tally ledger not found")
    return led


async def _customer(session: AsyncSession, customer_id: uuid.UUID) -> Customer:
    c = await session.get(Customer, customer_id)
    if c is None:
        raise _not_found("Outlet not found")
    return c


def _event(session, action, actor: Optional[User], ledger_id=None, from_c=None, to_c=None, moved=None,
           before=None, batch_id=None, note=None) -> OutletLinkEvent:
    ev = OutletLinkEvent(id=uuid.uuid4(), action=action, ledger_id=ledger_id, from_customer_id=from_c, to_customer_id=to_c,
                         moved=moved or {}, before=before, batch_id=batch_id,
                         actor_id=actor.id if actor else None, note=note, created_at=_now())
    session.add(ev)
    return ev


async def _move(session, table: str, column: str, where_sql: str, params: dict, to_id) -> list[str]:
    rows = (await session.execute(text(f"SELECT id FROM {table} WHERE {where_sql}"), params)).scalars().all()
    if rows:
        await session.execute(text(f"UPDATE {table} SET {column} = :to WHERE id = ANY(:ids)"),
                              {"to": to_id, "ids": list(rows)})
    return _ids(rows)


# ---------------------------------------------------------------------------
# LINK / UNLINK
# ---------------------------------------------------------------------------

async def link(session: AsyncSession, ledger_id: uuid.UUID, target_customer_id: uuid.UUID, actor: Optional[User],
               note: Optional[str] = None, batch_id: Optional[uuid.UUID] = None) -> OutletLinkEvent:
    led = await _ledger(session, ledger_id)
    target = await _customer(session, target_customer_id)
    if target.merged_into_customer_id:
        raise _conflict("The target outlet is merged into another outlet; link to that outlet instead")
    if led.customer_id == target.id:
        raise _conflict("The ledger already belongs to this outlet")
    if led.is_debtor is False:
        raise _conflict("Only a debtor ledger can be linked to an outlet")
    src_id = led.customer_id
    src = await _customer(session, src_id)
    await session.flush()
    moved: dict[str, Any] = {}
    before: dict[str, Any] = {"ledger": {"is_primary": led.is_primary, "mapping_status": led.mapping_status,
                                         "linked_by": str(led.linked_by) if led.linked_by else None,
                                         "linked_at": led.linked_at.isoformat() if led.linked_at else None}}

    for table in FINANCIAL_TABLES:
        ids = await _move(session, table, "customer_id", "tally_debtor_ledger_id = :l AND customer_id = :s",
                          {"l": led.id, "s": src_id}, target.id)
        if ids:
            moved[table] = ids

    target_has_primary = (await session.execute(select(TallyDebtorLedger.id).where(
        TallyDebtorLedger.customer_id == target.id, TallyDebtorLedger.is_primary))).first() is not None
    was_primary = led.is_primary
    led.is_primary = False
    await session.flush()
    led.customer_id = target.id
    led.is_primary = not target_has_primary
    led.mapping_status = MAPPING_CONFIRMED
    led.linked_by = actor.id if actor else None
    led.linked_at = _now()
    await session.flush()

    remaining = (await session.execute(select(TallyDebtorLedger).where(
        TallyDebtorLedger.customer_id == src_id).order_by(TallyDebtorLedger.name))).scalars().all()
    if remaining and was_primary:
        remaining[0].is_primary = True
        before["promoted_primary_ledger_id"] = str(remaining[0].id)
    if not remaining:
        await _merge(session, src, target, actor, moved, before)
    await session.flush()
    return _event(session, "LINK", actor, led.id, src_id, target.id, moved, before, batch_id, note)


async def _merge(session, src: Customer, target: Customer, actor, moved: dict, before: dict) -> None:
    """Move an emptied customer's outlet data to the physical outlet and hide it (never delete)."""
    for table, col in OPERATIONAL:
        ids = await _move(session, table, col, f"{col} = :s", {"s": src.id}, target.id)
        if ids:
            moved[table] = moved.get(table, []) + ids
    superseded: dict[str, list[str]] = {}
    for table, col, other in UNIQUE_PER_OUTLET:
        clash = (await session.execute(text(
            f"SELECT a.id FROM {table} a WHERE a.{col} = :s AND EXISTS "
            f"(SELECT 1 FROM {table} b WHERE b.{col} = :t AND b.{other} = a.{other})"),
            {"s": src.id, "t": target.id})).scalars().all()
        if clash:
            superseded[table] = _ids(clash)
        ids = await _move(session, table, col, f"{col} = :s AND NOT (id = ANY(:clash))",
                          {"s": src.id, "clash": list(clash) or [uuid.uuid4()]}, target.id)
        if ids:
            moved[table] = moved.get(table, []) + ids
    if superseded:
        moved["superseded"] = superseded
    copied: dict[str, Any] = {}
    for col in COPY_IF_EMPTY:
        t_val = (await session.execute(text(f"SELECT {col} IS NULL FROM customers WHERE id = :t"),
                                       {"t": target.id})).scalar()
        s_has = (await session.execute(text(f"SELECT {col} IS NOT NULL FROM customers WHERE id = :s"),
                                       {"s": src.id})).scalar()
        if t_val and s_has:
            if col == "outlet_code":  # unique: it moves to the outlet (restored on unlink)
                code = src.outlet_code
                src.outlet_code = None
                await session.flush()
                target.outlet_code = code
                await session.flush()
            else:
                await session.execute(text(
                    f"UPDATE customers SET {col} = (SELECT {col} FROM customers WHERE id = :s) WHERE id = :t"),
                    {"s": src.id, "t": target.id})
            copied[col] = True
    if copied:
        before["copied_to_target"] = sorted(copied)
    src.merged_into_customer_id = target.id
    src.merged_at = _now()
    src.merged_by = actor.id if actor else None
    before["merged_source"] = str(src.id)
    await session.flush()
    await session.refresh(target)


async def _last_link(session, ledger_id: uuid.UUID, to_customer_id: uuid.UUID) -> Optional[OutletLinkEvent]:
    """The ledger's most recent LINK into its current outlet that has not been undone."""
    evs = (await session.execute(select(OutletLinkEvent).where(
        OutletLinkEvent.ledger_id == ledger_id, OutletLinkEvent.action.in_(("LINK", "UNLINK"))
    ).order_by(OutletLinkEvent.created_at.desc()))).scalars().all()
    for ev in evs:
        if ev.action == "UNLINK":
            return None
        if ev.to_customer_id == to_customer_id:
            return ev
    return None


async def unlink(session: AsyncSession, ledger_id: uuid.UUID, actor: Optional[User], note: Optional[str] = None,
                 batch_id: Optional[uuid.UUID] = None, link_event: Optional[OutletLinkEvent] = None) -> OutletLinkEvent:
    led = await _ledger(session, ledger_id)
    outlet = await _customer(session, led.customer_id)
    others = (await session.execute(select(TallyDebtorLedger).where(
        TallyDebtorLedger.customer_id == outlet.id, TallyDebtorLedger.id != led.id))).scalars().all()
    ev = link_event or await _last_link(session, led.id, outlet.id)
    moved: dict[str, Any] = {}
    if ev is not None and ev.from_customer_id:
        src = await session.get(Customer, ev.from_customer_id)
        if src is None:
            raise _conflict("The ledger's original outlet no longer exists")
        before = ev.before or {}
        if src.merged_into_customer_id == outlet.id:
            # restore the merged customer and every outlet row recorded when it was merged
            src.merged_into_customer_id = None
            src.merged_at = None
            src.merged_by = None
            await session.flush()
            for col in before.get("copied_to_target", []):
                if col == "outlet_code":
                    code = outlet.outlet_code
                    outlet.outlet_code = None
                    await session.flush()
                    src.outlet_code = code
                else:
                    await session.execute(text(f"UPDATE customers SET {col} = NULL WHERE id = :t"), {"t": outlet.id})
            await session.flush()
            cols = dict(OPERATIONAL) | {t: c for t, c, _o in UNIQUE_PER_OUTLET}
            for table, ids in (ev.moved or {}).items():
                col = cols.get(table)
                if table != "superseded" and col and ids:
                    await session.execute(text(f"UPDATE {table} SET {col} = :s WHERE id = ANY(:ids) AND {col} = :t"),
                                          {"s": src.id, "t": outlet.id, "ids": [uuid.UUID(i) for i in ids]})
        target_id = src.id
    else:
        if not others:
            raise _conflict("The ledger is already its own outlet")
        if outlet.tally_guid == led.tally_guid:
            raise _conflict("This is the outlet's own ledger; unlink the ledgers linked into it instead")
        taken = (await session.execute(select(Customer.id).where(Customer.tally_guid == led.tally_guid))).first()
        src = Customer(name=led.name, tally_guid=None if taken else led.tally_guid, address=led.address or "",
                       contact_number=(led.mobile or "")[:20], gst_number=led.gst_number, mobile_number=led.mobile,
                       location_status="MISSING", created_by=actor.id if actor else outlet.created_by,
                       tally_is_debtor=led.is_debtor)
        session.add(src)
        await session.flush()
        target_id = src.id
        before = {}
    for table in FINANCIAL_TABLES:
        ids = await _move(session, table, "customer_id", "tally_debtor_ledger_id = :l AND customer_id = :o",
                          {"l": led.id, "o": outlet.id}, target_id)
        if ids:
            moved[table] = ids
    was_primary = led.is_primary
    led.is_primary = False
    await session.flush()
    led.customer_id = target_id
    src_has_primary = (await session.execute(select(TallyDebtorLedger.id).where(
        TallyDebtorLedger.customer_id == target_id, TallyDebtorLedger.is_primary))).first() is not None
    prev = (before.get("ledger") or {}) if ev is not None else {}
    led.is_primary = not src_has_primary
    led.mapping_status = prev.get("mapping_status") or MAPPING_CONFIRMED
    if ev is not None:  # an undo restores the ledger's previous link audit stamps exactly
        led.linked_by = uuid.UUID(prev["linked_by"]) if prev.get("linked_by") else None
        led.linked_at = datetime.fromisoformat(prev["linked_at"]) if prev.get("linked_at") else None
    await session.flush()
    if was_primary and others:
        promote = next((o for o in others if o.tally_guid == outlet.tally_guid), None) or sorted(
            others, key=lambda o: o.name)[0]
        promote.is_primary = True
    await session.flush()
    return _event(session, "UNLINK", actor, led.id, outlet.id, target_id, moved,
                  {"link_event_id": str(ev.id)} if ev is not None else None, batch_id, note)


# ---------------------------------------------------------------------------
# Single changes
# ---------------------------------------------------------------------------

async def set_primary(session: AsyncSession, ledger_id: uuid.UUID, actor: Optional[User],
                      batch_id=None) -> OutletLinkEvent:
    led = await _ledger(session, ledger_id)
    old = (await session.execute(select(TallyDebtorLedger).where(
        TallyDebtorLedger.customer_id == led.customer_id, TallyDebtorLedger.is_primary))).scalar_one_or_none()
    if old is not None and old.id == led.id:
        raise _conflict("The ledger is already the outlet's primary ledger")
    if old is not None:
        old.is_primary = False
        await session.flush()
    led.is_primary = True
    cust = await _customer(session, led.customer_id)
    if cust.outlet_name_source != "ADMIN":
        cust.name = led.name
    await session.flush()
    return _event(session, "SET_PRIMARY", actor, led.id, led.customer_id, led.customer_id,
                  before={"previous_primary_ledger_id": str(old.id) if old else None}, batch_id=batch_id)


async def set_brand(session: AsyncSession, ledger_id: uuid.UUID, brand: Optional[str], actor: Optional[User],
                    batch_id=None) -> OutletLinkEvent:
    from app.services.brand_service import resolve_canonical_brand_name

    led = await _ledger(session, ledger_id)
    previous = led.brand_override
    prev_by, prev_at = led.brand_override_by, led.brand_override_at
    clean = (brand or "").strip()
    led.brand_override = resolve_canonical_brand_name(clean)[:100] if clean else None
    led.brand_override_by = actor.id if actor else None
    led.brand_override_at = _now()
    await session.flush()
    return _event(session, "BRAND_OVERRIDE", actor, led.id, led.customer_id, led.customer_id,
                  before={"brand_override": previous, "brand_override_by": str(prev_by) if prev_by else None,
                          "brand_override_at": prev_at.isoformat() if prev_at else None}, batch_id=batch_id)


async def set_outlet_code(session: AsyncSession, customer_id: uuid.UUID, outlet_code: Optional[str],
                          actor: Optional[User], batch_id=None) -> OutletLinkEvent:
    cust = await _customer(session, customer_id)
    code = (outlet_code or "").strip().upper() or None
    if code and (await session.execute(select(Customer.id).where(
            Customer.outlet_code == code, Customer.id != cust.id))).first():
        raise _conflict(f"Outlet code {code} is already used by another outlet", "DUPLICATE_OUTLET_CODE")
    previous = cust.outlet_code
    cust.outlet_code = code
    await session.flush()
    return _event(session, "OUTLET_CODE", actor, None, cust.id, cust.id, before={"outlet_code": previous},
                  batch_id=batch_id)


async def rename(session: AsyncSession, customer_id: uuid.UUID, name: str, actor: Optional[User],
                 batch_id=None) -> OutletLinkEvent:
    cust = await _customer(session, customer_id)
    clean = (name or "").strip()
    if not clean:
        raise BaseAPIException(status_code=422, detail="Name is required", error_code="VALIDATION_ERROR")
    before = {"name": cust.name, "outlet_name_source": cust.outlet_name_source}
    cust.name = clean[:150]
    cust.outlet_name_source = "ADMIN"
    await session.flush()
    return _event(session, "RENAME", actor, None, cust.id, cust.id, before=before, batch_id=batch_id)


async def review(session: AsyncSession, ledger_id: uuid.UUID, decision: str, actor: Optional[User],
                 batch_id=None) -> OutletLinkEvent:
    """KEEP_SEPARATE: a NEW_UNREVIEWED / REVIEW ledger is confirmed on its current outlet."""
    if decision != "KEEP_SEPARATE":
        raise BaseAPIException(status_code=422, detail="decision must be KEEP_SEPARATE", error_code="VALIDATION_ERROR")
    led = await _ledger(session, ledger_id)
    if led.mapping_status not in (MAPPING_NEW, MAPPING_REVIEW):
        raise _conflict(f"The ledger is not awaiting review (status {led.mapping_status})")
    previous = led.mapping_status
    led.mapping_status = MAPPING_CONFIRMED
    led.linked_by = actor.id if actor else None
    led.linked_at = _now()
    await session.flush()
    return _event(session, "REVIEW", actor, led.id, led.customer_id, led.customer_id,
                  before={"mapping_status": previous, "decision": decision}, batch_id=batch_id)


# ---------------------------------------------------------------------------
# Queues and events
# ---------------------------------------------------------------------------

async def queues(session: AsyncSession) -> dict:
    """
    Work queues of the Outlet Mapping page.

      new_unreviewed  debtor LEDGERS first seen in Tally after go-live, not reviewed yet
      missing_brand   debtor LEDGERS with no brand from Tally and no manual override (a brand is per ledger)
      missing_code    OUTLETS (not merged, holding at least one debtor ledger) with no outlet code - the code is
                      stored on the outlet, so a saved code takes the outlet off this list
      linked_outlets  number of outlets holding more than one debtor ledger

    Ledger rows carry their outlet's name / address / code / area / territory so the page can show which shop
    each row is; outlet rows carry their ledgers (name, brand, parent group, the Tally alias code if any).
    """
    from app.models.area import Area
    from app.models.territory import Territory
    from app.schemas.customer import LedgerRead

    debtor = TallyDebtorLedger.is_debtor.is_not(False)
    outlet_cols = (Customer.name, Customer.address, Customer.outlet_code, Area.name, Territory.name)

    def ledger_rows(where):
        return (
            select(TallyDebtorLedger, *outlet_cols)
            .join(Customer, Customer.id == TallyDebtorLedger.customer_id)
            .outerjoin(Area, Area.id == Customer.area_id)
            .outerjoin(Territory, Territory.id == Customer.territory_id)
            .where(*where)
            .order_by(Customer.name, TallyDebtorLedger.name)
            .limit(5000)
        )

    def ledger_out(rows):
        return [
            {
                **LedgerRead.from_model(l).model_dump(mode="json"),
                "customer_id": str(l.customer_id),
                "outlet_name": c_name,
                "outlet_address": (c_addr or "").strip() or None,
                "outlet_code": (c_code or "").strip() or None,
                "area_name": a_name,
                "territory_name": t_name,
            }
            for l, c_name, c_addr, c_code, a_name, t_name in rows
        ]

    new = (await session.execute(ledger_rows([debtor, TallyDebtorLedger.mapping_status == MAPPING_NEW]))).all()
    nob = (await session.execute(ledger_rows([debtor, func.coalesce(TallyDebtorLedger.brand_override, "") == "",
                                              func.coalesce(TallyDebtorLedger.brand_tally, "") == ""]))).all()

    # Outlets without an outlet code (one row per OUTLET - the code is saved on the outlet).
    has_debtor_ledger = select(TallyDebtorLedger.id).where(TallyDebtorLedger.customer_id == Customer.id, debtor).exists()
    outlets = (await session.execute(
        select(Customer.id, *outlet_cols)
        .outerjoin(Area, Area.id == Customer.area_id)
        .outerjoin(Territory, Territory.id == Customer.territory_id)
        .where(Customer.merged_into_customer_id.is_(None), func.coalesce(Customer.outlet_code, "") == "", has_debtor_ledger)
        .order_by(Customer.name)
        .limit(5000)
    )).all()
    ids = [o[0] for o in outlets]
    ledgers_by_outlet: dict = {}
    if ids:
        for l in (await session.execute(
            select(TallyDebtorLedger).where(TallyDebtorLedger.customer_id.in_(ids), debtor).order_by(TallyDebtorLedger.name)
        )).scalars().all():
            ledgers_by_outlet.setdefault(l.customer_id, []).append({
                "id": str(l.id), "name": l.name, "brand": l.effective_brand, "brand_source": l.brand_source,
                "parent_group": l.parent_group, "tally_outlet_code": (l.tally_outlet_code or "").strip() or None,
                "gst_number": l.gst_number, "mobile": l.mobile, "pincode": l.pincode, "is_primary": bool(l.is_primary),
            })
    noc = [
        {
            "customer_id": str(cid), "outlet_name": c_name, "outlet_address": (c_addr or "").strip() or None,
            "outlet_code": (c_code or "").strip() or None, "area_name": a_name, "territory_name": t_name,
            "ledgers": ledgers_by_outlet.get(cid, []),
        }
        for cid, c_name, c_addr, c_code, a_name, t_name in outlets
    ]

    linked = (await session.execute(select(func.count()).select_from(
        select(TallyDebtorLedger.customer_id).where(debtor).group_by(TallyDebtorLedger.customer_id)
        .having(func.count() > 1).subquery()))).scalar() or 0
    return {"new_unreviewed": ledger_out(new), "missing_brand": ledger_out(nob), "missing_code": noc,
            "linked_outlets": linked}


async def event_read(session: AsyncSession, ev: OutletLinkEvent) -> dict:
    led = await session.get(TallyDebtorLedger, ev.ledger_id) if ev.ledger_id else None
    actor = await session.get(User, ev.actor_id) if ev.actor_id else None
    return {"id": ev.id, "action": ev.action, "ledger_id": ev.ledger_id, "ledger_name": led.name if led else None,
            "from_customer_id": ev.from_customer_id, "to_customer_id": ev.to_customer_id, "batch_id": ev.batch_id,
            "actor": getattr(actor, "email", None), "note": ev.note, "created_at": ev.created_at}


async def list_events(session: AsyncSession, batch_id=None, ledger_id=None, limit: int = 200) -> list[OutletLinkEvent]:
    q = select(OutletLinkEvent)
    if batch_id:
        q = q.where(OutletLinkEvent.batch_id == batch_id)
    if ledger_id:
        q = q.where(OutletLinkEvent.ledger_id == ledger_id)
    return list((await session.execute(q.order_by(OutletLinkEvent.created_at.desc()).limit(limit))).scalars().all())


# ---------------------------------------------------------------------------
# Client workbook: preview / apply / revert
# ---------------------------------------------------------------------------

_PREVIEWS: dict[uuid.UUID, dict] = {}  # single uvicorn worker (deployment rule); 24 h lifetime
PREVIEW_TTL = timedelta(hours=24)

H_OUTLET = "Outlet ID"
H_SUGGEST = "Suggested shop"
H_LEDGER = "Tally ledger name"
H_YN = "Same shop? (Y/N)"
H_BELONGS = "Belongs to Outlet ID (if different)"
H_BRAND = "Brand (if blank)"
H_CODE = "Outlet / DMS code (if known)"
H_GUID = "Tally ID (do not change)"
H_STATUS = "Status code"


def _cell(v) -> str:
    return "" if v is None else str(v).strip()


def parse_workbook(content: bytes) -> tuple[list[dict], dict[str, str], dict[str, str], list[dict]]:
    """-> (ledger rows, brand answers by GUID, code answers by GUID, errors). Format of build_mapping_proposal.py."""
    from openpyxl import load_workbook

    errors: list[dict] = []
    try:
        wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    except Exception as ex:  # not an xlsx
        raise BaseAPIException(status_code=422, detail=f"Not a readable workbook: {str(ex)[:200]}",
                               error_code="INVALID_WORKBOOK")
    if "Ledgers" not in wb.sheetnames:
        raise BaseAPIException(status_code=422, detail="Sheet 'Ledgers' not found", error_code="INVALID_WORKBOOK")
    it = wb["Ledgers"].iter_rows(values_only=True)
    hdr = [_cell(h) for h in next(it, [])]
    need = (H_OUTLET, H_LEDGER, H_YN, H_BELONGS, H_GUID)
    missing = [h for h in need if h not in hdr]
    if missing:
        raise BaseAPIException(status_code=422, detail=f"Missing columns: {', '.join(missing)}",
                               error_code="INVALID_WORKBOOK")
    ix = {h: i for i, h in enumerate(hdr)}
    rows = []
    for n, r in enumerate(it, start=2):
        if r is None or all(v in (None, "") for v in r):
            continue
        g = lambda h: _cell(r[ix[h]]) if h in ix and ix[h] < len(r) else ""  # noqa: E731
        rows.append({"row": n, "guid": g(H_GUID), "label": g(H_OUTLET).upper(), "suggest": g(H_SUGGEST).upper(),
                     "ledger_name": g(H_LEDGER), "yn": g(H_YN).upper(), "belongs": g(H_BELONGS).upper(),
                     "brand": g(H_BRAND), "code": g(H_CODE), "status": g(H_STATUS)})
    brands: dict[str, str] = {}
    codes: dict[str, str] = {}
    for r in rows:
        if r["brand"]:
            brands[r["guid"]] = r["brand"]
        if r["code"]:
            codes[r["guid"]] = r["code"]
    for sheet, col, target in (("Missing brand", "Brand (fill)", brands),
                               ("Missing outlet code", "Outlet / DMS code (fill, if known)", codes)):
        if sheet not in wb.sheetnames:
            continue
        it2 = wb[sheet].iter_rows(values_only=True)
        h2 = [_cell(h) for h in next(it2, [])]
        if col not in h2 or H_GUID not in h2:
            continue
        for r in it2:
            if r is None:
                continue
            guid, val = _cell(r[h2.index(H_GUID)]), _cell(r[h2.index(col)])
            if guid and val:
                if target.get(guid) and target[guid] != val:
                    errors.append({"row": None, "tally_id": guid,
                                   "message": f"different answers on 'Ledgers' and '{sheet}': {target[guid]} / {val}"})
                target.setdefault(guid, val)
    return rows, brands, codes, errors


async def _ledger_totals(session: AsyncSession, ledger_ids=None) -> dict:
    """Per-ledger Tally balances and financial row counts (the invariants linking must not change)."""
    q = select(TallyDebtorLedger.id, TallyDebtorLedger.opening_balance, TallyDebtorLedger.closing_balance)
    if ledger_ids is not None:
        q = q.where(TallyDebtorLedger.id.in_(list(ledger_ids)))
    out = {str(i): {"opening": str(o), "closing": str(c)} for i, o, c in (await session.execute(q)).all()}
    for table in FINANCIAL_TABLES:
        for lid, n in (await session.execute(text(
                f"SELECT tally_debtor_ledger_id, count(*) FROM {table} WHERE tally_debtor_ledger_id = ANY(:ids) "
                f"GROUP BY 1"), {"ids": [uuid.UUID(k) for k in out]})).all():
            out[str(lid)][table] = n
    return out


async def _outstanding(session: AsyncSession, customer_ids) -> Decimal:
    from app.services.account_position import load_outlet_positions

    ids = [c for c in customer_ids if c]
    if not ids:
        return ZERO
    pos = await load_outlet_positions(session, ids)
    return sum((d.outlet.outstanding for d in pos.values()), ZERO)


async def build_preview(session: AsyncSession, content: bytes, actor: Optional[User]) -> dict:
    rows, brands, codes, errors = parse_workbook(content)
    warnings: list[dict] = []
    guids = [r["guid"] for r in rows if r["guid"]]
    leds = {l.tally_guid: l for l in (await session.execute(
        select(TallyDebtorLedger).where(TallyDebtorLedger.tally_guid.in_(guids)))).scalars().all()} if guids else {}
    seen: dict[str, int] = {}
    by_label: dict[str, list[dict]] = {}
    for r in rows:
        if not r["guid"]:
            errors.append({"row": r["row"], "tally_id": None, "message": "Tally ID is empty"})
            continue
        if r["guid"] in seen:
            errors.append({"row": r["row"], "tally_id": r["guid"],
                           "message": f"Tally ID listed twice (rows {seen[r['guid']]} and {r['row']})"})
            continue
        seen[r["guid"]] = r["row"]
        if r["guid"] not in leds:
            # A ledger created in Tally after FieldTrack's last sync. Only a CONFIRMED row needs it
            # (error: that row cannot be linked); an unanswered row must not block the rest (warning).
            entry = {"row": r["row"], "tally_id": r["guid"], "message": "Tally ID not known to FieldTrack (not synced yet)"}
            (errors if r["yn"] == "Y" else warnings).append(entry)
            continue
        by_label.setdefault(r["label"], []).append(r)
        if r["yn"] not in ("", "Y", "N"):
            errors.append({"row": r["row"], "tally_id": r["guid"], "message": f"answer must be Y or N, not {r['yn']!r}"})

    def anchor(label: str) -> Optional[dict]:
        """A label resolves to its first confirmed (Y) ledger, else its first ledger."""
        members = by_label.get(label) or []
        ys = [m for m in members if m["yn"] == "Y"]
        return (ys or members or [None])[0]

    links: list[dict] = []
    for r in rows:
        if r["guid"] not in leds or seen.get(r["guid"]) != r["row"] or r["yn"] != "Y":
            continue
        target_label = r["belongs"] or (r["suggest"] if r["status"].startswith("REVIEW") and r["suggest"] else r["label"])
        a = anchor(target_label)
        if a is None:
            errors.append({"row": r["row"], "tally_id": r["guid"], "message": f"Outlet ID {target_label} not found"})
            continue
        led, a_led = leds[r["guid"]], leds[a["guid"]]
        if led.is_debtor is False:
            errors.append({"row": r["row"], "tally_id": r["guid"], "message": "ledger is not a debtor in Tally"})
            continue
        if a["guid"] == r["guid"] or a_led.customer_id == led.customer_id:
            continue  # the anchor itself / already together
        links.append({"ledger_id": str(led.id), "ledger_name": led.name, "from_customer_id": str(led.customer_id),
                      "to_outlet_id_label": target_label, "to_customer_id": str(a_led.customer_id), "row": r["row"]})
    targets = {l["ledger_id"]: l["to_customer_id"] for l in links}
    # A ledger must not end up in two shops, and a target must not itself be moved away.
    moved_away = {l["from_customer_id"] for l in links}
    for l in links:
        if l["to_customer_id"] in moved_away and not any(
                x["from_customer_id"] == l["to_customer_id"] and x["to_customer_id"] == l["to_customer_id"] for x in links):
            src_led = [x for x in links if x["from_customer_id"] == l["to_customer_id"]]
            if src_led:
                errors.append({"row": l["row"], "tally_id": None,
                               "message": f"target outlet of {l['ledger_name']} is itself being linked elsewhere"})
    brand_updates = []
    for guid, b in brands.items():
        led = leds.get(guid)
        if led is None:
            errors.append({"row": None, "tally_id": guid, "message": "brand answer for an unknown Tally ID"})
            continue
        if led.brand_tally and led.brand_tally.strip().lower() != b.strip().lower():
            warnings.append({"row": seen.get(guid), "tally_id": guid,
                             "message": f"Tally already has brand {led.brand_tally}; '{b}' will be an override"})
        brand_updates.append({"ledger_id": str(led.id), "brand": b})
    code_updates = []
    for guid, code in codes.items():
        led = leds.get(guid)
        if led is None:
            errors.append({"row": None, "tally_id": guid, "message": "outlet code answer for an unknown Tally ID"})
            continue
        cid = targets.get(str(led.id), str(led.customer_id))
        clean = code.strip().upper()
        cust = await session.get(Customer, uuid.UUID(cid))
        if cust is not None and cust.outlet_code and cust.outlet_code != clean:
            warnings.append({"row": seen.get(guid), "tally_id": guid,
                             "message": f"outlet already has code {cust.outlet_code}; {clean} not applied"})
            continue
        taken = (await session.execute(select(Customer.id).where(Customer.outlet_code == clean,
                                                                 Customer.id != uuid.UUID(cid)))).first()
        if taken:
            errors.append({"row": seen.get(guid), "tally_id": guid, "message": f"outlet code {clean} is used by another outlet"})
            continue
        if not any(c["customer_id"] == cid for c in code_updates):
            code_updates.append({"customer_id": cid, "outlet_code": clean})

    affected = {uuid.UUID(l["from_customer_id"]) for l in links} | {uuid.UUID(l["to_customer_id"]) for l in links}
    total_before = await _outstanding(session, list(affected))
    outlets_before = (await session.execute(select(func.count()).select_from(Customer).where(
        Customer.tally_is_debtor.is_not(False), Customer.merged_into_customer_id.is_(None)))).scalar() or 0
    # each ledger leaving its customer empties it when all that customer's ledgers move
    leaving: dict[str, int] = {}
    for l in links:
        leaving[l["from_customer_id"]] = leaving.get(l["from_customer_id"], 0) + 1
    emptied = 0
    for cid, n in leaving.items():
        cnt = (await session.execute(select(func.count()).select_from(TallyDebtorLedger).where(
            TallyDebtorLedger.customer_id == uuid.UUID(cid)))).scalar() or 0
        if cnt <= n:
            emptied += 1
    pid = uuid.uuid4()
    preview = {
        "preview_id": pid, "expires_at": _now() + PREVIEW_TTL,
        "rows": len(rows), "confirmed_rows": sum(1 for r in rows if r["yn"] == "Y"),
        "ignored_rows": sum(1 for r in rows if r["yn"] != "Y"),
        "links": [{k: v for k, v in l.items() if k != "row"} for l in links],
        "brand_updates": brand_updates, "code_updates": code_updates,
        "errors": errors, "warnings": warnings,
        "outlets_before": outlets_before, "outlets_after": outlets_before - emptied,
        "totals_before": {"outstanding": total_before}, "totals_after": {"outstanding": total_before},
        "invariants_ok": not errors,
    }
    _PREVIEWS[pid] = {"preview": preview, "actor_id": actor.id if actor else None, "affected": affected}
    for k in [k for k, v in _PREVIEWS.items() if v["preview"]["expires_at"] < _now()]:
        _PREVIEWS.pop(k, None)
    return preview


async def apply_preview(session: AsyncSession, preview_id: uuid.UUID, actor: Optional[User]) -> dict:
    entry = _PREVIEWS.get(preview_id)
    if entry is None or entry["preview"]["expires_at"] < _now():
        raise _not_found("Preview not found or expired; upload the workbook again")
    p = entry["preview"]
    if p["errors"]:
        raise _conflict("The preview has errors; fix the workbook and preview again", "PREVIEW_HAS_ERRORS")
    batch = uuid.uuid4()
    affected = set(entry["affected"])
    ledger_ids = {uuid.UUID(l["ledger_id"]) for l in p["links"]}
    before_totals = await _ledger_totals(session, ledger_ids)
    before_out = await _outstanding(session, list(affected))
    events = 0
    for l in p["links"]:
        await link(session, uuid.UUID(l["ledger_id"]), uuid.UUID(l["to_customer_id"]), actor,
                   note=f"workbook row (preview {preview_id})", batch_id=batch)
        events += 1
    for b in p["brand_updates"]:
        await set_brand(session, uuid.UUID(b["ledger_id"]), b["brand"], actor, batch_id=batch)
        events += 1
    for c in p["code_updates"]:
        await set_outlet_code(session, uuid.UUID(c["customer_id"]), c["outlet_code"], actor, batch_id=batch)
        events += 1
    await session.flush()
    after_totals = await _ledger_totals(session, ledger_ids)
    live = {c for c in affected if (await session.get(Customer, c)) is not None
            and (await session.get(Customer, c)).merged_into_customer_id is None}
    after_out = await _outstanding(session, list(live))
    if before_totals != after_totals or before_out != after_out:
        await session.rollback()
        raise _conflict(f"Invariant check failed (outstanding {before_out} -> {after_out}); nothing was applied",
                        "INVARIANT_FAILED")
    _event(session, "BULK_APPLY", actor, batch_id=batch,
           moved={"links": len(p["links"]), "brands": len(p["brand_updates"]), "codes": len(p["code_updates"])},
           note=f"preview {preview_id}")
    await session.commit()
    _PREVIEWS.pop(preview_id, None)
    return {"batch_id": batch, "applied": len(p["links"]), "events": events}


async def revert_batch(session: AsyncSession, batch_id: uuid.UUID, actor: Optional[User]) -> dict:
    evs = (await session.execute(select(OutletLinkEvent).where(OutletLinkEvent.batch_id == batch_id)
                                 .order_by(OutletLinkEvent.created_at.desc()))).scalars().all()
    if not evs:
        raise _not_found("Batch not found")
    if any(e.action == "BULK_REVERT" for e in evs):
        raise _conflict("This batch has already been reverted")
    rev = uuid.uuid4()
    n = 0
    for ev in evs:
        b = ev.before or {}
        if ev.action == "LINK":
            await unlink(session, ev.ledger_id, actor, note=f"revert of batch {batch_id}", batch_id=rev, link_event=ev)
        elif ev.action == "BRAND_OVERRIDE":
            led = await session.get(TallyDebtorLedger, ev.ledger_id)
            if led is not None:
                led.brand_override = b.get("brand_override")
                led.brand_override_by = uuid.UUID(b["brand_override_by"]) if b.get("brand_override_by") else None
                led.brand_override_at = datetime.fromisoformat(b["brand_override_at"]) if b.get("brand_override_at") else None
        elif ev.action == "OUTLET_CODE":
            c = await session.get(Customer, ev.to_customer_id)
            if c is not None:
                c.outlet_code = b.get("outlet_code")
        elif ev.action == "RENAME":
            c = await session.get(Customer, ev.to_customer_id)
            if c is not None:
                c.name, c.outlet_name_source = b.get("name", c.name), b.get("outlet_name_source", "TALLY_PRIMARY")
        else:
            continue
        n += 1
        await session.flush()
    _event(session, "BULK_REVERT", actor, batch_id=batch_id, moved={"reverted": n, "revert_batch": str(rev)})
    await session.commit()
    return {"batch_id": batch_id, "reverted": n}
