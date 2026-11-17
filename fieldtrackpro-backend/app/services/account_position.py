"""
Account position: the ONE shared calculation behind every outlet / brand money
figure (outlet Account summary AND Collections overview rows + totals).

Owner rule: Tally is the final truth. Outstanding only drops for payments that
are POSTED to Tally (see payment_tally.py); verified-but-not-yet-in-Tally money
is reported separately and never touches any figure below except `awaiting`.

Per brand (and, summed, per outlet) the position is:

    opening_balance + invoiced - paid_in_tally == outstanding        (exactly)

where
  baseline_invoiced   OutletFinancialSnapshot.sales (Tally baseline; summed over snapshots)
  invoiced            baseline_invoiced + sum(live TALLY Invoice.amount)
  baseline_collected  OutletFinancialSnapshot.collection (Tally baseline)
  paid_in_tally       baseline_collected + POSTED payments (receipt in Tally)
  outstanding         max(LATEST snapshot.market_outstanding per brand + live invoice remaining
                          - POSTED on-account (unapplied) credit, 0) - field
                          collections and Tally receipts without bill-wise allocation
  opening_balance     DERIVED = outstanding - invoiced + paid_in_tally, i.e. the
                      Tally baseline carried forward into the period. It also
                      absorbs `advance_credit` (over-payment that cannot push
                      outstanding below zero): carried-forward balance excluding
                      advance = opening_balance - advance_credit.
  awaiting            verified MANUAL payments not yet confirmed in Tally;
                      NOT in paid_in_tally, NOT in outstanding. A collection
                      linked to an imported Tally receipt is in neither: the
                      receipt itself is the posted money (payment_tally.py).

Ageing buckets (always sum to `outstanding`):
  normal / warning / overdue   live invoice remaining by
                               aging_service.classify_age_days
                               (<21 / 21-25 / >=26 days since invoice date)
  baseline_current             Tally baseline balance whose snapshot age is
                               under 30 days (or unaged residual); the
                               snapshot bands (<15, 15-30, 30-45 ...) cannot be
                               mapped onto 21/26, so it is labelled separately
  baseline_overdue             Tally baseline balance aged 30+ days (snapshot
                               columns 30-45 ... >90): certainly >= 26 days
  On-account credit is netted oldest first:
  baseline_overdue, overdue, baseline_current, warning, normal.
  overdue_amount = overdue + baseline_overdue.

Tally-balance mode (agent 2.0; used for an outlet that is a Tally debtor with a
ledger balance, once a complete Bills Receivable snapshot exists - otherwise the
baseline model above applies unchanged):
  outstanding        Tally's own open bills (latest Bills Receivable snapshot) per
                     brand, plus - on the Unbranded row - the ledger's unallocated
                     remainder (Tally closing balance - sum of its open bills)
  ageing             each open bill by its bill date (same 21/26-day rule); the
                     unallocated remainder is unaged (baseline_current); open credit
                     bills and credit remainder are netted oldest first as above
  invoiced / paid    TALLY invoices / POSTED payments dated on or after the ledger's
                     opening-balance date (Tally's current period start)
  adjustments        credit / debit notes, journals ... (TallyLedgerAdjustment)
  opening_balance    derived per brand: outstanding - invoiced - adjustments + paid
  outlet check       tally_difference = Tally opening + invoiced + adjustments - paid
                     - Tally closing; `reconciles` is False unless it is 0.00.

Both the single-outlet path (account_service) and the bulk path
(collections_service) call `load_outlet_positions`, which batches the queries
and then calls the same pure `compute_brand_position` / `sum_positions`.
"""
from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass, field, replace
from datetime import date, datetime
from decimal import Decimal
from typing import Iterable

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.datetime_utils import get_ist_now
from app.models.customer import Customer
from app.models.customer_brand import CustomerBrand
from app.models.invoice import Invoice, InvoiceSource
from app.models.outlet_financial_snapshot import OutletFinancialSnapshot
from app.models.payment import Payment, PaymentBrandAllocation, PaymentStatus
from app.models.payment_invoice_allocation import PaymentInvoiceAllocation
from app.models.tally_ledger import ADJUSTMENT_ACTIVE, TallyLedgerAdjustment, TallyOpenBill, TallySnapshotRun
from app.services import brand_service, payment_tally
from app.services.aging_service import AgingStatus, classify_age_days, compute_invoice_aging

ZERO = Decimal("0.00")
_CENT = Decimal("0.01")

# Oldest-first order in which on-account credit is netted off the buckets.
_NETTING_ORDER = ("baseline_overdue", "overdue", "baseline_current", "warning", "normal")


# ---------------------------------------------------------------------------
# Pure maths
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Ageing:
    normal: Decimal = ZERO
    warning: Decimal = ZERO
    overdue: Decimal = ZERO
    baseline_current: Decimal = ZERO
    baseline_overdue: Decimal = ZERO

    @property
    def total(self) -> Decimal:
        return self.normal + self.warning + self.overdue + self.baseline_current + self.baseline_overdue

    def __add__(self, other: "Ageing") -> "Ageing":
        return Ageing(
            self.normal + other.normal,
            self.warning + other.warning,
            self.overdue + other.overdue,
            self.baseline_current + other.baseline_current,
            self.baseline_overdue + other.baseline_overdue,
        )


@dataclass(frozen=True)
class InvoiceLine:
    amount: Decimal
    remaining: Decimal
    days_outstanding: int
    aging_status: AgingStatus


@dataclass
class BrandInputs:
    """Raw facts for one brand of one outlet (no derived maths)."""

    snapshot_sales: Decimal = ZERO
    snapshot_collection: Decimal = ZERO
    snapshot_outstanding: Decimal = ZERO
    # Sum of the snapshot ageing columns aged 30+ days (30-45 ... >90).
    snapshot_aged_30_plus: Decimal = ZERO
    invoices: list[InvoiceLine] = field(default_factory=list)
    posted_payments: Decimal = ZERO       # POSTED payment shares for this brand
    awaiting: Decimal = ZERO              # verified, not yet in Tally
    on_account_credit: Decimal = ZERO     # unapplied part of POSTED payments (field or Tally)


@dataclass(frozen=True)
class Position:
    opening_balance: Decimal = ZERO
    baseline_invoiced: Decimal = ZERO
    invoiced: Decimal = ZERO
    baseline_collected: Decimal = ZERO
    paid_in_tally: Decimal = ZERO
    verified_awaiting_tally: Decimal = ZERO
    outstanding: Decimal = ZERO
    overdue: Decimal = ZERO
    advance_credit: Decimal = ZERO
    ageing: Ageing = field(default_factory=Ageing)
    max_days_outstanding: int = 0
    collection_status: AgingStatus = AgingStatus.PAID
    reconciles: bool = True
    adjustments: Decimal = ZERO
    balance_source: str = "BASELINE"          # BASELINE | TALLY
    balance_as_of: datetime | None = None
    tally_opening_balance: Decimal | None = None   # receivable sign (+ = owed)
    tally_closing_balance: Decimal | None = None
    tally_difference: Decimal | None = None


def _q(v: Decimal) -> Decimal:
    return v.quantize(_CENT)


def derive_status(outstanding: Decimal, overdue: Decimal, ageing: Ageing) -> AgingStatus:
    """The single collection-status rule (worst wins): OVERDUE > WARNING > NORMAL > PAID."""
    if overdue > 0:
        return AgingStatus.OVERDUE
    if ageing.warning > 0:
        return AgingStatus.WARNING
    if outstanding > 0:
        return AgingStatus.NORMAL
    return AgingStatus.PAID


def check_reconciles(p: Position) -> bool:
    """Derived self-check: the arithmetic adds up and every figure is sane."""
    return (
        p.opening_balance + p.invoiced + p.adjustments - p.paid_in_tally == p.outstanding
        and p.ageing.total == p.outstanding
        and p.outstanding >= 0
        and 0 <= p.overdue <= p.outstanding
    )


def compute_brand_position(i: BrandInputs) -> Position:
    inv_normal = inv_warning = inv_overdue = ZERO
    max_days = 0
    inv_remaining = ZERO
    for line in i.invoices:
        if line.remaining <= 0:
            continue
        inv_remaining += line.remaining
        max_days = max(max_days, line.days_outstanding)
        if line.aging_status == AgingStatus.OVERDUE:
            inv_overdue += line.remaining
        elif line.aging_status == AgingStatus.WARNING:
            inv_warning += line.remaining
        else:
            inv_normal += line.remaining

    base_overdue = max(min(i.snapshot_aged_30_plus, i.snapshot_outstanding), ZERO)
    base_current = i.snapshot_outstanding - base_overdue
    buckets = {
        "baseline_overdue": base_overdue,
        "overdue": inv_overdue,
        "baseline_current": base_current,
        "warning": inv_warning,
        "normal": inv_normal,
    }

    raw = i.snapshot_outstanding + inv_remaining - i.on_account_credit
    outstanding = max(raw, ZERO)
    advance_credit = max(-raw, ZERO)

    # Net credit / zero-clamp off the buckets, oldest first.
    reduce = (i.snapshot_outstanding + inv_remaining) - outstanding
    for name in _NETTING_ORDER:
        if reduce <= 0:
            break
        take = min(max(buckets[name], ZERO), reduce)
        buckets[name] -= take
        reduce -= take
    # Guard: any rounding / negative-baseline residue lands in the unaged bucket.
    residue = outstanding - sum(buckets.values(), ZERO)
    buckets["baseline_current"] += residue

    ageing = Ageing(**buckets)
    overdue = min(ageing.overdue + ageing.baseline_overdue, outstanding)

    invoiced = i.snapshot_sales + sum((l.amount for l in i.invoices), ZERO)
    paid = i.snapshot_collection + i.posted_payments
    pos = Position(
        opening_balance=outstanding - invoiced + paid,
        baseline_invoiced=i.snapshot_sales,
        invoiced=invoiced,
        baseline_collected=i.snapshot_collection,
        paid_in_tally=paid,
        verified_awaiting_tally=i.awaiting,
        outstanding=outstanding,
        overdue=overdue,
        advance_credit=advance_credit,
        ageing=ageing,
        max_days_outstanding=max_days,
        collection_status=derive_status(outstanding, overdue, ageing),
    )
    return replace(pos, reconciles=check_reconciles(pos))


@dataclass
class TallyBrandInputs:
    """Raw facts for one brand of one outlet in Tally-balance mode."""

    bills: list[InvoiceLine] = field(default_factory=list)  # remaining = Tally pending (signed)
    residue: Decimal = ZERO          # unallocated ledger remainder (Unbranded row only)
    invoiced: Decimal = ZERO
    adjustments: Decimal = ZERO
    posted_payments: Decimal = ZERO
    awaiting: Decimal = ZERO


def compute_tally_brand_position(t: TallyBrandInputs) -> Position:
    buckets = {name: ZERO for name in _NETTING_ORDER}
    credits = ZERO
    max_days = 0
    for line in t.bills:
        if line.remaining < 0:
            credits += -line.remaining
            continue
        if line.remaining == 0:
            continue
        max_days = max(max_days, line.days_outstanding)
        if line.days_outstanding < 0:
            buckets["baseline_current"] += line.remaining  # undated bill: unaged
        elif line.aging_status == AgingStatus.OVERDUE:
            buckets["overdue"] += line.remaining
        elif line.aging_status == AgingStatus.WARNING:
            buckets["warning"] += line.remaining
        else:
            buckets["normal"] += line.remaining
    if t.residue > 0:
        buckets["baseline_current"] += t.residue
    else:
        credits += -t.residue
    gross = sum(buckets.values(), ZERO)
    raw = gross - credits
    outstanding = max(raw, ZERO)
    advance_credit = max(-raw, ZERO)
    reduce = gross - outstanding
    for name in _NETTING_ORDER:
        if reduce <= 0:
            break
        take = min(max(buckets[name], ZERO), reduce)
        buckets[name] -= take
        reduce -= take
    buckets["baseline_current"] += outstanding - sum(buckets.values(), ZERO)
    ageing = Ageing(**buckets)
    overdue = min(ageing.overdue + ageing.baseline_overdue, outstanding)
    pos = Position(
        opening_balance=outstanding - t.invoiced - t.adjustments + t.posted_payments,
        invoiced=t.invoiced,
        paid_in_tally=t.posted_payments,
        verified_awaiting_tally=t.awaiting,
        outstanding=outstanding,
        overdue=overdue,
        advance_credit=advance_credit,
        ageing=ageing,
        max_days_outstanding=max_days,
        collection_status=derive_status(outstanding, overdue, ageing),
        adjustments=t.adjustments,
        balance_source="TALLY",
    )
    return replace(pos, reconciles=check_reconciles(pos))


def sum_positions(positions: Iterable[Position]) -> Position:
    """Outlet (or any group) position = exact sum of its brand positions."""
    ps = list(positions)
    ageing = Ageing()
    for p in ps:
        ageing = ageing + p.ageing
    outstanding = sum((p.outstanding for p in ps), ZERO)
    overdue = sum((p.overdue for p in ps), ZERO)
    total = Position(
        opening_balance=sum((p.opening_balance for p in ps), ZERO),
        baseline_invoiced=sum((p.baseline_invoiced for p in ps), ZERO),
        invoiced=sum((p.invoiced for p in ps), ZERO),
        baseline_collected=sum((p.baseline_collected for p in ps), ZERO),
        paid_in_tally=sum((p.paid_in_tally for p in ps), ZERO),
        verified_awaiting_tally=sum((p.verified_awaiting_tally for p in ps), ZERO),
        outstanding=outstanding,
        overdue=overdue,
        advance_credit=sum((p.advance_credit for p in ps), ZERO),
        ageing=ageing,
        max_days_outstanding=max((p.max_days_outstanding for p in ps), default=0),
        collection_status=derive_status(outstanding, overdue, ageing),
        adjustments=sum((p.adjustments for p in ps), ZERO),
        balance_source="TALLY" if ps and all(p.balance_source == "TALLY" for p in ps) else "BASELINE",
    )
    return replace(total, reconciles=all(p.reconciles for p in ps) and check_reconciles(total))


def position_fields(p: Position) -> dict:
    """kwargs for schemas.position.PositionFields (additive response fields)."""
    return {
        "opening_balance": p.opening_balance,
        "baseline_invoiced": p.baseline_invoiced,
        "baseline_collected": p.baseline_collected,
        "paid_in_tally": p.paid_in_tally,
        "advance_credit": p.advance_credit,
        "ageing": {
            "normal": p.ageing.normal,
            "warning": p.ageing.warning,
            "overdue": p.ageing.overdue,
            "baseline_current": p.ageing.baseline_current,
            "baseline_overdue": p.ageing.baseline_overdue,
        },
        "reconciles": p.reconciles,
        "adjustments": p.adjustments,
        "balance_source": p.balance_source,
        "balance_as_of": p.balance_as_of,
        "tally_opening_balance": p.tally_opening_balance,
        "tally_closing_balance": p.tally_closing_balance,
        "tally_difference": p.tally_difference,
    }


# ---------------------------------------------------------------------------
# Loader (batched queries -> the pure maths above)
# ---------------------------------------------------------------------------

@dataclass
class BrandDetail:
    brand: str                      # canonical display name
    position: Position
    invoice_count: int = 0
    payment_count: int = 0
    latest_invoice_date: date | None = None
    latest_payment_date: date | None = None


@dataclass
class LedgerPosition:
    """One Tally ledger of a physical outlet (receivable sign: + = owed). Release 2.1.0."""
    ledger_id: uuid.UUID | None
    tally_guid: str | None
    name: str
    brand: str | None
    tally_outlet_code: str | None
    opening_balance: Decimal = ZERO
    closing_balance: Decimal = ZERO
    invoiced: Decimal = ZERO
    paid_in_tally: Decimal = ZERO
    adjustments: Decimal = ZERO
    outstanding: Decimal = ZERO
    open_bills_total: Decimal = ZERO
    unallocated: Decimal = ZERO
    tally_difference: Decimal = ZERO
    reconciles: bool = True


@dataclass
class OutletDetail:
    outlet: Position
    brands: list[BrandDetail]
    ledgers: list[LedgerPosition] = field(default_factory=list)
    # Sum of POSTED payment amounts (legacy `total_paid` = posted payments only,
    # excludes the snapshot baseline collection).
    posted_payments_total: Decimal = ZERO
    invoice_settled_total: Decimal = ZERO   # posted money that settled live invoices
    posted_payment_ids: set[uuid.UUID] = field(default_factory=set)


def brand_key(raw: str | None) -> str:
    """Canonical brand identity (alias / case / whitespace-insensitive)."""
    clean = (raw or "").strip()
    if not clean:
        return "unbranded"
    return brand_service.normalize_brand_name(brand_service.resolve_canonical_brand_name(clean))


async def load_outlet_positions(
    session: AsyncSession,
    customer_ids: list[uuid.UUID],
    today: date | None = None,
) -> dict[uuid.UUID, OutletDetail]:
    # Business day is IST; the server clock is UTC (date.today() lags by up to 5.5h after IST midnight).
    today = today or get_ist_now().date()
    if not customer_ids:
        return {}

    master_map = {mb.normalized_name: mb.name for mb in await brand_service.list_brands(session, active_only=True)}

    def display(raw: str | None) -> str:
        clean = (raw or "").strip()
        if not clean:
            return "Unbranded"
        resolved = brand_service.resolve_canonical_brand_name(clean)
        return master_map.get(brand_service.normalize_brand_name(resolved), resolved)

    snapshots = (await session.execute(
        select(OutletFinancialSnapshot).where(OutletFinancialSnapshot.customer_id.in_(customer_ids))
    )).scalars().all()
    assigned = (await session.execute(
        select(CustomerBrand.customer_id, CustomerBrand.brand).where(
            CustomerBrand.customer_id.in_(customer_ids), CustomerBrand.is_active.is_(True)
        )
    )).all()
    # Sales invoices come only from Tally; any other invoice row is not part of the books.
    invoices = (await session.execute(
        select(Invoice).where(Invoice.customer_id.in_(customer_ids), Invoice.source == InvoiceSource.TALLY)
    )).scalars().all()
    payments = (await session.execute(
        select(Payment).where(Payment.customer_id.in_(customer_ids), Payment.status == PaymentStatus.VERIFIED)
    )).scalars().all()

    jobs = await payment_tally.load_jobs(session, [p.id for p in payments])
    posted = [p for p in payments if payment_tally.is_posted(p, jobs.get(p.id))]
    awaiting = [p for p in payments if payment_tally.is_awaiting(p, jobs.get(p.id))]
    paid_by_invoice = await payment_tally.posted_paid_by_invoice(session, [i.id for i in invoices])

    pay_ids = [p.id for p in payments]
    alloc_by_payment: dict[uuid.UUID, list[tuple[str, Decimal]]] = defaultdict(list)
    applied_by_payment: dict[uuid.UUID, Decimal] = {}
    if pay_ids:
        for pid, brand, amt in (await session.execute(
            select(PaymentBrandAllocation.payment_id, PaymentBrandAllocation.brand,
                   PaymentBrandAllocation.allocated_amount)
            .where(PaymentBrandAllocation.payment_id.in_(pay_ids))
        )).all():
            alloc_by_payment[pid].append((brand, amt))
        for pid, amt in (await session.execute(
            select(PaymentInvoiceAllocation.payment_id, func.sum(PaymentInvoiceAllocation.allocated_amount))
            .where(PaymentInvoiceAllocation.payment_id.in_(pay_ids))
            .group_by(PaymentInvoiceAllocation.payment_id)
        )).all():
            applied_by_payment[pid] = amt or ZERO

    invoice_brand = {i.id: i.brand for i in invoices}

    def shares(p: Payment) -> list[tuple[str, Decimal]]:
        """(brand, amount) split of a payment: its brand allocations, else its
        invoice's brand, else Unbranded (on-account)."""
        if alloc_by_payment.get(p.id):
            return [(b or "", a) for b, a in alloc_by_payment[p.id]]
        if p.invoice_id is not None:
            return [(invoice_brand.get(p.invoice_id) or "", p.amount)]
        return [("", p.amount)]

    def unapplied_credit(p: Payment) -> Decimal:
        # On-account money (posted, not tied to a bill) still lowers the outlet's
        # balance, as it does in Tally's ledger - for field collections and for
        # Tally receipts that carry no bill-wise allocation alike. Nothing is
        # guessed onto individual invoices.
        applied = applied_by_payment.get(p.id)
        if applied is None:
            applied = p.amount if p.invoice_id is not None else ZERO
        return max(p.amount - min(applied, p.amount), ZERO)

    # cust -> brand key -> (display, inputs, counters)
    inputs: dict[uuid.UUID, dict[str, BrandInputs]] = defaultdict(dict)
    names: dict[uuid.UUID, dict[str, str]] = defaultdict(dict)
    meta: dict[uuid.UUID, dict[str, dict]] = defaultdict(dict)

    def entry(cid: uuid.UUID, raw: str | None) -> BrandInputs:
        k = brand_key(raw)
        if k not in inputs[cid]:
            inputs[cid][k] = BrandInputs()
            names[cid][k] = display(raw)
            meta[cid][k] = {"invoice_count": 0, "payment_count": 0, "latest_invoice": None, "latest_payment": None}
        return inputs[cid][k]

    for cid in customer_ids:
        inputs[cid]  # ensure every outlet has an entry
    # Snapshot semantics: FLOWS (sales, collection) are summed across every snapshot;
    # STOCK (market outstanding, ageing) is the LATEST snapshot per outlet+brand - a
    # balance is never summed across snapshot dates.
    latest_snapshot: dict[tuple[uuid.UUID, str], OutletFinancialSnapshot] = {}
    for s in snapshots:
        e = entry(s.customer_id, s.brand)
        e.snapshot_sales += s.sales or ZERO
        e.snapshot_collection += s.collection or ZERO
        key = (s.customer_id, s.brand)
        cur = latest_snapshot.get(key)
        if cur is None or (s.snapshot_date, str(s.id)) > (cur.snapshot_date, str(cur.id)):
            latest_snapshot[key] = s
    for s in latest_snapshot.values():
        e = entry(s.customer_id, s.brand)
        e.snapshot_outstanding += s.market_outstanding or ZERO
        e.snapshot_aged_30_plus += sum(
            (v or ZERO for v in (s.bucket_30_45, s.bucket_45_60, s.bucket_60_75, s.bucket_75_90, s.bucket_gt_90)),
            ZERO,
        )
    for cid, b in assigned:
        if b:
            entry(cid, b)

    for inv in invoices:
        e = entry(inv.customer_id, inv.brand)
        a = compute_invoice_aging(inv.invoice_date, inv.amount, paid_by_invoice.get(inv.id, ZERO), today)
        e.invoices.append(InvoiceLine(inv.amount, a.remaining_amount, a.days_outstanding, a.aging_status))
        m = meta[inv.customer_id][brand_key(inv.brand)]
        m["invoice_count"] += 1
        if m["latest_invoice"] is None or inv.invoice_date > m["latest_invoice"]:
            m["latest_invoice"] = inv.invoice_date

    for p in posted:
        credit = unapplied_credit(p)
        ratio = (credit / p.amount) if p.amount else Decimal("0")
        for brand, amount in shares(p):
            e = entry(p.customer_id, brand)
            e.posted_payments += amount
            e.on_account_credit += _q(amount * ratio)
            m = meta[p.customer_id][brand_key(brand)]
            m["payment_count"] += 1
            if m["latest_payment"] is None or p.payment_date > m["latest_payment"]:
                m["latest_payment"] = p.payment_date
    for p in awaiting:
        for brand, amount in shares(p):
            entry(p.customer_id, brand).awaiting += amount

    posted_total: dict[uuid.UUID, Decimal] = defaultdict(lambda: ZERO)
    posted_ids: dict[uuid.UUID, set[uuid.UUID]] = defaultdict(set)
    for p in posted:
        posted_total[p.customer_id] += p.amount
        posted_ids[p.customer_id].add(p.id)
    settled: dict[uuid.UUID, Decimal] = defaultdict(lambda: ZERO)
    for inv in invoices:
        settled[inv.customer_id] += paid_by_invoice.get(inv.id, ZERO)

    out: dict[uuid.UUID, OutletDetail] = {}
    for cid in customer_ids:
        brands: list[BrandDetail] = []
        for k, bi in sorted(inputs[cid].items(), key=lambda kv: names[cid][kv[0]]):
            m = meta[cid][k]
            brands.append(BrandDetail(
                brand=names[cid][k],
                position=compute_brand_position(bi),
                invoice_count=m["invoice_count"],
                payment_count=m["payment_count"],
                latest_invoice_date=m["latest_invoice"],
                latest_payment_date=m["latest_payment"],
            ))
        outlet = sum_positions(b.position for b in brands)
        out[cid] = OutletDetail(
            outlet=outlet,
            brands=brands,
            posted_payments_total=posted_total.get(cid, ZERO),
            invoice_settled_total=settled.get(cid, ZERO),
            posted_payment_ids=posted_ids.get(cid, set()),
        )

    await _apply_tally_balance_mode(
        session, customer_ids, today, out, invoices, posted, awaiting, shares, display, assigned, paid_by_invoice,
    )
    return out


@dataclass
class _Led:
    """A ledger row, or a stand-in built from a legacy customer that has no ledger row yet."""
    id: uuid.UUID | None
    customer_id: uuid.UUID
    tally_guid: str | None
    name: str
    brand: str | None
    code: str | None
    opening: Decimal
    closing: Decimal
    opening_as_of: date | None
    closing_at: datetime | None
    is_primary: bool
    # Brand set explicitly by an admin / the client sheet (brand_override). Only this fills a missing
    # invoice or bill brand: the Tally-derived ledger brand never moves money between brand rows, so
    # bills and the unallocated remainder net exactly as in release 2.0 (rehearsal M1).
    override: str | None = None


async def _tally_ledgers(session, customer_ids) -> dict[uuid.UUID, list[_Led]]:
    """Debtor ledgers with a Tally balance, per outlet (TALLY mode inputs)."""
    from app.models.tally_debtor_ledger import TallyDebtorLedger

    custs = {c.id: c for c in (await session.execute(
        select(Customer).where(Customer.id.in_(customer_ids), Customer.tally_is_debtor.is_(True))
    )).scalars()}
    if not custs:
        return {}
    out: dict[uuid.UUID, list[_Led]] = defaultdict(list)
    rows = (await session.execute(
        select(TallyDebtorLedger).where(TallyDebtorLedger.customer_id.in_(list(custs)))
    )).scalars().all()
    with_rows = set()
    for l in rows:
        with_rows.add(l.customer_id)
        if l.is_debtor is False or l.closing_balance_at is None:
            continue
        out[l.customer_id].append(_Led(
            l.id, l.customer_id, l.tally_guid, l.name, l.effective_brand, l.tally_outlet_code,
            -(l.opening_balance or ZERO), -(l.closing_balance or ZERO), l.opening_balance_as_of,
            l.closing_balance_at, bool(l.is_primary), (l.brand_override or None)))
    for cid, c in custs.items():  # legacy customer without ledger rows: itself is its ledger
        if cid not in with_rows and c.tally_closing_balance_at is not None:
            out[cid].append(_Led(None, cid, c.tally_guid, c.name, None, c.outlet_code,
                                 -(c.tally_opening_balance or ZERO), -(c.tally_closing_balance or ZERO),
                                 c.tally_opening_balance_as_of, c.tally_closing_balance_at, True))
    for cid in out:
        out[cid].sort(key=lambda x: (not x.is_primary, x.name.lower()))
    return dict(out)


async def _apply_tally_balance_mode(
    session, customer_ids, today, out, invoices, posted, awaiting, shares, display, assigned, paid_by_invoice,
) -> None:
    """Replace the baseline position by the Tally-balance position for every outlet
    that is a Tally debtor with ledger balances, once open bills exist.

    Release 2.1.0: an outlet (physical shop) may hold several Tally ledgers (one per
    brand). Each ledger keeps its own opening / closing balance, open bills and
    unallocated remainder; brand rows aggregate across ledgers by brand; the outlet is
    the sum of its ledgers, and `ledgers[]` gives the per-ledger breakdown."""
    run = (await session.execute(
        select(TallySnapshotRun).where(TallySnapshotRun.kind == "BILLS", TallySnapshotRun.status == "COMPLETE")
        .order_by(TallySnapshotRun.as_of_date.desc(), TallySnapshotRun.completed_at.desc()).limit(1)
    )).scalar_one_or_none()
    if run is None:
        return
    leds = await _tally_ledgers(session, customer_ids)
    if not leds:
        return
    ids = list(leds)
    by_id: dict[uuid.UUID, _Led] = {l.id: l for ls in leds.values() for l in ls if l.id is not None}

    def ledger_of(cid, ledger_id) -> _Led:
        """The row's own ledger when it belongs to this outlet, else the outlet's primary ledger."""
        l = by_id.get(ledger_id) if ledger_id is not None else None
        return l if l is not None and l.customer_id == cid else leds[cid][0]

    bills = (await session.execute(
        select(TallyOpenBill).where(TallyOpenBill.customer_id.in_(ids), TallyOpenBill.as_of_date == run.as_of_date)
    )).scalars().all()
    adjustments = (await session.execute(
        select(TallyLedgerAdjustment).where(
            TallyLedgerAdjustment.customer_id.in_(ids), TallyLedgerAdjustment.state == ADJUSTMENT_ACTIVE
        )
    )).scalars().all()

    def since_ok(l: _Led, d) -> bool:
        return l.opening_as_of is None or d >= l.opening_as_of

    def lkey(l: _Led):
        return l.id or ("legacy", l.customer_id)

    brand_of_bill: dict[tuple, str | None] = {}
    for inv in invoices:
        if inv.customer_id in leds and inv.tally_bill_name:
            l = ledger_of(inv.customer_id, getattr(inv, "tally_debtor_ledger_id", None))
            brand_of_bill.setdefault((lkey(l), inv.tally_bill_name), inv.brand or l.override)

    # Inputs are kept per (ledger, brand): every ledger nets its own bills, credits and unallocated
    # remainder exactly as a single-ledger outlet did in 2.0, and brand rows / the outlet are SUMS of
    # those positions. A credit on one brand ledger therefore never reduces another brand ledger's
    # outstanding (strict brand isolation), and linking ledgers never changes any figure.
    t_inputs: dict[uuid.UUID, dict[tuple, TallyBrandInputs]] = defaultdict(dict)
    t_names: dict[uuid.UUID, dict[str, str]] = defaultdict(dict)
    t_meta: dict[uuid.UUID, dict[str, dict]] = defaultdict(dict)
    acc: dict = defaultdict(lambda: {"invoiced": ZERO, "paid": ZERO, "adj": ZERO, "bills": ZERO})

    def entry(cid, l: _Led, raw) -> TallyBrandInputs:
        k = brand_key(raw)
        if k not in t_names[cid]:
            t_names[cid][k] = display(raw)
            t_meta[cid][k] = {"invoice_count": 0, "payment_count": 0, "latest_invoice": None, "latest_payment": None}
        key = (lkey(l), k)
        if key not in t_inputs[cid]:
            t_inputs[cid][key] = TallyBrandInputs()
        return t_inputs[cid][key]

    for cid in ids:
        for l in leds[cid]:
            entry(cid, l, None)  # each ledger's Unbranded row carries its own unallocated remainder
    for cid, b in assigned:
        if cid in leds and b:
            entry(cid, leds[cid][0], b)
    for b in bills:
        l = ledger_of(b.customer_id, getattr(b, "tally_debtor_ledger_id", None))
        days = (today - b.bill_date).days if b.bill_date else -1
        status = classify_age_days(max(days, 0))
        brand = brand_of_bill.get((lkey(l), b.bill_name)) or l.override
        entry(b.customer_id, l, brand).bills.append(InvoiceLine(b.pending_amount, b.pending_amount, days, status))
        acc[lkey(l)]["bills"] += b.pending_amount
    for inv in invoices:
        if inv.customer_id not in leds:
            continue
        l = ledger_of(inv.customer_id, getattr(inv, "tally_debtor_ledger_id", None))
        if since_ok(l, inv.invoice_date):
            brand = inv.brand or l.override
            entry(inv.customer_id, l, brand).invoiced += inv.amount
            acc[lkey(l)]["invoiced"] += inv.amount
            m = t_meta[inv.customer_id][brand_key(brand)]
            m["invoice_count"] += 1
            if m["latest_invoice"] is None or inv.invoice_date > m["latest_invoice"]:
                m["latest_invoice"] = inv.invoice_date
    posted_total: dict[uuid.UUID, Decimal] = defaultdict(lambda: ZERO)
    posted_ids: dict[uuid.UUID, set[uuid.UUID]] = defaultdict(set)
    for p in posted:
        if p.customer_id not in leds:
            continue
        l = ledger_of(p.customer_id, getattr(p, "tally_debtor_ledger_id", None))
        if since_ok(l, p.payment_date):
            posted_total[p.customer_id] += p.amount
            posted_ids[p.customer_id].add(p.id)
            acc[lkey(l)]["paid"] += p.amount
            for brand, amount in shares(p):
                brand = brand or l.override
                entry(p.customer_id, l, brand).posted_payments += amount
                m = t_meta[p.customer_id][brand_key(brand)]
                m["payment_count"] += 1
                if m["latest_payment"] is None or p.payment_date > m["latest_payment"]:
                    m["latest_payment"] = p.payment_date
    for p in awaiting:
        if p.customer_id in leds:
            l = ledger_of(p.customer_id, getattr(p, "tally_debtor_ledger_id", None))
            for brand, amount in shares(p):
                entry(p.customer_id, l, brand).awaiting += amount
    for a in adjustments:
        l = ledger_of(a.customer_id, getattr(a, "tally_debtor_ledger_id", None))
        if since_ok(l, a.voucher_date):
            entry(a.customer_id, l, None).adjustments += a.amount
            acc[lkey(l)]["adj"] += a.amount

    for cid, ls in leds.items():
        ledger_rows: list[LedgerPosition] = []
        for l in ls:
            x = acc[lkey(l)]
            unallocated = l.closing - x["bills"]
            entry(cid, l, None).residue = unallocated
            diff = _q(l.opening + x["invoiced"] + x["adj"] - x["paid"] - l.closing)
            ledger_rows.append(LedgerPosition(
                ledger_id=l.id, tally_guid=l.tally_guid, name=l.name, brand=l.brand, tally_outlet_code=l.code,
                opening_balance=_q(l.opening), closing_balance=_q(l.closing), invoiced=_q(x["invoiced"]),
                paid_in_tally=_q(x["paid"]), adjustments=_q(x["adj"]), outstanding=_q(l.closing),
                open_bills_total=_q(x["bills"]), unallocated=_q(unallocated), tally_difference=diff,
                reconciles=diff == ZERO,
            ))
        by_brand: dict[str, list[Position]] = defaultdict(list)
        for (_lk, k), ti in t_inputs[cid].items():
            by_brand[k].append(compute_tally_brand_position(ti))
        brands = []
        for k in sorted(by_brand, key=lambda kk: t_names[cid][kk]):
            m = t_meta[cid][k]
            ps = by_brand[k]
            brands.append(BrandDetail(
                brand=t_names[cid][k], position=ps[0] if len(ps) == 1 else sum_positions(ps),
                invoice_count=m["invoice_count"], payment_count=m["payment_count"],
                latest_invoice_date=m["latest_invoice"], latest_payment_date=m["latest_payment"],
            ))
        total = sum_positions(b.position for b in brands)
        opening = sum((l.opening for l in ls), ZERO)
        closing = sum((l.closing for l in ls), ZERO)
        diff = _q(opening + total.invoiced + total.adjustments - total.paid_in_tally - closing)
        as_of = max((l.closing_at for l in ls if l.closing_at), default=None)
        total = replace(
            total, balance_as_of=as_of, tally_opening_balance=opening,
            tally_closing_balance=closing, tally_difference=diff,
            reconciles=total.reconciles and diff == ZERO,
        )
        out[cid] = OutletDetail(
            outlet=total, brands=brands, ledgers=ledger_rows,
            posted_payments_total=posted_total.get(cid, ZERO),
            invoice_settled_total=sum(
                (paid_by_invoice.get(i.id, ZERO) for i in invoices if i.customer_id == cid), ZERO
            ),
            posted_payment_ids=posted_ids.get(cid, set()),
        )
