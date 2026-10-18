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
  invoiced            baseline_invoiced + sum(live Invoice.amount)
  baseline_collected  OutletFinancialSnapshot.collection (Tally baseline)
  paid_in_tally       baseline_collected + POSTED payments (receipt in Tally)
  outstanding         max(LATEST snapshot.market_outstanding per brand + live invoice remaining
                          - POSTED on-account (unapplied) MANUAL credit, 0)
  opening_balance     DERIVED = outstanding - invoiced + paid_in_tally, i.e. the
                      Tally baseline carried forward into the period. It also
                      absorbs `advance_credit` (over-payment that cannot push
                      outstanding below zero): carried-forward balance excluding
                      advance = opening_balance - advance_credit.
  awaiting            verified MANUAL payments not yet confirmed in Tally;
                      NOT in paid_in_tally, NOT in outstanding.

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

Both the single-outlet path (account_service) and the bulk path
(collections_service) call `load_outlet_positions`, which batches the queries
and then calls the same pure `compute_brand_position` / `sum_positions`.
"""
from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass, field, replace
from datetime import date
from decimal import Decimal
from typing import Iterable

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.datetime_utils import get_ist_now
from app.models.customer_brand import CustomerBrand
from app.models.invoice import Invoice
from app.models.outlet_financial_snapshot import OutletFinancialSnapshot
from app.models.payment import Payment, PaymentBrandAllocation, PaymentSource, PaymentStatus
from app.models.payment_invoice_allocation import PaymentInvoiceAllocation
from app.services import brand_service, payment_tally
from app.services.aging_service import AgingStatus, compute_invoice_aging

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
    on_account_credit: Decimal = ZERO     # unapplied part of POSTED MANUAL payments


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
        p.opening_balance + p.invoiced - p.paid_in_tally == p.outstanding
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
class OutletDetail:
    outlet: Position
    brands: list[BrandDetail]
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
    invoices = (await session.execute(
        select(Invoice).where(Invoice.customer_id.in_(customer_ids))
    )).scalars().all()
    payments = (await session.execute(
        select(Payment).where(Payment.customer_id.in_(customer_ids), Payment.status == PaymentStatus.VERIFIED)
    )).scalars().all()

    jobs = await payment_tally.load_jobs(session, [p.id for p in payments])
    posted = [p for p in payments if payment_tally.is_posted(p, jobs.get(p.id))]
    awaiting = [p for p in payments if not payment_tally.is_posted(p, jobs.get(p.id))]
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
        if p.source != PaymentSource.MANUAL:
            return ZERO
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
    return out
