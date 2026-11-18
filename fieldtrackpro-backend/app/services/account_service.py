from __future__ import annotations

import logging
import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions.custom import BaseAPIException
from app.models.customer import Customer
from app.models.customer_brand import CustomerBrand
from app.models.invoice import Invoice
from app.models.outlet_financial_snapshot import OutletFinancialSnapshot
from app.models.payment import Payment, PaymentBrandAllocation, PaymentSource, PaymentStatus
from app.models.user import Role, User
from app.repositories.customer_repo import CustomerRepository
from app.repositories.invoice_repo import InvoiceRepository
from app.repositories.payment_repo import PaymentRepository
from app.repositories.visit_repo import VisitRepository
from app.schemas.account import AccountSummary, BrandSummary, LedgerPosition
from app.schemas.invoice import AgingStatus, InvoiceRead
from app.services.reporting_floor import is_live_invoice, is_live_payment
from app.schemas.payment import PaymentRead
from app.services import account_position, invoice_service, payment_tally
from app.services.account_position import position_fields

logger = logging.getLogger("fieldtrackpro")


def to_payment_read(p: Payment, job=None, is_admin: bool = False) -> PaymentRead:
    from app.services.payment_service import to_payment_read as _to_read
    return _to_read(p, job, is_admin)


async def assert_employee_can_view_account(
    customer_id: uuid.UUID,
    current_user: User,
    session: AsyncSession,
) -> None:
    """
    Confines an EMPLOYEE to outlets in their scope (assigned, on their visits, or in a covered Area).
    ADMIN can view any outlet.
    """
    from app.services.customer_service import assert_employee_can_view_customer

    await assert_employee_can_view_customer(customer_id, current_user, session)


async def _attach_ledger_names(session: AsyncSession, payments) -> None:
    from app.models.tally_debtor_ledger import TallyDebtorLedger
    ids = {p.tally_debtor_ledger_id for p in payments if getattr(p, "tally_debtor_ledger_id", None)}
    if not ids:
        return
    names = dict((await session.execute(
        select(TallyDebtorLedger.id, TallyDebtorLedger.name).where(TallyDebtorLedger.id.in_(ids))
    )).all())
    for p in payments:
        p._tally_ledger_name = names.get(getattr(p, "tally_debtor_ledger_id", None))


async def get_account_history(customer_id: uuid.UUID, current_user: User, session: AsyncSession,
                              limit: int = 200, offset: int = 0):
    """Every Tally invoice, receipt and adjustment of every ledger of this physical outlet, newest
    first, with ledger and brand (retired rows included and marked). Release 2.1.0."""
    from sqlalchemy import text
    from app.schemas.account import HistoryItem, HistoryPage

    await assert_employee_can_view_account(customer_id, current_user, session)
    if await CustomerRepository(session).get_by_id(customer_id) is None:
        raise BaseAPIException(status_code=404, detail="Outlet not found", error_code="CUSTOMER_NOT_FOUND")
    base = """
      SELECT i.invoice_date d, 'INVOICE' kind, i.tally_voucher_type vt, i.invoice_number vn, i.amount amt,
             COALESCE(i.brand, NULLIF(l.brand_override, ''), l.brand_tally) brand, l.id lid, l.name lname,
             i.tally_bill_name bill, i.narration narr, (i.source = 'TALLY_RETIRED') retired, i.tally_retired_reason rr,
             i.created_at ts
        FROM invoices i LEFT JOIN tally_debtor_ledgers l ON l.id = i.tally_debtor_ledger_id
       WHERE i.customer_id = :cid AND i.source IN ('TALLY', 'TALLY_RETIRED')
      UNION ALL
      SELECT p.payment_date, 'PAYMENT', p.tally_voucher_type, NULL, p.amount,
             COALESCE((SELECT min(a.brand) FROM payment_brand_allocations a WHERE a.payment_id = p.id),
                      NULLIF(l.brand_override, ''), l.brand_tally),
             l.id, l.name, NULL, p.narration, (p.source = 'TALLY_RETIRED'), p.tally_retired_reason, p.created_at
        FROM payments p LEFT JOIN tally_debtor_ledgers l ON l.id = p.tally_debtor_ledger_id
       WHERE p.customer_id = :cid AND p.source IN ('TALLY', 'TALLY_RETIRED')
      UNION ALL
      SELECT a.voucher_date, 'ADJUSTMENT', a.voucher_type, a.voucher_number, a.amount,
             COALESCE(NULLIF(l.brand_override, ''), l.brand_tally), l.id, l.name, NULL, a.narration,
             (a.state = 'RETIRED'), a.retired_reason, a.created_at
        FROM tally_ledger_adjustments a LEFT JOIN tally_debtor_ledgers l ON l.id = a.tally_debtor_ledger_id
       WHERE a.customer_id = :cid
    """
    total = (await session.execute(text(f"SELECT count(*) FROM ({base}) h"), {"cid": customer_id})).scalar() or 0
    rows = (await session.execute(text(f"SELECT * FROM ({base}) h ORDER BY d DESC, ts DESC LIMIT :lim OFFSET :off"),
                                  {"cid": customer_id, "lim": limit, "off": offset})).mappings().all()
    return HistoryPage(total=total, items=[HistoryItem(
        date=r["d"], kind=r["kind"], voucher_type=r["vt"], voucher_number=r["vn"], amount=r["amt"], brand=r["brand"],
        ledger_id=r["lid"], ledger_name=r["lname"], bill_name=r["bill"], narration=r["narr"],
        retired=bool(r["retired"]), retired_reason=r["rr"]) for r in rows])


async def get_account_summary(
    customer_id: uuid.UUID,
    current_user: User,
    session: AsyncSession,
) -> AccountSummary:
    """
    Authoritative single source of truth for outlet account summaries.
    Incorporates authoritative OutletFinancialSnapshot financial baseline, active customer brands,
    invoices, and payment allocations.

    TALLY IS THE FINAL TRUTH (see payment_tally.py). A collection moves
    PENDING_VERIFICATION -> VERIFIED (cash received) -> POSTED (Tally write-back
    CONFIRMED). Only POSTED payments (and payments that originate from Tally)
    are "paid" for outstanding math:
      * total_paid / BrandSummary.total_paid / payment_count  = posted only;
      * verified_awaiting_tally_amount (total and per brand)   = verified MANUAL
        payments whose receipt is not yet confirmed in Tally ("Verified, not
        yet in Tally") - they do NOT reduce any outstanding yet;
      * total_outstanding = sum of the per-brand total_outstanding buckets (Tally
        snapshot baseline + invoice remaining minus posted MANUAL on-account credit); per-brand total_outstanding is netted the same
        way by the payment's brand allocations (never spilling across brands).
    """
    await assert_employee_can_view_account(customer_id, current_user, session)

    cust_repo = CustomerRepository(session)
    customer = await cust_repo.get_by_id(customer_id)
    if customer is None:
        raise BaseAPIException(
            status_code=404,
            detail="Outlet not found",
            error_code="CUSTOMER_NOT_FOUND",
        )

    # ALL money maths lives in account_position (shared with the collections
    # overview): per brand and for the outlet, opening + invoiced - paid_in_tally
    # == outstanding, ageing buckets sum to outstanding, awaiting stays separate.
    detail = (await account_position.load_outlet_positions(session, [customer_id]))[customer_id]
    outlet = detail.outlet

    inv_repo = InvoiceRepository(session)
    # 2.2.0 (B4): the summary is a live-FY view; history stays in get_account_history.
    invoices = [i for i in await inv_repo.list_by_customer(customer_id) if is_live_invoice(i)]

    pay_repo = PaymentRepository(session)
    payments = [p for p in await pay_repo.list_by_customer(customer_id) if is_live_payment(p)]
    is_admin = current_user.is_admin
    jobs = await payment_tally.load_jobs(session, [p.id for p in payments])
    await _attach_ledger_names(session, payments)

    # Per-invoice display rows (recent list + legacy gross MIS view below); the
    # headline / brand figures come from `detail`, never from these.
    invoice_reads: list[InvoiceRead] = [
        await invoice_service.to_invoice_read(inv, session) for inv in invoices
    ]

    brand_summary: list[BrandSummary] = [
        BrandSummary(
            brand=b.brand,
            total_invoiced=b.position.invoiced,
            total_paid=b.position.paid_in_tally,
            verified_awaiting_tally_amount=b.position.verified_awaiting_tally,
            total_outstanding=b.position.outstanding,
            overdue_amount=b.position.overdue,
            invoice_count=b.invoice_count,
            payment_count=b.payment_count,
            latest_invoice_date=b.latest_invoice_date,
            latest_payment_date=b.latest_payment_date,
            **position_fields(b.position),
        )
        for b in detail.brands
    ]

    # Paid headline = payments POSTED to Tally only (snapshot baseline collection
    # is separate: paid_in_tally = baseline_collected + total_paid).
    total_paid = detail.posted_payments_total
    advance_amount = max(total_paid - detail.invoice_settled_total, Decimal("0.00"))

    # Legacy gross MIS view (not netted for on-account credit); see `ageing`.
    snapshots = (await session.execute(
        select(OutletFinancialSnapshot).where(OutletFinancialSnapshot.customer_id == customer_id)
    )).scalars().all()
    z = Decimal("0.00")
    def _inv_sum(lo: int, hi: int) -> Decimal:
        return sum((i.remaining_amount for i in invoice_reads if lo <= i.days_outstanding <= hi and i.remaining_amount > 0), z)
    aging_buckets = {
        "0-30": sum(((s.bucket_lt_15 or z) + (s.bucket_15_30 or z) for s in snapshots), z) + _inv_sum(0, 30),
        "31-60": sum(((s.bucket_30_45 or z) + (s.bucket_45_60 or z) for s in snapshots), z) + _inv_sum(31, 60),
        "61-90": sum(((s.bucket_60_75 or z) + (s.bucket_75_90 or z) for s in snapshots), z) + _inv_sum(61, 90),
        "90+": sum((s.bucket_gt_90 or z for s in snapshots), z) + _inv_sum(91, 10**9),
    }

    sorted_payments = sorted(payments, key=lambda p: (p.payment_date, p.created_at), reverse=True)
    most_recent_payment = (
        to_payment_read(sorted_payments[0], jobs.get(sorted_payments[0].id), is_admin) if sorted_payments else None
    )

    visit_repo = VisitRepository(session)
    most_recent_visit = await visit_repo.get_most_recent_checked_in(customer_id)

    return AccountSummary(
        customer_id=customer.id,
        customer_name=customer.name,
        outlet_code=customer.outlet_code,
        total_invoiced=outlet.invoiced,
        total_paid=total_paid,
        verified_awaiting_tally_amount=outlet.verified_awaiting_tally,
        total_outstanding=outlet.outstanding,
        advance_amount=advance_amount,
        overdue_amount=outlet.overdue,
        max_days_outstanding=outlet.max_days_outstanding,
        collection_status=outlet.collection_status,
        most_recent_payment=most_recent_payment,
        most_recent_visit_date=most_recent_visit.check_in_at if most_recent_visit else None,
        most_recent_visit_employee_name=most_recent_visit.employee.full_name if most_recent_visit else None,
        recent_invoices=invoice_reads[:20],
        recent_payments=[to_payment_read(p, jobs.get(p.id), is_admin) for p in sorted_payments[:20]],
        brand_summary=brand_summary,
        aging_buckets=aging_buckets,
        ledgers=[LedgerPosition(**vars(l)) for l in detail.ledgers],
        **position_fields(outlet),
    )
