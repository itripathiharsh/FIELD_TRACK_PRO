"""
Employee Activity Service: aggregates existing Visit/Payment/VisitMedia data
for one employee into a single admin-facing read (P2-C). No new tables - a
pure read layer over data that already exists, per the P2 instruction not to
duplicate everything into a parallel "activity database".
"""
from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.customer import Customer
from app.models.payment import Payment, PaymentStatus
from app.models.territory import Territory
from app.models.visit import Visit, VisitStatus
from app.repositories.geo_log_repo import GeoLogRepository
from app.repositories.media_repo import MediaRepository
from app.repositories.payment_repo import PaymentRepository
from app.repositories.visit_repo import VisitRepository
from app.schemas.employee_activity import (
    EmployeeActivity,
    EmployeeActivityCollection,
    EmployeeActivityOrder,
    EmployeeActivityVisit,
)
from app.services.employee_service import get_employee

# How many rows to show in each display list - counts/totals below are always
# computed over the FULL underlying data via COUNT/SUM queries, never over
# this capped slice, so a busy employee's summary numbers stay accurate even
# though the detail lists are bounded.
DISPLAY_LIMIT = 100


async def get_employee_activity(employee_id: uuid.UUID, session: AsyncSession) -> EmployeeActivity:
    employee = await get_employee(employee_id, session)  # 404s if missing; eager-loads .user only

    # P2-D: the currently effective territory (an active temporary
    # reassignment wins over the base assignment), not the raw column.
    from app.services.territory_assignment_service import get_effective_territory_id

    effective_territory_id = await get_effective_territory_id(employee.id, session)
    territory_name = None
    if effective_territory_id:
        territory_name = await session.scalar(select(Territory.name).where(Territory.id == effective_territory_id))

    visit_repo = VisitRepository(session)
    visits = sorted(
        await visit_repo.list_filtered(employee_id=employee_id, limit=DISPLAY_LIMIT),
        key=lambda v: v.scheduled_at,
        reverse=True,
    )
    visits_total = await visit_repo.count(Visit.employee_id == employee_id)
    visits_completed = await visit_repo.count(Visit.employee_id == employee_id, Visit.status == VisitStatus.COMPLETED)
    visits_missed = await visit_repo.count(Visit.employee_id == employee_id, Visit.status == VisitStatus.MISSED)
    visits_flagged = await visit_repo.count(Visit.employee_id == employee_id, Visit.status == VisitStatus.FLAGGED)

    geo_repo = GeoLogRepository(session)
    geo_failure_counts = await geo_repo.count_failed_by_visit_ids([v.id for v in visits])

    visit_items = [
        EmployeeActivityVisit(
            id=v.id,
            customer_id=v.customer_id,
            customer_name=v.customer.name,
            outlet_code=v.customer.outlet_code,
            scheduled_at=v.scheduled_at,
            check_in_at=v.check_in_at,
            check_out_at=v.check_out_at,
            duration_minutes=(
                int((v.check_out_at - v.check_in_at).total_seconds() // 60)
                if v.check_in_at and v.check_out_at
                else None
            ),
            status=v.status,
            geo_failure_count=geo_failure_counts.get(v.id, 0),
        )
        for v in visits
    ]

    payment_repo = PaymentRepository(session)
    all_payments = await payment_repo.list_by_employee(employee_id)
    collections_total = len(all_payments)
    collections_pending = sum(1 for p in all_payments if p.status == PaymentStatus.PENDING_VERIFICATION)
    collections_verified = sum(1 for p in all_payments if p.status == PaymentStatus.VERIFIED)
    collections_rejected = sum(1 for p in all_payments if p.status == PaymentStatus.REJECTED)
    verified_amount_row = await session.execute(
        select(func.coalesce(func.sum(Payment.amount), 0)).where(
            Payment.employee_id == employee_id, Payment.status == PaymentStatus.VERIFIED
        )
    )
    collections_verified_amount: Decimal = verified_amount_row.scalar_one()

    display_payments = all_payments[:DISPLAY_LIMIT]
    customer_ids = {p.customer_id for p in display_payments}
    customer_names: dict[uuid.UUID, str] = {}
    if customer_ids:
        rows = await session.execute(select(Customer.id, Customer.name).where(Customer.id.in_(customer_ids)))
        customer_names = dict(rows.all())

    collection_items = [
        EmployeeActivityCollection(
            id=p.id,
            customer_id=p.customer_id,
            customer_name=customer_names.get(p.customer_id),
            amount=p.amount,
            payment_method=p.payment_method,
            payment_date=p.payment_date,
            status=p.status,
        )
        for p in display_payments
    ]

    media_repo = MediaRepository(session)
    orders_total = await media_repo.count_orders_by_employee(employee_id)
    orders = await media_repo.list_orders_by_employee(employee_id, limit=DISPLAY_LIMIT)
    order_items = [
        EmployeeActivityOrder(id=o.id, visit_id=o.visit_id, note=o.note, uploaded_at=o.uploaded_at) for o in orders
    ]

    return EmployeeActivity(
        employee_id=employee.id,
        full_name=employee.full_name,
        employee_code=employee.employee_code,
        territory_id=effective_territory_id,
        territory_name=territory_name,
        is_active=employee.user.is_active,
        visits_total=visits_total,
        visits_completed=visits_completed,
        visits_missed=visits_missed,
        visits_flagged=visits_flagged,
        visits=visit_items,
        collections_total=collections_total,
        collections_pending=collections_pending,
        collections_verified=collections_verified,
        collections_rejected=collections_rejected,
        collections_verified_amount=collections_verified_amount,
        collections=collection_items,
        orders_total=orders_total,
        orders=order_items,
    )
