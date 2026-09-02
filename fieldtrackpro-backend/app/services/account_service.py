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
from app.models.payment import Payment, PaymentBrandAllocation, PaymentStatus
from app.models.user import Role, User
from app.repositories.customer_repo import CustomerRepository
from app.repositories.invoice_repo import InvoiceRepository
from app.repositories.payment_repo import PaymentRepository
from app.repositories.visit_repo import VisitRepository
from app.schemas.account import AccountSummary, BrandSummary
from app.schemas.invoice import AgingStatus, InvoiceRead
from app.schemas.payment import PaymentRead
from app.services import brand_service, invoice_service

logger = logging.getLogger("fieldtrackpro")


def to_payment_read(p: Payment) -> PaymentRead:
    from app.services.payment_service import to_payment_read as _to_read
    return _to_read(p)


async def assert_employee_can_view_account(
    customer_id: uuid.UUID,
    current_user: User,
    session: AsyncSession,
) -> None:
    """
    Confines an EMPLOYEE to outlets they have access to (assigned, visited, or within directory scope).
    ADMIN can view any outlet.
    """
    if current_user.role == Role.ADMIN:
        return

    cust_repo = CustomerRepository(session)
    customer = await cust_repo.get_by_id(customer_id)
    if customer is None:
        raise BaseAPIException(
            status_code=404,
            detail="Outlet not found",
            error_code="CUSTOMER_NOT_FOUND",
        )


async def get_account_summary(
    customer_id: uuid.UUID,
    current_user: User,
    session: AsyncSession,
) -> AccountSummary:
    """
    Authoritative single source of truth for outlet account summaries.
    Incorporates authoritative OutletFinancialSnapshot financial baseline, active customer brands,
    invoices, and verified payment allocations.
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

    # 1. Fetch registered master brands (USHA, VU, Zebronics)
    master_brands = await brand_service.list_brands(session, active_only=True)
    master_map: dict[str, str] = {mb.normalized_name: mb.name for mb in master_brands}

    # 2. Fetch customer's financial snapshots (authoritative baseline from DMS/OS Excel files)
    stmt_snaps = select(OutletFinancialSnapshot).where(OutletFinancialSnapshot.customer_id == customer_id)
    snapshots = (await session.execute(stmt_snaps)).scalars().all()

    # 3. Fetch active CustomerBrand mappings
    stmt_cb = select(CustomerBrand.brand).where(
        CustomerBrand.customer_id == customer_id,
        CustomerBrand.is_active.is_(True),
    )
    assigned_brands = (await session.execute(stmt_cb)).scalars().all()

    # 4. Fetch invoices & payments
    inv_repo = InvoiceRepository(session)
    invoices = await inv_repo.list_by_customer(customer_id)

    pay_repo = PaymentRepository(session)
    payments = await pay_repo.list_by_customer(customer_id)
    verified_payments = [p for p in payments if p.status == PaymentStatus.VERIFIED]

    invoice_reads: list[InvoiceRead] = [
        await invoice_service.to_invoice_read(inv, session) for inv in invoices
    ]

    # 5. Build unified known brands map with canonical casing
    known_brands_map: dict[str, str] = {}

    def get_canonical_brand(raw_name: str) -> str:
        clean = (raw_name or "").strip()
        if not clean:
            return "Unbranded"
        resolved = brand_service.resolve_canonical_brand_name(clean)
        norm = brand_service.normalize_brand_name(resolved)
        return master_map.get(norm, resolved)

    for s in snapshots:
        if s.brand:
            c = get_canonical_brand(s.brand)
            known_brands_map[c.upper()] = c

    for b in assigned_brands:
        if b:
            c = get_canonical_brand(b)
            known_brands_map[c.upper()] = c

    for inv in invoice_reads:
        c = get_canonical_brand(inv.brand or "")
        known_brands_map[c.upper()] = c

    for p in verified_payments:
        if p.allocations:
            for alloc in p.allocations:
                c = get_canonical_brand(alloc.brand or "")
                known_brands_map[c.upper()] = c

    # 6. Initialize brand totals
    brand_totals: dict[str, dict[str, Any]] = {
        canonical_name: {
            "invoiced": Decimal("0.00"),
            "paid": Decimal("0.00"),
            "outstanding": Decimal("0.00"),
            "overdue": Decimal("0.00"),
            "invoice_count": 0,
            "payment_count": 0,
            "latest_invoice_date": None,
            "latest_payment_date": None,
        }
        for canonical_name in known_brands_map.values()
    }

    def get_brand_entry(brand_name: str) -> dict[str, Any]:
        canonical = get_canonical_brand(brand_name)
        if canonical not in brand_totals:
            brand_totals[canonical] = {
                "invoiced": Decimal("0.00"),
                "paid": Decimal("0.00"),
                "outstanding": Decimal("0.00"),
                "overdue": Decimal("0.00"),
                "invoice_count": 0,
                "payment_count": 0,
                "latest_invoice_date": None,
                "latest_payment_date": None,
            }
        return brand_totals[canonical]

    # Populate baseline snapshot financials
    for s in snapshots:
        totals = get_brand_entry(s.brand)
        totals["invoiced"] += (s.sales or Decimal("0.00"))
        totals["paid"] += (s.collection or Decimal("0.00"))
        totals["outstanding"] += (s.market_outstanding or Decimal("0.00"))
        totals["overdue"] += (s.bucket_gt_90 or Decimal("0.00"))

    # Incorporate real-time invoices
    for inv in invoice_reads:
        brand = inv.brand or "Unbranded"
        totals = get_brand_entry(brand)
        totals["invoiced"] += inv.amount
        totals["outstanding"] += inv.remaining_amount
        if inv.aging_status == AgingStatus.OVERDUE:
            totals["overdue"] += inv.remaining_amount
        totals["invoice_count"] += 1
        if totals["latest_invoice_date"] is None or inv.invoice_date > totals["latest_invoice_date"]:
            totals["latest_invoice_date"] = inv.invoice_date

    invoice_brand_by_id = {inv.id: (inv.brand or "Unbranded") for inv in invoice_reads}

    # Attribute verified payments strictly by brand allocations
    for p in verified_payments:
        if p.allocations:
            for alloc in p.allocations:
                brand = alloc.brand or "Unbranded"
                totals = get_brand_entry(brand)
                totals["paid"] += alloc.allocated_amount
                totals["outstanding"] = max(totals["outstanding"] - alloc.allocated_amount, Decimal("0.00"))
                totals["payment_count"] += 1
                if totals["latest_payment_date"] is None or p.payment_date > totals["latest_payment_date"]:
                    totals["latest_payment_date"] = p.payment_date
        elif p.invoice_id is not None:
            brand = invoice_brand_by_id.get(p.invoice_id, "Unbranded")
            totals = get_brand_entry(brand)
            totals["paid"] += p.amount
            totals["outstanding"] = max(totals["outstanding"] - p.amount, Decimal("0.00"))
            totals["payment_count"] += 1
            if totals["latest_payment_date"] is None or p.payment_date > totals["latest_payment_date"]:
                totals["latest_payment_date"] = p.payment_date

    # Build strictly isolated brand summary
    brand_summary: list[BrandSummary] = []
    for brand, totals in sorted(brand_totals.items()):
        brand_invoiced = totals["invoiced"]
        brand_paid = totals["paid"]
        brand_outstanding = max(totals["outstanding"], Decimal("0.00"))
        brand_overdue = min(totals["overdue"], brand_outstanding)
        brand_summary.append(
            BrandSummary(
                brand=brand,
                total_invoiced=brand_invoiced,
                total_paid=brand_paid,
                total_outstanding=brand_outstanding,
                overdue_amount=brand_overdue,
                invoice_count=totals["invoice_count"],
                payment_count=totals["payment_count"],
                latest_invoice_date=totals["latest_invoice_date"],
                latest_payment_date=totals["latest_payment_date"],
            )
        )

    # Compute overall account aggregates
    total_invoiced = sum((b.total_invoiced for b in brand_summary), Decimal("0.00"))
    total_paid = sum((b.total_paid for b in brand_summary), Decimal("0.00"))
    total_outstanding = sum((b.total_outstanding for b in brand_summary), Decimal("0.00"))
    overdue_amount = sum((b.overdue_amount for b in brand_summary), Decimal("0.00"))

    # Snapshot aging buckets aggregation
    snap_bucket_0_30 = sum(((s.bucket_lt_15 or Decimal("0.00")) + (s.bucket_15_30 or Decimal("0.00")) for s in snapshots), Decimal("0.00"))
    snap_bucket_31_60 = sum(((s.bucket_30_45 or Decimal("0.00")) + (s.bucket_45_60 or Decimal("0.00")) for s in snapshots), Decimal("0.00"))
    snap_bucket_61_90 = sum(((s.bucket_60_75 or Decimal("0.00")) + (s.bucket_75_90 or Decimal("0.00")) for s in snapshots), Decimal("0.00"))
    snap_bucket_gt_90 = sum((s.bucket_gt_90 or Decimal("0.00") for s in snapshots), Decimal("0.00"))

    inv_bucket_0_30 = sum((inv.remaining_amount for inv in invoice_reads if 0 <= inv.days_outstanding <= 30 and inv.remaining_amount > 0), Decimal("0.00"))
    inv_bucket_31_60 = sum((inv.remaining_amount for inv in invoice_reads if 31 <= inv.days_outstanding <= 60 and inv.remaining_amount > 0), Decimal("0.00"))
    inv_bucket_61_90 = sum((inv.remaining_amount for inv in invoice_reads if 61 <= inv.days_outstanding <= 90 and inv.remaining_amount > 0), Decimal("0.00"))
    inv_bucket_gt_90 = sum((inv.remaining_amount for inv in invoice_reads if inv.days_outstanding > 90 and inv.remaining_amount > 0), Decimal("0.00"))

    aging_buckets = {
        "0-30": snap_bucket_0_30 + inv_bucket_0_30,
        "31-60": snap_bucket_31_60 + inv_bucket_31_60,
        "61-90": snap_bucket_61_90 + inv_bucket_61_90,
        "90+": snap_bucket_gt_90 + inv_bucket_gt_90,
    }

    outstanding_invoices = [inv for inv in invoice_reads if inv.remaining_amount > 0]
    max_days_outstanding = max((inv.days_outstanding for inv in outstanding_invoices), default=0)

    if overdue_amount > 0:
        collection_status = AgingStatus.OVERDUE
    elif total_outstanding > 0:
        collection_status = AgingStatus.NORMAL
    else:
        collection_status = AgingStatus.PAID

    sorted_payments = sorted(payments, key=lambda p: (p.payment_date, p.created_at), reverse=True)
    most_recent_payment = to_payment_read(sorted_payments[0]) if sorted_payments else None

    visit_repo = VisitRepository(session)
    most_recent_visit = await visit_repo.get_most_recent_checked_in(customer_id)

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
        aging_buckets=aging_buckets,
    )
