"""
Account Service: the outlet "Account / Collections" panel - summary,
brand-level aggregation, and the employee-visibility ownership rule.

Financial data is more sensitive than the basic outlet profile fields
customers.py already exposes to any authenticated user, so an EMPLOYEE may
only view a customer's account/invoices/payments if they have at least one
visit assigned to that outlet - mirroring visit_service's ownership pattern
rather than inventing a new one.
"""
from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.payment import PaymentStatus
from app.models.user import User
from app.repositories.payment_repo import PaymentRepository
from app.repositories.visit_repo import VisitRepository
from app.schemas.account import AccountSummary, BrandSummary
from app.schemas.invoice import InvoiceRead
from app.services.aging_service import AgingStatus
from app.services.customer_service import assert_employee_can_view_customer, get_customer
from app.services.invoice_service import list_invoices_for_customer, to_invoice_read
from app.services.payment_service import to_payment_read


async def assert_employee_can_view_account(
    customer_id: uuid.UUID, current_user: User, session: AsyncSession
) -> None:
    """
    P2-1: delegates to customer_service's single authoritative
    visited-outlet check (an EMPLOYEE may act on a customer only if they
    have at least one visit assigned to it) - this used to reimplement the
    identical Visit.customer_id/employee_id count query independently.
    """
    await assert_employee_can_view_customer(customer_id, current_user, session)


async def get_account_summary(
    customer_id: uuid.UUID, current_user: User, session: AsyncSession, today: date | None = None
) -> AccountSummary:
    await assert_employee_can_view_account(customer_id, current_user, session)
    customer = await get_customer(customer_id, session)
    today = today or date.today()

    invoices = await list_invoices_for_customer(customer_id, session)
    invoice_reads: list[InvoiceRead] = [await to_invoice_read(inv, session, today) for inv in invoices]

    payment_repo = PaymentRepository(session)
    payments = await payment_repo.list_by_customer(customer_id)
    verified_payments = [p for p in payments if p.status == PaymentStatus.VERIFIED]

    total_invoiced = sum((inv.amount for inv in invoice_reads), Decimal("0"))
    total_paid = sum((p.amount for p in verified_payments), Decimal("0"))
    # Not sum(inv.remaining_amount): a verified payment the employee didn't
    # tie to a specific invoice (deliberately allowed - see PaymentCreate)
    # would otherwise never reduce the outlet's total outstanding, even
    # though it demonstrably reduces what they owe overall. Per-invoice
    # remaining_amount only reflects payments allocated to THAT invoice;
    # the aggregate must account for unallocated ones too.
    total_outstanding = max(total_invoiced - total_paid, Decimal("0"))
    overdue_amount = sum(
        (inv.remaining_amount for inv in invoice_reads if inv.aging_status == AgingStatus.OVERDUE),
        Decimal("0"),
    )
    outstanding_invoices = [inv for inv in invoice_reads if inv.remaining_amount > 0]
    max_days_outstanding = max((inv.days_outstanding for inv in outstanding_invoices), default=0)

    if any(inv.aging_status == AgingStatus.OVERDUE for inv in invoice_reads):
        collection_status = AgingStatus.OVERDUE
    elif any(inv.aging_status == AgingStatus.WARNING for inv in invoice_reads):
        collection_status = AgingStatus.WARNING
    elif outstanding_invoices:
        collection_status = AgingStatus.NORMAL
    else:
        collection_status = AgingStatus.PAID

    sorted_payments = sorted(payments, key=lambda p: (p.payment_date, p.created_at), reverse=True)
    most_recent_payment = to_payment_read(sorted_payments[0]) if sorted_payments else None

    visit_repo = VisitRepository(session)
    most_recent_visit = await visit_repo.get_most_recent_checked_in(customer_id)

    brand_totals: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "invoiced": Decimal("0"), "outstanding": Decimal("0"), "overdue": Decimal("0"),
            "invoice_count": 0, "payment_count": 0,
            "latest_invoice_date": None, "latest_payment_date": None,
        }
    )
    for inv in invoice_reads:
        brand = inv.brand or "Unbranded"
        totals = brand_totals[brand]
        totals["invoiced"] += inv.amount
        totals["outstanding"] += inv.remaining_amount
        if inv.aging_status == AgingStatus.OVERDUE:
            totals["overdue"] += inv.remaining_amount
        totals["invoice_count"] += 1
        if totals["latest_invoice_date"] is None or inv.invoice_date > totals["latest_invoice_date"]:
            totals["latest_invoice_date"] = inv.invoice_date

    # Attribute payments to a brand only through the invoice they're
    # actually allocated to - an unallocated payment (invoice_id is None,
    # deliberately allowed, see above) has no brand and is left out rather
    # than guessed into a bucket.
    invoice_brand_by_id = {inv.id: (inv.brand or "Unbranded") for inv in invoice_reads}
    for p in verified_payments:
        if p.invoice_id is None:
            continue
        brand = invoice_brand_by_id.get(p.invoice_id)
        if brand is None:
            continue
        totals = brand_totals[brand]
        totals["payment_count"] += 1
        if totals["latest_payment_date"] is None or p.payment_date > totals["latest_payment_date"]:
            totals["latest_payment_date"] = p.payment_date

    brand_summary = [
        BrandSummary(
            brand=brand,
            total_invoiced=totals["invoiced"],
            total_paid=totals["invoiced"] - totals["outstanding"],
            total_outstanding=totals["outstanding"],
            overdue_amount=totals["overdue"],
            invoice_count=totals["invoice_count"],
            payment_count=totals["payment_count"],
            latest_invoice_date=totals["latest_invoice_date"],
            latest_payment_date=totals["latest_payment_date"],
        )
        for brand, totals in sorted(brand_totals.items())
    ]

    return AccountSummary(
        customer_id=customer.id,
        customer_name=customer.name,
        outlet_code=customer.outlet_code,
        total_invoiced=total_invoiced,
        total_paid=total_paid,
        total_outstanding=total_outstanding,
        overdue_amount=overdue_amount,
        max_days_outstanding=max_days_outstanding,
        collection_status=collection_status,
        most_recent_payment=most_recent_payment,
        most_recent_visit_date=most_recent_visit.check_in_at if most_recent_visit else None,
        most_recent_visit_employee_name=most_recent_visit.employee.full_name if most_recent_visit else None,
        recent_invoices=invoice_reads[:20],
        recent_payments=[to_payment_read(p) for p in sorted_payments[:20]],
        brand_summary=brand_summary,
    )
