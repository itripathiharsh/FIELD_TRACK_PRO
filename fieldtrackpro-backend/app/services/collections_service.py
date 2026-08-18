"""
Collections Overview service.

Aggregates every outlet's financial position - invoiced, paid, outstanding,
ageing bucket, last payment, last visit - in bulk, reusing the exact same
per-invoice calculation account_service.get_account_summary already uses
(aging_service.compute_invoice_aging) rather than a second, independently
maintained ageing calculation. The difference from account_service is scale:
this runs the same math across every matching outlet in a handful of bulk
queries, instead of one outlet at a time.

Filters that are stored columns (search, territory, employee) are applied in
SQL; filters on derived values (ageing/collection status) are applied in
Python after the per-outlet aggregation, since that status is never stored.
"""
from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import date
from decimal import Decimal

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.area import Area
from app.models.customer import Customer
from app.models.employee import Employee
from app.models.employee_area_assignment import EmployeeAreaAssignment
from app.models.invoice import Invoice
from app.models.payment import Payment, PaymentStatus
from app.models.territory import Territory
from app.models.visit import Visit
from app.schemas.collections import (
    AssignedEmployeeSummary,
    CollectionsOverviewResponse,
    CollectionsOverviewTotals,
    OutletCollectionRow,
)
from app.services.aging_service import AgingStatus, MisBucket, compute_invoice_aging, compute_mis_bucket

ZERO = Decimal("0")

_BUCKET_TOTAL_FIELDS: dict[MisBucket, str] = {
    MisBucket.DAYS_0_15: "bucket_0_15",
    MisBucket.DAYS_16_30: "bucket_16_30",
    MisBucket.DAYS_31_60: "bucket_31_60",
    MisBucket.DAYS_61_90: "bucket_61_90",
    MisBucket.DAYS_90_PLUS: "bucket_90_plus",
}


def _empty_response(skip: int, limit: int) -> CollectionsOverviewResponse:
    return CollectionsOverviewResponse(
        totals=CollectionsOverviewTotals(
            total_outlets=0, total_invoiced=ZERO, total_paid=ZERO, total_outstanding=ZERO,
            current_amount=ZERO, bucket_0_15=ZERO, bucket_16_30=ZERO, bucket_31_60=ZERO,
            bucket_61_90=ZERO, bucket_90_plus=ZERO,
        ),
        outlets=[], total_count=0, skip=skip, limit=limit,
    )


async def get_collections_overview(
    session: AsyncSession,
    search: str | None = None,
    territory_id: uuid.UUID | None = None,
    area_id: uuid.UUID | None = None,
    employee_id: uuid.UUID | None = None,
    collection_status: AgingStatus | None = None,
    skip: int = 0,
    limit: int = 50,
    today: date | None = None,
) -> CollectionsOverviewResponse:
    today = today or date.today()

    # 1. Resolve the matching outlet set via cheap, indexable filters only.
    customer_stmt = (
        select(
            Customer.id, Customer.name, Customer.outlet_code, Customer.territory_id,
            Territory.name.label("territory_name"), Customer.area_id, Area.name.label("area_name"),
        )
        .outerjoin(Territory, Territory.id == Customer.territory_id)
        .outerjoin(Area, Area.id == Customer.area_id)
    )
    if search:
        like = f"%{search.strip()}%"
        customer_stmt = customer_stmt.where(or_(Customer.name.ilike(like), Customer.outlet_code.ilike(like)))
    if territory_id:
        customer_stmt = customer_stmt.where(Customer.territory_id == territory_id)
    if area_id:
        customer_stmt = customer_stmt.where(Customer.area_id == area_id)
    customer_rows = (await session.execute(customer_stmt)).all()

    employee_name_by_id: dict[uuid.UUID, str] = {}
    for eid, name in (await session.execute(select(Employee.id, Employee.full_name))).all():
        employee_name_by_id[eid] = name

    # Employee coverage of an outlet is derived from EmployeeAreaAssignment
    # (brand-agnostic, many-to-many - confirmed against the client's real
    # data that one employee legitimately covers many areas/zones, so this
    # is never assumed to resolve to exactly one employee).
    employees_by_area: dict[uuid.UUID, list[tuple[uuid.UUID, str]]] = defaultdict(list)
    for eid, aid in (await session.execute(
        select(EmployeeAreaAssignment.employee_id, EmployeeAreaAssignment.area_id)
    )).all():
        name = employee_name_by_id.get(eid)
        if name:
            employees_by_area[aid].append((eid, name))

    # Legacy fallback, used ONLY for an outlet that has no Area assigned yet
    # (pre-migration data) - the old single-Zone Employee.territory_id
    # pointer, exactly as it derived "assigned employee" before this
    # hierarchy migration. Once an outlet gets a real Area, this is never
    # consulted for it again.
    employee_by_territory: dict[uuid.UUID, tuple[uuid.UUID, str]] = {}
    for eid, name, t_id in (await session.execute(
        select(Employee.id, Employee.full_name, Employee.territory_id)
    )).all():
        if t_id is not None and t_id not in employee_by_territory:
            employee_by_territory[t_id] = (eid, name)

    # Activity-based employee links (visits and payments captured for each outlet)
    visited_employees_by_customer: dict[uuid.UUID, set[uuid.UUID]] = defaultdict(set)
    for cid, eid in (await session.execute(
        select(Visit.customer_id, Visit.employee_id).where(Visit.customer_id.is_not(None), Visit.employee_id.is_not(None))
    )).all():
        visited_employees_by_customer[cid].add(eid)

    payment_employees_by_customer: dict[uuid.UUID, set[uuid.UUID]] = defaultdict(set)
    for cid, eid in (await session.execute(
        select(Payment.customer_id, Payment.employee_id).where(Payment.customer_id.is_not(None), Payment.employee_id.is_not(None))
    )).all():
        payment_employees_by_customer[cid].add(eid)

    if employee_id:
        def _covers(c) -> bool:
            if employee_id in visited_employees_by_customer.get(c.id, set()):
                return True
            if employee_id in payment_employees_by_customer.get(c.id, set()):
                return True
            if c.area_id is not None:
                return any(eid == employee_id for eid, _ in employees_by_area.get(c.area_id, []))
            legacy = employee_by_territory.get(c.territory_id)
            return legacy is not None and legacy[0] == employee_id
        customer_rows = [r for r in customer_rows if _covers(r)]

    if not customer_rows:
        return _empty_response(skip, limit)

    customer_ids = [r.id for r in customer_rows]

    # 2. Bulk-fetch invoices + payments for exactly this outlet set - a
    # handful of queries total, never one per outlet.
    invoices = (await session.execute(
        select(Invoice).where(Invoice.customer_id.in_(customer_ids))
    )).scalars().all()
    payments = (await session.execute(
        select(Payment).where(Payment.customer_id.in_(customer_ids))
    )).scalars().all()
    verified_payments = [p for p in payments if p.status == PaymentStatus.VERIFIED]

    verified_paid_by_invoice: dict[uuid.UUID, Decimal] = defaultdict(lambda: ZERO)
    for p in verified_payments:
        if p.invoice_id is not None:
            verified_paid_by_invoice[p.invoice_id] += p.amount

    invoices_by_customer: dict[uuid.UUID, list[Invoice]] = defaultdict(list)
    for inv in invoices:
        invoices_by_customer[inv.customer_id].append(inv)

    verified_payments_by_customer: dict[uuid.UUID, list[Payment]] = defaultdict(list)
    for p in verified_payments:
        verified_payments_by_customer[p.customer_id].append(p)

    # 3. Most recent ACTUAL visit (checked in) per outlet - bulk query,
    # reduced in Python exactly like account_service already does for
    # most_recent_payment, just extended across many outlets at once.
    visit_rows = (await session.execute(
        select(Visit.customer_id, Visit.check_in_at, Employee.full_name)
        .join(Employee, Employee.id == Visit.employee_id)
        .where(Visit.customer_id.in_(customer_ids), Visit.check_in_at.is_not(None))
    )).all()
    latest_visit_by_customer: dict[uuid.UUID, tuple] = {}
    for cid, check_in_at, emp_name in visit_rows:
        current = latest_visit_by_customer.get(cid)
        if current is None or check_in_at > current[0]:
            latest_visit_by_customer[cid] = (check_in_at, emp_name)

    # 4. Per-outlet aggregation - each invoice's aging is computed exactly
    # once via the single authoritative aging_service function.
    rows: list[OutletCollectionRow] = []
    bucket_amounts_by_customer: dict[uuid.UUID, dict[MisBucket, Decimal]] = {}
    current_amount_by_customer: dict[uuid.UUID, Decimal] = {}

    for c in customer_rows:
        cust_invoices = invoices_by_customer.get(c.id, [])
        cust_verified_payments = verified_payments_by_customer.get(c.id, [])

        total_invoiced = sum((inv.amount for inv in cust_invoices), ZERO)
        total_paid = sum((p.amount for p in cust_verified_payments), ZERO)
        total_outstanding = max(total_invoiced - total_paid, ZERO)

        agings = [
            compute_invoice_aging(
                invoice_date=inv.invoice_date,
                amount=inv.amount,
                verified_paid_amount=verified_paid_by_invoice.get(inv.id, ZERO),
                today=today,
            )
            for inv in cust_invoices
        ]
        outstanding_agings = [a for a in agings if a.remaining_amount > 0]

        bucket_amounts: dict[MisBucket, Decimal] = defaultdict(lambda: ZERO)
        current_amount = ZERO
        for a in agings:
            bucket_amounts[a.mis_bucket] += a.remaining_amount
            if a.aging_status == AgingStatus.NORMAL:
                current_amount += a.remaining_amount
        bucket_amounts_by_customer[c.id] = bucket_amounts
        current_amount_by_customer[c.id] = current_amount

        # Same precedence as account_service.get_account_summary's
        # collection_status derivation - never a second rule set.
        if any(a.aging_status == AgingStatus.OVERDUE for a in agings):
            worst_status = AgingStatus.OVERDUE
        elif any(a.aging_status == AgingStatus.WARNING for a in agings):
            worst_status = AgingStatus.WARNING
        elif outstanding_agings:
            worst_status = AgingStatus.NORMAL
        else:
            worst_status = AgingStatus.PAID

        overdue_amount = sum((a.remaining_amount for a in agings if a.aging_status == AgingStatus.OVERDUE), ZERO)
        max_days_outstanding = max((a.days_outstanding for a in outstanding_agings), default=0)
        relevant_bucket = compute_mis_bucket(max_days_outstanding) if outstanding_agings else None
        relevant_bucket_amount = bucket_amounts.get(relevant_bucket, ZERO) if relevant_bucket else ZERO

        most_recent_payment = max(
            cust_verified_payments, key=lambda p: (p.payment_date, p.created_at), default=None
        )
        latest_visit = latest_visit_by_customer.get(c.id)

        seen_eids: set[uuid.UUID] = set()
        assigned_employees: list[AssignedEmployeeSummary] = []

        if c.area_id is not None:
            for eid, name in employees_by_area.get(c.area_id, []):
                if eid not in seen_eids:
                    seen_eids.add(eid)
                    assigned_employees.append(AssignedEmployeeSummary(id=eid, name=name))
        else:
            legacy = employee_by_territory.get(c.territory_id)
            if legacy and legacy[0] not in seen_eids:
                seen_eids.add(legacy[0])
                assigned_employees.append(AssignedEmployeeSummary(id=legacy[0], name=legacy[1]))

        # Also include active employees who have conducted visits or recorded collections for this outlet
        active_eids = visited_employees_by_customer.get(c.id, set()) | payment_employees_by_customer.get(c.id, set())
        for eid in sorted(active_eids, key=lambda x: str(x)):
            if eid not in seen_eids:
                name = employee_name_by_id.get(eid)
                if name:
                    seen_eids.add(eid)
                    assigned_employees.append(AssignedEmployeeSummary(id=eid, name=name))

        rows.append(OutletCollectionRow(
            customer_id=c.id,
            outlet_code=c.outlet_code,
            customer_name=c.name,
            territory_id=c.territory_id,
            territory_name=c.territory_name,
            area_id=c.area_id,
            area_name=c.area_name,
            assigned_employees=assigned_employees,
            total_invoiced=total_invoiced,
            total_paid=total_paid,
            total_outstanding=total_outstanding,
            overdue_amount=overdue_amount,
            max_days_outstanding=max_days_outstanding,
            collection_status=worst_status,
            relevant_mis_bucket=relevant_bucket,
            relevant_bucket_amount=relevant_bucket_amount,
            most_recent_payment_date=most_recent_payment.payment_date if most_recent_payment else None,
            most_recent_payment_amount=most_recent_payment.amount if most_recent_payment else None,
            most_recent_payment_employee_name=(
                employee_name_by_id.get(most_recent_payment.employee_id) if most_recent_payment else None
            ),
            most_recent_visit_date=latest_visit[0] if latest_visit else None,
            most_recent_visit_employee_name=latest_visit[1] if latest_visit else None,
        ))

    # 5. Ageing/collection-status filter - derived, so applied post-aggregation.
    if collection_status:
        rows = [r for r in rows if r.collection_status == collection_status]

    # 6. Totals reflect exactly the filtered row set above - never the
    # pre-filter universe, so the summary tiles can't disagree with the table.
    filtered_ids = {r.customer_id for r in rows}
    bucket_totals = {field: ZERO for field in _BUCKET_TOTAL_FIELDS.values()}
    for cid in filtered_ids:
        for bucket, field in _BUCKET_TOTAL_FIELDS.items():
            bucket_totals[field] += bucket_amounts_by_customer.get(cid, {}).get(bucket, ZERO)
    current_total = sum((current_amount_by_customer.get(cid, ZERO) for cid in filtered_ids), ZERO)

    totals = CollectionsOverviewTotals(
        total_outlets=len(rows),
        total_invoiced=sum((r.total_invoiced for r in rows), ZERO),
        total_paid=sum((r.total_paid for r in rows), ZERO),
        total_outstanding=sum((r.total_outstanding for r in rows), ZERO),
        current_amount=current_total,
        **bucket_totals,
    )

    # Default sort: highest outstanding first - serves the client's stated
    # "who owes money, how much" priority directly.
    rows.sort(key=lambda r: r.total_outstanding, reverse=True)
    paginated = rows[skip: skip + limit]

    return CollectionsOverviewResponse(
        totals=totals, outlets=paginated, total_count=len(rows), skip=skip, limit=limit,
    )
