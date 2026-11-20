"""
Tally v2 sync: ledgers, every debtor voucher, Bills Receivable and the voucher
GUID manifest (agent 2.0). Tally is authoritative for all of it.

Classification (one row per voucher x debtor ledger; receivable = -Tally amount):
  * cancelled / optional voucher, or a non-accounting voucher type -> nothing
    (any row previously synced from it is retired)
  * Sales-parent voucher, debtor debited        -> Invoice  (source TALLY)
  * Receipt-parent voucher, debtor credited     -> Payment  (source TALLY, VERIFIED)
  * any other debtor line                       -> TallyLedgerAdjustment (signed)
Row key: the voucher GUID when the voucher touches one debtor ledger, otherwise
"<GUID>::<ledger name>".

A row Tally no longer has is RETIRED, never deleted: invoices / payments move to
source TALLY_RETIRED (every `source == TALLY` money query then ignores them),
adjustments to state RETIRED. A voucher that comes back reactivates its row.

Nothing is invented: a line whose ledger is not a known customer, or a sales
voucher without a number, fails (the agent quarantines it and retries); due
dates come only from Tally's Bills Receivable; payment mode is UNSPECIFIED when
Tally states none and the money did not go to a cash ledger; bill allocations
link to invoices by bill name only (no FIFO).
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Iterable, Optional

from sqlalchemy import and_, delete, func, or_, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.customer import Customer
from app.models.customer_brand import CustomerBrand
from app.models.invoice import Invoice, InvoiceSource, financial_year_of
from app.models.payment import (
    Payment,
    PaymentBrandAllocation,
    PaymentMethod,
    PaymentSource,
    PaymentStatus,
)
from app.models.payment_invoice_allocation import PaymentInvoiceAllocation
from app.models.sync_agent import SyncAgent
from app.models.tally_debtor_ledger import MAPPING_AUTO, MAPPING_NEW, TallyDebtorLedger
from app.models.tally_voucher_index import STATE_ACTIVE, STATE_DELETED, TallyVoucherIndex
from app.models.tally_ledger import (
    ADJUSTMENT_ACTIVE,
    ADJUSTMENT_RETIRED,
    TallyLedgerAdjustment,
    TallyManifestGuid,
    TallyOpenBill,
    TallySnapshotRun,
)
from app.schemas.tally_sync_v2 import (
    BankAllocation,
    BillAllocation,
    BillsSyncBatch,
    LedgerItem,
    LedgerSyncBatch,
    ManifestSyncBatch,
    V2SyncResult,
    VoucherItem,
    VoucherSyncBatch,
)
from app.services import tally_audit_service
from app.services.brand_service import ensure_brand, resolve_canonical_brand_name

ZERO = Decimal("0.00")
CENT = Decimal("0.01")

# Voucher-type parents that never post to ledgers (Tally's reserved non-accounting types).
NON_ACCOUNTING_PARENTS = frozenset(p.lower() for p in (
    "Sales Order", "Purchase Order", "Delivery Note", "Receipt Note", "Rejections In",
    "Rejections Out", "Stock Journal", "Physical Stock", "Material In", "Material Out",
    "Job Work In Order", "Job Work Out Order", "Memorandum", "Reversing Journal", "Attendance",
))

KIND_INVOICE = "INVOICE"
KIND_PAYMENT = "PAYMENT"
KIND_ADJUSTMENT = "ADJUSTMENT"

# Retirement reasons
R_CANCELLED = "CANCELLED"
R_OPTIONAL = "OPTIONAL"
R_NON_ACCOUNTING = "NON_ACCOUNTING_TYPE"
R_LINE_REMOVED = "NO_LONGER_A_DEBTOR_LINE"
R_RECLASSIFIED = "RECLASSIFIED"
R_DELETED = "DELETED_IN_TALLY"

# Safety floor: a manifest / full ledger snapshot covering less than this share of
# what FieldTrack already holds is treated as incomplete and applied to nothing.
SNAPSHOT_COMPLETENESS_FLOOR = Decimal("0.5")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _q(v: Decimal) -> Decimal:
    return Decimal(v).quantize(CENT)


def _clip(value: Optional[str], size: int) -> Optional[str]:
    value = (value or "").strip()
    return value[:size] if value else None


# ---------------------------------------------------------------------------
# Pure classification
# ---------------------------------------------------------------------------

@dataclass
class LinePlan:
    key: str
    kind: str
    ledger_name: str
    ledger_guid: Optional[str]
    receivable: Decimal  # signed: > 0 the customer owes more
    brand: Optional[str]
    bills: list[BillAllocation] = field(default_factory=list)


def exclusion_reason(v: VoucherItem) -> Optional[str]:
    if v.is_cancelled:
        return R_CANCELLED
    if v.is_optional:
        return R_OPTIONAL
    if (v.voucher_parent or v.voucher_type or "").strip().lower() in NON_ACCOUNTING_PARENTS:
        return R_NON_ACCOUNTING
    return None


def _parent(v: VoucherItem) -> str:
    return (v.voucher_parent or v.voucher_type or "").strip().lower()


def plan_voucher(v: VoucherItem) -> list[LinePlan]:
    """Debtor lines of an included voucher, aggregated per ledger and classified."""
    agg: dict[str, LinePlan] = {}
    order: list[str] = []
    for line in v.debtor_lines:
        name = line.ledger_name.strip()
        k = name.lower()
        if k not in agg:
            agg[k] = LinePlan("", "", name, line.ledger_guid, ZERO, line.brand)
            order.append(k)
        p = agg[k]
        p.receivable += -Decimal(line.amount)
        p.bills.extend(line.bill_allocations)
        p.ledger_guid = p.ledger_guid or line.ledger_guid
        p.brand = p.brand or line.brand
    plans = [agg[k] for k in order if _q(agg[k].receivable) != ZERO]
    multi = len(order) > 1
    parent = _parent(v)
    for p in plans:
        p.receivable = _q(p.receivable)
        p.key = f"{v.guid}::{p.ledger_name}" if multi else v.guid
        if parent == "sales" and p.receivable > 0:
            p.kind = KIND_INVOICE
        elif parent == "receipt" and p.receivable < 0:
            p.kind = KIND_PAYMENT
        else:
            p.kind = KIND_ADJUSTMENT
    return plans


ONLINE_TRANSACTION_TYPES = frozenset((
    "inter bank transfer", "same bank transfer", "e-fund transfer", "electronic cheque", "electronic dd/po",
    "neft", "rtgs", "imps", "upi",
))


def payment_details(v: VoucherItem) -> dict:
    """Payment mode / cheque / UTR exactly as the voucher's bank allocations state them.

    Proven on the client's data (13 Nov 2026): Tally fills a unique reference
    number on every bank allocation itself (an internal id, not a bank UTR), and
    bank-statement imports carry the default type "Cheque" with no instrument
    number even for RTGS receipts. So:
      Cash                                  -> CASH
      Cheque / Cheque/DD WITH an instrument -> CHEQUE (instrument = cheque number)
      a transfer type                       -> ONLINE (instrument number = UTR, if given)
      anything else, or no type and no cash ledger -> UNSPECIFIED (narration kept)
    """
    banks: list[BankAllocation] = []
    for line in v.counter_lines:
        banks.extend(line.bank_allocations)
    for line in v.debtor_lines:
        banks.extend(line.bank_allocations)

    def first(attr: str) -> Optional[str]:
        return next((str(getattr(b, attr)).strip() for b in banks if (getattr(b, attr) or "")
                     and str(getattr(b, attr)).strip()), None)

    raw_type = first("transaction_type")
    instrument = first("instrument_number")
    t = (raw_type or "").lower()
    if t == "cash":
        method = PaymentMethod.CASH
    elif t in ("cheque", "cheque/dd", "dd") and instrument:
        method = PaymentMethod.CHEQUE
    elif t in ONLINE_TRANSACTION_TYPES:
        method = PaymentMethod.ONLINE
    elif not t:
        classes = {(c.ledger_class or "OTHER").upper() for c in v.counter_lines if Decimal(c.amount) != 0}
        method = PaymentMethod.CASH if classes == {"CASH"} else PaymentMethod.UNSPECIFIED
    else:
        method = PaymentMethod.UNSPECIFIED
    return {
        "method": method,
        "transaction_type": _clip(raw_type, 50),
        "cheque_number": _clip(instrument, 50) if method == PaymentMethod.CHEQUE else None,
        "utr_reference": _clip(instrument, 50) if method == PaymentMethod.ONLINE else None,
        "cheque_bank_name": _clip(first("bank_name"), 150),
        "bank_details": [b.model_dump(mode="json", exclude_none=True) for b in banks] or None,
    }


def _bill_json(bills: Iterable[BillAllocation]) -> Optional[list[dict]]:
    out = [b.model_dump(mode="json", exclude_none=True) for b in bills]
    return out or None


def _raised_bill_name(bills: list[BillAllocation]) -> Optional[str]:
    """The bill a sales invoice raises: its New Ref allocation (or its only allocation)."""
    named = [b for b in bills if (b.name or "").strip()]
    new_ref = [b for b in named if (b.bill_type or "").strip().lower() == "new ref"]
    pick = new_ref[0] if new_ref else (named[0] if len(named) == 1 else None)
    return _clip(pick.name, 150) if pick else None


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

async def system_user_id(session: AsyncSession) -> uuid.UUID:
    from app.services.tally_sync_service import _get_system_user_id
    return await _get_system_user_id(session)


async def outlet_of(session: AsyncSession, cust: Optional[Customer]) -> Optional[Customer]:
    """The physical outlet a customer row stands for (follows merged_into; never loops)."""
    seen = set()
    while cust is not None and cust.merged_into_customer_id and cust.id not in seen:
        seen.add(cust.id)
        nxt = await session.get(Customer, cust.merged_into_customer_id)
        if nxt is None:
            break
        cust = nxt
    return cust


async def ensure_ledger_for_customer(session: AsyncSession, cust: Customer,
                                     status: str = MAPPING_AUTO) -> Optional[TallyDebtorLedger]:
    """A customer that holds a Tally GUID but no ledger row yet (created by the v1 sync after the
    migration, or by an older path) gets its 1:1 primary ledger - exactly what the migration backfill does."""
    if not cust.tally_guid:
        return None
    led = (await session.execute(
        select(TallyDebtorLedger).where(TallyDebtorLedger.tally_guid == cust.tally_guid)
    )).scalar_one_or_none()
    if led is not None:
        return led
    has_primary = (await session.execute(
        select(TallyDebtorLedger.id).where(TallyDebtorLedger.customer_id == cust.id, TallyDebtorLedger.is_primary)
    )).first() is not None
    led = TallyDebtorLedger(
        customer_id=cust.id, tally_guid=cust.tally_guid, name=(cust.name or cust.tally_guid)[:150],
        parent_group=cust.tally_parent_group, aliases=cust.tally_aliases, tally_outlet_code=cust.outlet_code,
        is_debtor=cust.tally_is_debtor, is_bill_wise=cust.tally_is_bill_wise, credit_period=cust.tally_credit_period,
        opening_balance=cust.tally_opening_balance, opening_balance_as_of=cust.tally_opening_balance_as_of,
        closing_balance=cust.tally_closing_balance, closing_balance_at=cust.tally_closing_balance_at,
        gst_number=cust.gst_number, mobile=cust.mobile_number or None, address=cust.address or None,
        is_primary=not has_primary, mapping_status=status,
    )
    session.add(led)
    await session.flush()
    return led


class LedgerResolver:
    """Tally ledger -> (physical outlet, ledger row), cached per batch.

    By ledger GUID first (the ledger row, else a legacy customer holding that GUID, which gets its
    1:1 ledger), then by exact LEDGER name (unique). A legacy customer without a ledger row is
    matched by exact name only when unique and not merged (pre-2.1.0 compatibility)."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.cache: dict[tuple[Optional[str], str], tuple[Optional[Customer], Optional[TallyDebtorLedger]]] = {}

    async def resolve(self, ledger_guid: Optional[str], ledger_name: str
                      ) -> tuple[Optional[Customer], Optional[TallyDebtorLedger]]:
        key = (ledger_guid, ledger_name.strip().lower())
        if key in self.cache:
            return self.cache[key]
        s = self.session
        led = None
        if ledger_guid:
            led = (await s.execute(
                select(TallyDebtorLedger).where(TallyDebtorLedger.tally_guid == ledger_guid)
            )).scalar_one_or_none()
            if led is None:
                cust = (await s.execute(select(Customer).where(Customer.tally_guid == ledger_guid))).scalar_one_or_none()
                if cust is not None:
                    led = await ensure_ledger_for_customer(s, cust)
        if led is None:
            rows = (await s.execute(
                select(TallyDebtorLedger).where(func.lower(TallyDebtorLedger.name) == key[1])
            )).scalars().all()
            if len(rows) > 1:
                debtors = [r for r in rows if r.is_debtor]
                rows = debtors if len(debtors) == 1 else []
            led = rows[0] if len(rows) == 1 else None
        if led is None:
            rows = (await s.execute(
                select(Customer).where(func.lower(Customer.name) == key[1], Customer.merged_into_customer_id.is_(None))
            )).scalars().all()
            if len(rows) > 1:
                debtors = [r for r in rows if r.tally_is_debtor]
                rows = debtors if len(debtors) == 1 else []
            if len(rows) == 1:
                cust = rows[0]
                led = await ensure_ledger_for_customer(s, cust)
                if led is None:  # a customer never seen in Tally (no GUID): outlet only
                    self.cache[key] = (cust, None)
                    return self.cache[key]
        cust = await outlet_of(s, await s.get(Customer, led.customer_id)) if led is not None else None
        self.cache[key] = (cust, led)
        return self.cache[key]

    async def get(self, ledger_guid: Optional[str], ledger_name: str) -> Optional[Customer]:
        return (await self.resolve(ledger_guid, ledger_name))[0]


CustomerResolver = LedgerResolver  # backwards-compatible name


def _voucher_rows_clause(model, guid: str):
    return or_(
        model.tally_voucher_guid == guid,
        model.source_reference == guid,
        model.source_reference.like(f"{guid}::%"),
    )


async def _retire_invoice(inv: Invoice, reason: str, now: datetime) -> bool:
    if inv.source != InvoiceSource.TALLY:
        return False
    inv.source = InvoiceSource.TALLY_RETIRED
    inv.tally_retired_at = now
    inv.tally_retired_reason = reason
    return True


async def _retire_payment(p: Payment, reason: str, now: datetime) -> bool:
    if p.source != PaymentSource.TALLY:
        return False  # a MANUAL field collection is FieldTrack's record: never retired by Tally
    p.source = PaymentSource.TALLY_RETIRED
    p.tally_retired_at = now
    p.tally_retired_reason = reason
    return True


def _retire_adjustment(a: TallyLedgerAdjustment, reason: str, now: datetime) -> bool:
    if a.state != ADJUSTMENT_ACTIVE:
        return False
    a.state = ADJUSTMENT_RETIRED
    a.retired_at = now
    a.retired_reason = reason
    return True


async def retire_voucher_rows(
    session: AsyncSession, guid: str, keep: dict[str, set[str]], reason: str, now: datetime
) -> int:
    """Retire every live row of voucher `guid` whose key is not kept for its kind."""
    n = 0
    retired_invoices = []
    for inv in (await session.execute(
        select(Invoice).where(_voucher_rows_clause(Invoice, guid), Invoice.source == InvoiceSource.TALLY)
    )).scalars():
        if inv.source_reference not in keep.get(KIND_INVOICE, set()):
            n += await _retire_invoice(inv, reason, now)
            retired_invoices.append(inv.id)
    for p in (await session.execute(
        select(Payment).where(_voucher_rows_clause(Payment, guid), Payment.source == PaymentSource.TALLY)
    )).scalars():
        if p.source_reference not in keep.get(KIND_PAYMENT, set()):
            n += await _retire_payment(p, reason, now)
    for a in (await session.execute(
        select(TallyLedgerAdjustment).where(
            _voucher_rows_clause(TallyLedgerAdjustment, guid), TallyLedgerAdjustment.state == ADJUSTMENT_ACTIVE
        )
    )).scalars():
        if a.source_reference not in keep.get(KIND_ADJUSTMENT, set()):
            n += _retire_adjustment(a, reason, now)
    await relink_receipts_of_invoices(session, retired_invoices)
    return n


async def relink_receipts_of_invoices(session: AsyncSession, invoice_ids) -> int:
    """Release 3.0: invoices were retired (cancelled / deleted / re-classified in Tally). Every Tally receipt linked to
    one of them is linked again from its stored allocations: the bill now resolves to the invoice Tally still holds
    under that name (bill numbers restart each FY), or stays unlinked. Before 3.0 such a receipt kept pointing at the
    retired invoice."""
    ids = list({i for i in invoice_ids if i})
    if not ids:
        return 0
    await session.flush()
    pays = (await session.execute(
        select(Payment).where(Payment.source == PaymentSource.TALLY,
                              Payment.id.in_(select(PaymentInvoiceAllocation.payment_id)
                                             .where(PaymentInvoiceAllocation.invoice_id.in_(ids))))
    )).scalars().all()
    st = _Stats()
    for pay in pays:
        await _apply_receipt_bills(session, pay, pay.customer_id, _stored_bills(pay.tally_bill_allocations), st,
                                   pay.tally_debtor_ledger_id)
    if pays:
        await session.flush()
    return len(pays)


async def _brand(session: AsyncSession, raw: Optional[str]) -> tuple[Optional[str], Optional[uuid.UUID]]:
    if not raw:
        return None, None
    b = await ensure_brand(session, raw)
    return (b.name if b else resolve_canonical_brand_name(raw)), (b.id if b else None)


# ---------------------------------------------------------------------------
# Vouchers
# ---------------------------------------------------------------------------

@dataclass
class _Stats:
    created: int = 0
    updated: int = 0
    retired: int = 0
    failed: int = 0
    by_kind: dict = field(default_factory=lambda: {KIND_INVOICE: 0, KIND_PAYMENT: 0, KIND_ADJUSTMENT: 0})
    excluded: dict = field(default_factory=dict)
    unresolved_bills: int = 0
    unresolved_bill_amount: Decimal = ZERO
    errors: list = field(default_factory=list)


def _named_bill_totals(bills: Iterable[BillAllocation]) -> tuple[dict[str, Decimal], dict[str, str]]:
    """Signed total per bill name, exactly as Tally gives it on a receipt's debtor line: + settles the bill,
    - re-opens it (money moved from one bill to another inside the receipt). A Tally bill is the ledger + its
    name, whatever the allocation type (Agst Ref, New Ref, Advance), so every named allocation counts;
    only On Account (no bill) is skipped."""
    totals: dict[str, Decimal] = {}
    types: dict[str, str] = {}
    for b in bills:
        name = (b.name or "").strip()
        btype = (b.bill_type or "").strip()
        if not name or btype.lower() == "on account":
            continue
        totals[name] = totals.get(name, ZERO) + _q(Decimal(b.amount))
        types.setdefault(name, btype or "Agst Ref")
    return totals, types


async def _invoice_for_bill(session: AsyncSession, customer_id: uuid.UUID, ledger_id: Optional[uuid.UUID],
                            name: str, on: Optional[date]) -> Optional[Invoice]:
    """The invoice that raised this Tally bill for this customer (within the receipt's own ledger: a shop's brand
    ledgers may reuse a bill name). When several invoices carry the name (numbers restart each FY), the latest
    one dated on or before the receipt; when every one is later (an advance received before its invoice), the
    earliest of them."""
    rows = (await session.execute(
        select(Invoice).where(
            Invoice.customer_id == customer_id,
            Invoice.source == InvoiceSource.TALLY,
            Invoice.tally_bill_name == name,
            *([or_(Invoice.tally_debtor_ledger_id == ledger_id, Invoice.tally_debtor_ledger_id.is_(None))]
              if ledger_id else []),
        ).order_by(Invoice.invoice_date, Invoice.source_reference)
    )).scalars().all()
    if not rows:
        return None
    if on is None:
        return rows[-1]
    before = [i for i in rows if i.invoice_date <= on]
    return before[-1] if before else rows[0]


async def _apply_receipt_bills(
    session: AsyncSession, payment: Payment, customer_id: uuid.UUID, bills: list[BillAllocation], st: _Stats,
    ledger_id: Optional[uuid.UUID] = None,
) -> None:
    """Tally's bill-wise settlement replaces every earlier link of this receipt.

    Each named allocation links, with its Tally sign, to the invoice raising that bill: + settles it, - re-opens
    it (a receipt may move money between bills; only the net equals the receipt). Allocations to the same
    invoice are netted. On-account parts and bills not (yet) in FieldTrack stay unlinked; the receipt's
    allocations are kept on the payment, so a bill whose invoice arrives later is linked then
    (relink_receipts_for_invoice)."""
    await session.execute(delete(PaymentInvoiceAllocation).where(PaymentInvoiceAllocation.payment_id == payment.id))
    totals, types = _named_bill_totals(bills)
    resolved: dict[uuid.UUID, Decimal] = {}
    names: dict[uuid.UUID, tuple[str, str]] = {}
    for name, amt in totals.items():
        if amt == ZERO:
            continue
        inv = await _invoice_for_bill(session, customer_id, ledger_id, name, payment.payment_date)
        if inv is None:
            st.unresolved_bills += 1
            st.unresolved_bill_amount += amt.copy_abs()
            continue
        resolved[inv.id] = resolved.get(inv.id, ZERO) + amt
        names.setdefault(inv.id, (name, types[name]))
    resolved = {k: v for k, v in resolved.items() if v != ZERO}
    # Guard against inconsistent data: Tally's own allocations of this line (every one, signed, on-account
    # included) never exceed the receipt. The linked part alone may (a re-opened bill not in FieldTrack).
    total = sum((_q(Decimal(b.amount)) for b in bills), ZERO)
    if total - payment.amount > CENT:
        st.errors.append({"identifier": payment.source_reference,
                          "error": f"bill allocations {total} exceed receipt {payment.amount}; left unlinked"})
        resolved = {}
    for inv_id, amt in resolved.items():
        session.add(PaymentInvoiceAllocation(
            payment_id=payment.id, invoice_id=inv_id, bill_name=names[inv_id][0][:150],
            bill_type=names[inv_id][1][:50], allocated_amount=amt,
        ))
    settled = [k for k, v in resolved.items() if v > ZERO]
    payment.invoice_id = settled[0] if len(settled) == 1 and len(resolved) == 1 else None


def _stored_bills(raw: Optional[list[dict]]) -> list[BillAllocation]:
    return [BillAllocation(**b) for b in (raw or []) if isinstance(b, dict) and b.get("amount") is not None]


async def relink_receipts_for_invoice(session: AsyncSession, inv: Invoice, st: Optional[_Stats] = None) -> int:
    """An invoice raising a bill has arrived (or changed): every Tally receipt of the same customer whose stored
    allocations name that bill is linked again from those allocations. Covers receipts loaded before their
    invoice (a historical year loaded after the live one; an advance received before the invoice).
    Returns the number of receipts re-linked."""
    name = (inv.tally_bill_name or "").strip()
    if not name:
        return 0
    pays = (await session.execute(
        select(Payment).where(
            Payment.customer_id == inv.customer_id,
            Payment.source == PaymentSource.TALLY,
            Payment.tally_bill_allocations.is_not(None),
            Payment.tally_bill_allocations.contains([{"name": name}]),
            *([or_(Payment.tally_debtor_ledger_id == inv.tally_debtor_ledger_id,
                   Payment.tally_debtor_ledger_id.is_(None))] if inv.tally_debtor_ledger_id else []),
        )
    )).scalars().all()
    stats = st or _Stats()
    for pay in pays:
        await _apply_receipt_bills(session, pay, pay.customer_id, _stored_bills(pay.tally_bill_allocations), stats,
                                   pay.tally_debtor_ledger_id)
    if pays:
        await session.flush()
    return len(pays)


async def relink_all_receipts(session: AsyncSession) -> dict:
    """Maintenance: rebuild the links of every Tally receipt that carries its stored allocations."""
    st = _Stats()
    pays = (await session.execute(
        select(Payment).where(Payment.source == PaymentSource.TALLY, Payment.tally_bill_allocations.is_not(None))
    )).scalars().all()
    for pay in pays:
        await _apply_receipt_bills(session, pay, pay.customer_id, _stored_bills(pay.tally_bill_allocations), st,
                                   pay.tally_debtor_ledger_id)
    await session.flush()
    return {"receipts": len(pays), "unresolved_bills": st.unresolved_bills,
            "unresolved_bill_amount": str(st.unresolved_bill_amount), "errors": st.errors}


async def _upsert_invoice(session, v: VoucherItem, p: LinePlan, cust: Customer, uid, now, ledger_id=None) -> bool:
    number = (v.voucher_number or "").strip()
    if not number:
        raise ValueError("sales voucher has no voucher number")
    brand, brand_id = await _brand(session, p.brand)
    inv = (await session.execute(select(Invoice).where(Invoice.source_reference == p.key))).scalar_one_or_none()
    created = inv is None
    if created:
        inv = Invoice(source_reference=p.key, created_by=uid, due_date=None)
        session.add(inv)
    inv.customer_id = cust.id
    inv.tally_debtor_ledger_id = ledger_id
    inv.invoice_number = number[:100]
    inv.invoice_date = v.date
    inv.amount = p.receivable
    inv.source = InvoiceSource.TALLY
    if brand:
        inv.brand, inv.brand_id = brand, brand_id
    raised = _raised_bill_name(p.bills)
    if raised or created:
        inv.tally_bill_name = raised
    inv.tally_voucher_guid = v.guid
    inv.tally_voucher_type = v.voucher_type[:100]
    inv.tally_alter_id = v.alter_id
    inv.narration = v.narration
    inv.tally_retired_at = None
    inv.tally_retired_reason = None
    await session.flush()
    await relink_receipts_for_invoice(session, inv)  # receipts that reached FieldTrack before this invoice
    return created


async def _upsert_payment(session, v: VoucherItem, p: LinePlan, cust: Customer, uid, now, st: _Stats,
                          ledger_id=None) -> bool:
    d = payment_details(v)
    pay = (await session.execute(
        select(Payment).where(Payment.source_reference == p.key).order_by(Payment.created_at)
    )).scalars().first()
    created = pay is None
    amount = -p.receivable
    if created:
        pay = Payment(source_reference=p.key, created_by=uid, employee_id=None, status=PaymentStatus.VERIFIED,
                      source=PaymentSource.TALLY)
        session.add(pay)
    elif pay.source != PaymentSource.MANUAL:
        pay.source = PaymentSource.TALLY  # legacy import / retired copy is Tally's again
    pay.customer_id = cust.id
    if pay.source != PaymentSource.MANUAL:
        pay.tally_debtor_ledger_id = ledger_id
    pay.amount = amount
    pay.payment_date = v.date
    pay.payment_method = d["method"]
    pay.cheque_number = d["cheque_number"]
    pay.cheque_bank_name = d["cheque_bank_name"]
    pay.utr_reference = d["utr_reference"]
    pay.tally_transaction_type = d["transaction_type"]
    pay.tally_bank_details = d["bank_details"]
    pay.tally_bill_allocations = _bill_json(p.bills)
    label = f"Tally {v.voucher_type} {v.voucher_number or ''}".strip()
    pay.notes = v.narration or label
    pay.narration = v.narration
    pay.tally_voucher_guid = v.guid
    pay.tally_voucher_type = v.voucher_type[:100]
    pay.tally_alter_id = v.alter_id
    pay.tally_retired_at = None
    pay.tally_retired_reason = None
    if pay.source == PaymentSource.TALLY:
        pay.status = PaymentStatus.VERIFIED
    await session.flush()

    if pay.source == PaymentSource.TALLY:
        brand, brand_id = await _brand(session, p.brand)
        await session.execute(delete(PaymentBrandAllocation).where(PaymentBrandAllocation.payment_id == pay.id))
        if brand:
            session.add(PaymentBrandAllocation(payment_id=pay.id, brand=brand, brand_id=brand_id,
                                               allocated_amount=amount))
        await _apply_receipt_bills(session, pay, cust.id, p.bills, st, ledger_id)
    return created


async def _upsert_adjustment(session, v: VoucherItem, p: LinePlan, cust: Customer, ledger_id=None) -> bool:
    adj = (await session.execute(
        select(TallyLedgerAdjustment).where(TallyLedgerAdjustment.source_reference == p.key)
    )).scalar_one_or_none()
    created = adj is None
    if created:
        adj = TallyLedgerAdjustment(source_reference=p.key)
        session.add(adj)
    adj.customer_id = cust.id
    adj.tally_debtor_ledger_id = ledger_id
    adj.tally_voucher_guid = v.guid
    adj.voucher_type = v.voucher_type[:100]
    adj.voucher_parent = _clip(v.voucher_parent, 100)
    adj.voucher_number = _clip(v.voucher_number, 100)
    adj.voucher_date = v.date
    adj.financial_year = financial_year_of(v.date)
    adj.amount = p.receivable
    adj.narration = v.narration
    adj.bill_allocations = _bill_json(p.bills)
    adj.tally_alter_id = v.alter_id
    adj.state = ADJUSTMENT_ACTIVE
    adj.retired_at = None
    adj.retired_reason = None
    await session.flush()
    return created


async def _stored_alter_id(session, guid: str) -> Optional[int]:
    vals = []
    for model in (Invoice, Payment, TallyLedgerAdjustment):
        vals.append((await session.execute(
            select(func.max(model.tally_alter_id)).where(_voucher_rows_clause(model, guid))
        )).scalar())
    vals = [x for x in vals if x is not None]
    return max(vals) if vals else None


async def _stamp_alter_id(session, guid: str, alter_id: Optional[int]) -> None:
    if alter_id is None:
        return
    for model in (Invoice, Payment, TallyLedgerAdjustment):
        await session.execute(update(model).where(_voucher_rows_clause(model, guid)).values(tally_alter_id=alter_id))


async def _index_voucher(session, v: VoucherItem, company_guid: Optional[str]) -> None:
    """Release 3.0: record that FieldTrack has processed this version of the voucher (same savepoint as its rows)."""
    stmt = pg_insert(TallyVoucherIndex).values(guid=v.guid, alter_id=int(v.alter_id or 0), voucher_date=v.date,
                                               state=STATE_ACTIVE, company_guid=company_guid)
    stmt = stmt.on_conflict_do_update(index_elements=["guid"], set_={
        "alter_id": func.greatest(TallyVoucherIndex.alter_id, stmt.excluded.alter_id),
        "voucher_date": stmt.excluded.voucher_date,
        "state": STATE_ACTIVE,
        "company_guid": func.coalesce(stmt.excluded.company_guid, TallyVoucherIndex.company_guid),
        "updated_at": func.now(),
    })
    await session.execute(stmt)


async def _sync_one_voucher(session, v: VoucherItem, resolver: CustomerResolver, uid, now, st: _Stats,
                            company_guid: Optional[str] = None) -> None:
    stored = await _stored_alter_id(session, v.guid)
    if v.alter_id is not None and stored is not None and v.alter_id < stored:
        st.excluded["STALE_VERSION"] = st.excluded.get("STALE_VERSION", 0) + 1
        return  # an older copy (e.g. a retried batch) never overwrites a newer one
    reason = exclusion_reason(v)
    if reason:
        st.excluded[reason] = st.excluded.get(reason, 0) + 1
        st.retired += await retire_voucher_rows(session, v.guid, {}, reason, now)
        await _stamp_alter_id(session, v.guid, v.alter_id)
        await _index_voucher(session, v, company_guid)
        return
    plans = plan_voucher(v)
    keep: dict[str, set[str]] = {KIND_INVOICE: set(), KIND_PAYMENT: set(), KIND_ADJUSTMENT: set()}
    for p in plans:
        cust, led = await resolver.resolve(p.ledger_guid, p.ledger_name)
        if cust is None:
            raise LookupError(f"ledger '{p.ledger_name}' is not a known customer (sync ledgers first)")
        lid = led.id if led is not None else None
        if p.brand is None and led is not None and led.effective_brand:
            p.brand = led.effective_brand  # the ledger's (Tally or client-confirmed) brand
        if p.kind == KIND_INVOICE:
            created = await _upsert_invoice(session, v, p, cust, uid, now, lid)
        elif p.kind == KIND_PAYMENT:
            created = await _upsert_payment(session, v, p, cust, uid, now, st, lid)
        else:
            created = await _upsert_adjustment(session, v, p, cust, lid)
        keep[p.kind].add(p.key)
        st.by_kind[p.kind] += 1
        if created:
            st.created += 1
        else:
            st.updated += 1
    st.retired += await retire_voucher_rows(
        session, v.guid, keep, R_LINE_REMOVED if not plans else R_RECLASSIFIED, now
    )
    await _stamp_alter_id(session, v.guid, v.alter_id)
    await _index_voucher(session, v, company_guid)


async def sync_vouchers(agent: SyncAgent, batch: VoucherSyncBatch, session: AsyncSession) -> V2SyncResult:
    started = time.time()
    uid = await system_user_id(session)
    resolver = CustomerResolver(session)
    st = _Stats()
    now = _now()
    for v in batch.vouchers:
        try:
            async with session.begin_nested():
                await _sync_one_voucher(session, v, resolver, uid, now, st, batch.company_guid)
        except Exception as ex:  # one bad voucher fails alone
            resolver.cache.clear()
            st.failed += 1
            st.errors.append({"identifier": v.guid, "error": str(ex)[:500]})
    agent.last_sync_at = now
    await session.commit()
    details = {
        "by_kind": st.by_kind, "excluded": st.excluded,
        "unresolved_bill_count": st.unresolved_bills, "unresolved_bill_amount": str(st.unresolved_bill_amount),
    }
    await _audit(session, agent, "SYNC_VOUCHERS", "VOUCHERS", len(batch.vouchers), st, started, batch.batch_id, details)
    try:
        from app.services.period_service import ensure_monthly_periods_synced
        await ensure_monthly_periods_synced(session)
    except Exception:
        pass
    return V2SyncResult(batch_id=batch.batch_id, total_received=len(batch.vouchers), created_count=st.created,
                        updated_count=st.updated, retired_count=st.retired, failed_count=st.failed,
                        details=details, errors=st.errors)


async def _audit(session, agent, op, entity, count, st: _Stats, started, batch_id, details) -> None:
    status = "SUCCESS" if st.failed == 0 else ("PARTIAL" if (st.created or st.updated) else "FAILED")
    await tally_audit_service.record_read_audit(
        session=session, agent=agent, operation=op, entity_type=entity, record_count=count, status=status,
        duration_ms=int((time.time() - started) * 1000),
        error_message="; ".join(e["error"] for e in st.errors[:3]) or None,
        details={"batch_id": batch_id, "created_count": st.created, "updated_count": st.updated,
                 "retired_count": st.retired, "failed_count": st.failed, **details},
    )


# ---------------------------------------------------------------------------
# Snapshot runs (shared by ledgers / bills / manifest)
# ---------------------------------------------------------------------------

async def _run(session, agent, snapshot_id: str, kind: str, **fields) -> TallySnapshotRun:
    run = await session.get(TallySnapshotRun, snapshot_id)
    if run is None:
        run = TallySnapshotRun(id=snapshot_id, agent_id=agent.id, kind=kind, status="RECEIVING",
                               received_count=0, **fields)
        session.add(run)
        await session.flush()
    elif run.kind != kind:
        raise ValueError(f"snapshot {snapshot_id} is a {run.kind} snapshot, not {kind}")
    elif run.status != "RECEIVING":
        raise ValueError(f"snapshot {snapshot_id} is already {run.status}")
    return run


async def latest_complete_run(session: AsyncSession, kind: str) -> Optional[TallySnapshotRun]:
    return (await session.execute(
        select(TallySnapshotRun).where(TallySnapshotRun.kind == kind, TallySnapshotRun.status == "COMPLETE")
        .order_by(TallySnapshotRun.as_of_date.desc().nullslast(), TallySnapshotRun.completed_at.desc())
        .limit(1)
    )).scalar_one_or_none()


# ---------------------------------------------------------------------------
# Ledgers
# ---------------------------------------------------------------------------

def _ledger_facts(led: TallyDebtorLedger, item: LedgerItem, batch: LedgerSyncBatch, brand: Optional[str]) -> None:
    """Tally facts of ONE ledger, exactly as exported (never touched by mapping)."""
    led.name = item.name.strip()[:150]
    led.parent_group = _clip(item.parent, 150)
    led.aliases = [a for a in item.aliases if a.strip()] or None
    code = (item.outlet_code or "").strip() or None
    if code:
        led.tally_outlet_code = code[:50]
    if brand:
        led.brand_tally = brand
    led.is_debtor = bool(item.is_debtor)
    if item.is_debtor:
        led.is_bill_wise = item.is_bill_wise
        led.credit_period = _clip(item.credit_period, 50)
        for attr, value, size in (("gst_number", item.gst_number, 20), ("mobile", item.mobile or item.contact_number, 50),
                                  ("address", item.address, None), ("pincode", item.pincode, 20),
                                  ("state", item.state, 100)):
            value = (value or "").strip()
            if value:
                setattr(led, attr, value[:size] if size else value)
        if batch.snapshot_id:  # balances are only taken from a full snapshot (consistent as-of)
            led.opening_balance = item.opening_balance if item.opening_balance is not None else ZERO
            led.opening_balance_as_of = batch.period_start
            led.closing_balance = item.closing_balance if item.closing_balance is not None else ZERO
            led.closing_balance_at = batch.as_of or _now()


async def _refresh_outlet_debtor_flag(session, cust: Customer) -> None:
    """An outlet is hidden as "not a debtor" only when ALL its ledgers are non-debtors."""
    flags = (await session.execute(
        select(TallyDebtorLedger.is_debtor).where(TallyDebtorLedger.customer_id == cust.id)
    )).scalars().all()
    if flags:
        if any(f for f in flags):
            cust.tally_is_debtor = True
        elif all(f is False for f in flags):
            cust.tally_is_debtor = False


async def _upsert_debtor(session, item: LedgerItem, batch: LedgerSyncBatch, uid, st: _Stats, conflicts: list):
    from app.services.tally_sync_service import ensure_area, ensure_territory

    name = item.name.strip()
    code = (item.outlet_code or "").strip() or None
    brand, brand_id = (await _brand(session, item.brand)) if item.brand else (None, None)

    led = (await session.execute(
        select(TallyDebtorLedger).where(TallyDebtorLedger.tally_guid == item.guid)
    )).scalar_one_or_none()
    if led is None:
        cust = (await session.execute(select(Customer).where(Customer.tally_guid == item.guid))).scalar_one_or_none()
        if cust is None and code:
            cust = (await session.execute(
                select(Customer).where(Customer.outlet_code == code, Customer.tally_guid.is_(None))
            )).scalar_one_or_none()
        if cust is None:
            rows = (await session.execute(
                select(Customer).where(func.lower(Customer.name) == name.lower(), Customer.tally_guid.is_(None),
                                       Customer.merged_into_customer_id.is_(None))
            )).scalars().all()
            cust = rows[0] if len(rows) == 1 else None
        status = MAPPING_AUTO
        if cust is None:  # a ledger FieldTrack has never seen: its own outlet, flagged for review
            cust = Customer(name=name, tally_guid=item.guid, address="", contact_number="",
                            location_status="MISSING", created_by=uid)
            session.add(cust)
            st.created += 1
            status = MAPPING_NEW
        else:
            st.updated += 1
        cust.tally_guid = cust.tally_guid or item.guid
        await session.flush()
        has_primary = (await session.execute(select(TallyDebtorLedger.id).where(
            TallyDebtorLedger.customer_id == cust.id, TallyDebtorLedger.is_primary))).first() is not None
        led = TallyDebtorLedger(customer_id=cust.id, tally_guid=item.guid, name=name[:150],
                                is_primary=not has_primary, mapping_status=status)
        session.add(led)
    else:
        cust = await outlet_of(session, await session.get(Customer, led.customer_id))
        st.updated += 1
    _ledger_facts(led, item, batch, brand)
    await session.flush()

    if led.is_primary and cust.id == led.customer_id:
        # The outlet's master data follows its primary ledger (customers.tally_* = primary ledger).
        if cust.outlet_name_source != "ADMIN":
            cust.name = name
        details = {
            "address": (item.address, None), "contact_number": (item.contact_number or item.mobile, 20),
            "contact_person": (item.contact_person, 150), "gst_number": (item.gst_number, 20),
            "email": (item.email, 255), "mobile_number": (item.mobile, 50),
        }
        for attr, (value, size) in details.items():
            value = (value or "").strip()
            if value:
                setattr(cust, attr, value[:size] if size else value)
        if code:
            if not cust.outlet_code:
                taken = (await session.execute(
                    select(Customer.id).where(Customer.outlet_code == code, Customer.id != cust.id)
                )).first()
                if taken:
                    conflicts.append({"ledger": name, "outlet_code": code, "issue": "code already used by another outlet"})
                else:
                    cust.outlet_code = code
            elif cust.outlet_code != code:
                conflicts.append({"ledger": name, "outlet_code": code, "stored": cust.outlet_code,
                                  "issue": "stored code differs from Tally alias (kept)"})
        cust.tally_parent_group = led.parent_group
        cust.tally_aliases = led.aliases
        cust.tally_is_bill_wise = led.is_bill_wise
        cust.tally_credit_period = led.credit_period
        if batch.snapshot_id:
            cust.tally_opening_balance = led.opening_balance
            cust.tally_opening_balance_as_of = led.opening_balance_as_of
            cust.tally_closing_balance = led.closing_balance
            cust.tally_closing_balance_at = led.closing_balance_at
        if item.zone and item.zone.strip():
            terr = await ensure_territory(session, item.zone)
            cust.territory_id = terr.id
            if item.area and item.area.strip():
                cust.area_id = (await ensure_area(session, item.area, terr.id)).id
    cust.tally_is_debtor = True
    cust.needs_tally_entry = False
    await session.flush()
    if brand and not (await session.execute(select(CustomerBrand.id).where(
            CustomerBrand.customer_id == cust.id, CustomerBrand.brand == brand))).first():
        session.add(CustomerBrand(customer_id=cust.id, brand=brand, brand_id=brand_id, is_active=True))
        await session.flush()


async def _mark_non_debtor(session, item: LedgerItem, st: _Stats) -> bool:
    led = (await session.execute(
        select(TallyDebtorLedger).where(TallyDebtorLedger.tally_guid == item.guid)
    )).scalar_one_or_none()
    if led is None:
        cust = (await session.execute(select(Customer).where(Customer.tally_guid == item.guid))).scalar_one_or_none()
        if cust is None:
            rows = (await session.execute(
                select(Customer).where(func.lower(Customer.name) == item.name.strip().lower(),
                                       Customer.tally_guid.is_(None), Customer.merged_into_customer_id.is_(None))
            )).scalars().all()
            cust = rows[0] if len(rows) == 1 else None
            if cust is not None:
                cust.tally_guid = item.guid
        if cust is None:
            return False  # a non-debtor ledger never becomes a customer
        led = await ensure_ledger_for_customer(session, cust)
    was_debtor = led.is_debtor is not False
    led.is_debtor = False
    led.parent_group = _clip(item.parent, 150)
    led.aliases = [a for a in item.aliases if a.strip()] or None
    cust = await session.get(Customer, led.customer_id)
    if led.is_primary:
        cust.tally_parent_group = led.parent_group
        cust.tally_aliases = led.aliases
    await session.flush()
    before = cust.tally_is_debtor
    await _refresh_outlet_debtor_flag(session, cust)
    if cust.tally_is_debtor is None:  # the only ledger is now known to be a non-debtor
        cust.tally_is_debtor = False
    st.updated += 1
    return was_debtor and before is not False and cust.tally_is_debtor is False


async def sync_ledgers(agent: SyncAgent, batch: LedgerSyncBatch, session: AsyncSession) -> V2SyncResult:
    started = time.time()
    uid = await system_user_id(session)
    st = _Stats()
    conflicts: list[dict] = []
    newly_non_debtor: list[str] = []
    run = None
    if batch.snapshot_id:
        run = await _run(session, agent, batch.snapshot_id, "LEDGERS",
                         as_of_date=(batch.as_of or _now()).date())
    for item in batch.ledgers:
        try:
            async with session.begin_nested():
                if item.is_debtor:
                    await _upsert_debtor(session, item, batch, uid, st, conflicts)
                elif await _mark_non_debtor(session, item, st):
                    newly_non_debtor.append(item.name)
                if run is not None:
                    await session.merge(TallyManifestGuid(snapshot_id=run.id, guid=item.guid))
        except Exception as ex:
            st.failed += 1
            st.errors.append({"identifier": item.guid, "error": str(ex)[:500]})
    details: dict = {"outlet_code_conflicts": conflicts[:200], "newly_non_debtor": newly_non_debtor[:500]}
    if run is not None:
        run.received_count += len(batch.ledgers)
        if batch.is_final_chunk:
            details["missing_from_tally"] = await _finish_ledger_snapshot(session, run, st)
    agent.last_sync_at = _now()
    await session.commit()
    await _audit(session, agent, "SYNC_LEDGERS", "CUSTOMERS", len(batch.ledgers), st, started, batch.batch_id,
                 {"conflict_count": len(conflicts), "newly_non_debtor_count": len(newly_non_debtor)})
    return V2SyncResult(batch_id=batch.batch_id, total_received=len(batch.ledgers), created_count=st.created,
                        updated_count=st.updated, failed_count=st.failed, details=details, errors=st.errors)


async def _finish_ledger_snapshot(session, run: TallySnapshotRun, st: _Stats) -> list[str]:
    """A ledger whose GUID is absent from a complete snapshot no longer exists in Tally: it stops
    being treated as a debtor (never deleted); its outlet too once none of its ledgers is a debtor."""
    seen = select(TallyManifestGuid.guid).where(TallyManifestGuid.snapshot_id == run.id)
    known = (await session.execute(select(func.count()).select_from(
        select(TallyDebtorLedger.tally_guid).union(
            select(Customer.tally_guid).where(Customer.tally_guid.is_not(None))).subquery()))).scalar() or 0
    seen_n = (await session.execute(select(func.count()).select_from(seen.subquery()))).scalar() or 0
    missing: list[str] = []
    if known and Decimal(seen_n) < SNAPSHOT_COMPLETENESS_FLOOR * known:
        run.status = "FAILED"
        run.details = {"error": f"snapshot has {seen_n} ledgers, FieldTrack knows {known}: not applied"}
    else:
        # Legacy customers holding a GUID without a ledger row get one first (1:1).
        for c in (await session.execute(select(Customer).where(
            Customer.tally_guid.is_not(None),
            ~select(TallyDebtorLedger.id).where(TallyDebtorLedger.tally_guid == Customer.tally_guid).exists(),
        ))).scalars().all():
            await ensure_ledger_for_customer(session, c)
        gone = (await session.execute(
            select(TallyDebtorLedger).where(TallyDebtorLedger.tally_guid.not_in(seen),
                                            or_(TallyDebtorLedger.is_debtor.is_(None), TallyDebtorLedger.is_debtor.is_(True)))
        )).scalars().all()
        outlets = set()
        for led in gone:
            led.is_debtor = False
            missing.append(led.name)
            outlets.add(led.customer_id)
        await session.flush()
        for cid in outlets:
            c = await session.get(Customer, cid)
            if c is not None:
                await _refresh_outlet_debtor_flag(session, c)
        run.status = "COMPLETE"
        run.details = {"ledgers": seen_n, "missing_from_tally": len(missing)}
    run.completed_at = _now()
    await session.execute(delete(TallyManifestGuid).where(TallyManifestGuid.snapshot_id == run.id))
    return missing[:500]


# ---------------------------------------------------------------------------
# Bills Receivable
# ---------------------------------------------------------------------------

async def sync_bills(agent: SyncAgent, batch: BillsSyncBatch, session: AsyncSession) -> V2SyncResult:
    started = time.time()
    st = _Stats()
    run = await _run(session, agent, batch.snapshot_id, "BILLS", as_of_date=batch.as_of_date)
    resolver = CustomerResolver(session)
    skipped_non_debtor = 0
    unknown: list[str] = []
    for b in batch.bills:
        cust, led = await resolver.resolve(b.ledger_guid, b.ledger_name)
        if cust is None:
            unknown.append(b.ledger_name)
            continue
        if (led.is_debtor if led is not None else cust.tally_is_debtor) is False:
            skipped_non_debtor += 1
            continue
        session.add(TallyOpenBill(
            customer_id=cust.id, tally_debtor_ledger_id=led.id if led is not None else None,
            as_of_date=batch.as_of_date, snapshot_id=run.id, bill_name=b.bill_name[:150],
            bill_date=b.bill_date, due_date=b.due_date, pending_amount=_q(-Decimal(b.pending_amount)),
            overdue_days=b.overdue_days,
        ))
        st.created += 1
    run.received_count += st.created
    details = {"skipped_non_debtor": skipped_non_debtor, "unknown_ledgers": sorted(set(unknown))[:200]}
    if batch.is_final_chunk:
        details.update(await _finish_bills_snapshot(session, run))
    agent.last_sync_at = _now()
    await session.commit()
    await _audit(session, agent, "SYNC_BILLS", "BILLS", len(batch.bills), st, started, batch.batch_id,
                 {"skipped_non_debtor": skipped_non_debtor, "unknown_ledger_count": len(set(unknown))})
    return V2SyncResult(batch_id=batch.batch_id, total_received=len(batch.bills), created_count=st.created,
                        details=details)


async def _finish_bills_snapshot(session, run: TallySnapshotRun) -> dict:
    await session.flush()
    # The newest snapshot for its date replaces earlier ones for the same date.
    await session.execute(delete(TallyOpenBill).where(
        TallyOpenBill.as_of_date == run.as_of_date, TallyOpenBill.snapshot_id != run.id))
    # Older daily copies are pruned; month-end and 31 March snapshots are kept as history.
    month_end = func.extract("day", TallyOpenBill.as_of_date + text("INTERVAL '1 day'")) == 1
    await session.execute(delete(TallyOpenBill).where(TallyOpenBill.as_of_date < run.as_of_date, ~month_end))
    run.status = "COMPLETE"
    run.completed_at = _now()
    latest = await latest_complete_run(session, "BILLS")
    due_updates = 0
    if latest is None or latest.as_of_date is None or run.as_of_date >= latest.as_of_date:
        # Tally's due date for every still-open bill becomes the invoice's due date.
        res = await session.execute(text("""
            UPDATE invoices i SET due_date = b.due_date
            FROM tally_open_bills b
            WHERE b.snapshot_id = :sid AND b.due_date IS NOT NULL
              AND i.customer_id = b.customer_id AND i.tally_bill_name = b.bill_name
              AND (b.tally_debtor_ledger_id IS NULL OR i.tally_debtor_ledger_id IS NULL
                   OR i.tally_debtor_ledger_id = b.tally_debtor_ledger_id)
              AND i.source = 'TALLY' AND i.due_date IS DISTINCT FROM b.due_date
              -- 2.2.0 (B6): a bill name used by two invoices of the customer (numbers restart each FY)
              -- is matched on its date too
              AND (b.bill_date IS NULL OR i.invoice_date = b.bill_date
                   OR (SELECT count(*) FROM invoices i2 WHERE i2.customer_id = i.customer_id
                         AND i2.tally_bill_name = i.tally_bill_name AND i2.source = 'TALLY') = 1)
        """), {"sid": run.id})
        due_updates = res.rowcount or 0
    run.details = {"bills": run.received_count, "invoice_due_dates_set": due_updates}
    return {"invoice_due_dates_set": due_updates, "snapshot_status": run.status}


# ---------------------------------------------------------------------------
# Voucher GUID manifest (deletions)
# ---------------------------------------------------------------------------

_GUID_EXPR = "COALESCE({t}.tally_voucher_guid, split_part({t}.source_reference, '::', 1))"


async def sync_manifest(agent: SyncAgent, batch: ManifestSyncBatch, session: AsyncSession) -> V2SyncResult:
    started = time.time()
    st = _Stats()
    run = await _run(session, agent, batch.snapshot_id, "VOUCHER_MANIFEST",
                     window_from=batch.window_from, window_to=batch.window_to)
    for g in {g.strip() for g in batch.guids if g and g.strip()}:
        await session.merge(TallyManifestGuid(snapshot_id=run.id, guid=g))
    run.received_count += len(batch.guids)
    details: dict = {}
    if batch.is_final_chunk:
        details = await _finish_manifest(session, run, st)
    await session.commit()
    await _audit(session, agent, "SYNC_MANIFEST", "VOUCHERS", len(batch.guids), st, started, batch.batch_id, details)
    return V2SyncResult(batch_id=batch.batch_id, total_received=len(batch.guids), retired_count=st.retired,
                        details=details)


async def _finish_manifest(session, run: TallySnapshotRun, st: _Stats) -> dict:
    await session.flush()
    params = {"sid": run.id, "f": run.window_from, "t": run.window_to}
    held = (await session.execute(text(f"""
        SELECT count(DISTINCT g) FROM (
          SELECT {_GUID_EXPR.format(t='i')} g FROM invoices i
           WHERE i.source = 'TALLY' AND i.invoice_date BETWEEN :f AND :t
          UNION ALL
          SELECT {_GUID_EXPR.format(t='p')} FROM payments p
           WHERE p.source = 'TALLY' AND p.payment_date BETWEEN :f AND :t
          UNION ALL
          SELECT a.tally_voucher_guid FROM tally_ledger_adjustments a
           WHERE a.state = 'ACTIVE' AND a.voucher_date BETWEEN :f AND :t) x
    """), params)).scalar() or 0
    staged = (await session.execute(
        select(func.count()).select_from(TallyManifestGuid).where(TallyManifestGuid.snapshot_id == run.id)
    )).scalar() or 0
    if held and Decimal(staged) < SNAPSHOT_COMPLETENESS_FLOOR * held:
        run.status = "FAILED"
        run.details = {"error": f"manifest lists {staged} vouchers, FieldTrack holds {held}: not applied"}
        run.completed_at = _now()
        await session.execute(delete(TallyManifestGuid).where(TallyManifestGuid.snapshot_id == run.id))
        return run.details
    now = _now()
    absent = "NOT EXISTS (SELECT 1 FROM tally_manifest_guids m WHERE m.snapshot_id = :sid AND m.guid = {g})"
    counts = {}
    for name, sql in (
        ("invoices", f"""UPDATE invoices i SET source = 'TALLY_RETIRED', tally_retired_at = :now,
                         tally_retired_reason = '{R_DELETED}'
                         WHERE i.source = 'TALLY' AND i.invoice_date BETWEEN :f AND :t
                           AND i.source_reference IS NOT NULL
                           AND {absent.format(g=_GUID_EXPR.format(t='i'))}
                         RETURNING i.id"""),
        ("payments", f"""UPDATE payments p SET source = 'TALLY_RETIRED', tally_retired_at = :now,
                         tally_retired_reason = '{R_DELETED}'
                         WHERE p.source = 'TALLY' AND p.payment_date BETWEEN :f AND :t
                           AND p.source_reference IS NOT NULL
                           AND {absent.format(g=_GUID_EXPR.format(t='p'))}"""),
        ("adjustments", f"""UPDATE tally_ledger_adjustments a SET state = 'RETIRED', retired_at = :now,
                            retired_reason = '{R_DELETED}'
                            WHERE a.state = 'ACTIVE' AND a.voucher_date BETWEEN :f AND :t
                              AND {absent.format(g='a.tally_voucher_guid')}"""),
    ):
        res = await session.execute(text(sql), {**params, "now": now})
        if name == "invoices":
            retired_invoice_ids = [r[0] for r in res.fetchall()]
            counts[name] = len(retired_invoice_ids)
        else:
            counts[name] = res.rowcount or 0
    st.retired = sum(counts.values())
    await relink_receipts_of_invoices(session, retired_invoice_ids)
    # Release 3.0: the voucher index follows the same accepted manifest.
    index_deleted = (await session.execute(text(
        f"""UPDATE tally_voucher_index x SET state = '{STATE_DELETED}', updated_at = :now
            WHERE x.state = '{STATE_ACTIVE}' AND x.voucher_date BETWEEN :f AND :t AND {absent.format(g='x.guid')}"""),
        {**params, "now": now})).rowcount or 0
    run.status = "COMPLETE"
    run.completed_at = now
    run.details = {"vouchers_listed": staged, "held_in_window": held, "retired": counts, "index_deleted": index_deleted}
    await session.execute(delete(TallyManifestGuid).where(TallyManifestGuid.snapshot_id == run.id))
    return run.details


# ---------------------------------------------------------------------------
# Reconciliation (release 3.0)
# ---------------------------------------------------------------------------

class ReconcileCompanyMismatch(Exception):
    pass


async def reconcile(agent: SyncAgent, batch, session: AsyncSession) -> dict:
    """Compare EVERY voucher header Tally holds in a date window with what FieldTrack has processed. Read-only:
    nothing is written here. The agent re-sends the missing / stale vouchers (idempotent upserts) and retires the
    extra ones through an accepted manifest (with its completeness floor).

      missing  listed by Tally, never processed by FieldTrack (or marked DELETED: re-created / restored in Tally)
      stale    listed with a higher AlterID than the version FieldTrack processed
      extra    processed by FieldTrack, dated in the window, ACTIVE, but no longer listed by Tally
    """
    if agent.tally_company_guid and batch.company_guid and agent.tally_company_guid != batch.company_guid:
        raise ReconcileCompanyMismatch(
            f"reconcile for company {batch.company_guid} refused: this agent is bound to {agent.tally_company_guid}")
    listed = {}
    for e in batch.entries:
        listed[e.guid] = max(int(e.alter_id or 0), listed.get(e.guid, 0))
    held: dict = {}
    keys = list(listed)
    for i in range(0, len(keys), 5000):
        for g, a, state in (await session.execute(
                select(TallyVoucherIndex.guid, TallyVoucherIndex.alter_id, TallyVoucherIndex.state)
                .where(TallyVoucherIndex.guid.in_(keys[i:i + 5000])))).all():
            held[g] = (int(a or 0), state)
    missing = sorted(g for g in listed if g not in held or held[g][1] != STATE_ACTIVE)
    stale = sorted(g for g, a in listed.items() if g in held and held[g][1] == STATE_ACTIVE and held[g][0] < a)
    in_window = [g for (g,) in (await session.execute(
        select(TallyVoucherIndex.guid).where(TallyVoucherIndex.state == STATE_ACTIVE,
                                             TallyVoucherIndex.voucher_date >= batch.window_from,
                                             TallyVoucherIndex.voucher_date <= batch.window_to))).all()]
    extra = sorted(g for g in in_window if g not in listed)
    return {"batch_id": batch.batch_id, "window_from": batch.window_from, "window_to": batch.window_to,
            "listed": len(listed), "held_in_window": len(in_window), "missing": missing, "stale": stale, "extra": extra}
