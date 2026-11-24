from __future__ import annotations
import uuid
from decimal import Decimal
from typing import Any, Optional
from sqlalchemy import select, func, case, or_, and_, exists, literal
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.datetime_utils import get_ist_today_range
from app.models.customer import Customer
from app.models.employee import Employee
from app.models.employee_customer_assignment import EmployeeCustomerAssignment
from app.models.field_exception import FieldException, ExceptionStatus
from app.models.payment import Payment, PaymentBrandAllocation
from app.models.user import Role, User
from app.models.visit import Visit, VisitStatus
from app.models.visit_media import MediaType, VisitMedia
from app.schemas.dashboard import (
    DashboardExecutiveKPIs,
    DashboardRecentVisit,
    DashboardSummaryResponse,
    EmployeeDayDashboardResponse,
)
from app.services.report_filters import as_list, as_uuid_list, in_ranges, resolve_snapshot_window, where_ist_window
from app.services.reporting_floor import live_payment_clause, reporting_floor
from app.services import field_exception_service, payment_tally, report_service
from app.services.employee_service import get_employee_by_user_id


async def get_dashboard_summary(
    current_user: User,
    session: AsyncSession,
    brand: Any = None,
    zone_id: Optional[uuid.UUID] = None,
    area_id: Optional[uuid.UUID] = None,
    employee_id: Any = None,
    ageing_bucket: Optional[str] = None,
    month: Any = None,
) -> DashboardSummaryResponse:
    """
    Unified Dashboard aggregation sharing one source of truth with ReportService (collect_bi_entries).

    * brand / month / employee_id take one value or several (OR inside a filter, AND across filters).
    * ageing_bucket restricts EVERY widget to the outlets holding outstanding in that bucket; the money
      figures show only the outstanding in that bucket.
    * Month boundaries are Asia/Kolkata calendar days (timestamps are compared with IST day windows).
    """
    from app.services.report_service import _brand_aliases, _wants_unattributed

    brands = as_list(brand)
    months = as_list(month)
    emp_ids = as_uuid_list(employee_id)
    # None = Current Live Data; one or several months / financial years otherwise.
    window = resolve_snapshot_window(",".join(months) if months else None, None, None)
    has_period = bool(months)
    is_history = bool(has_period and window.start and window.start < reporting_floor())

    # 1. Business BI (single execution) + the outlets of the selected ageing bucket.
    bi_data, bucket_customers = await report_service.ReportService.build_business_bi(
        session=session,
        brand=",".join(brands) if brands else None,
        zone_id=zone_id,
        area_id=area_id,
        employee_id=emp_ids,
        month=",".join(months) if months else None,
        ageing_bucket=ageing_bucket,
    )
    cust_scope = list(bucket_customers) if bucket_customers is not None else None
    no_match = cust_scope is not None and not cust_scope  # ageing bucket selected, nothing in it

    # 2. Employees within the filter scope (WEB-DASH-012)
    emp_stmt = select(func.count(func.distinct(Employee.id)))
    if emp_ids:
        emp_stmt = emp_stmt.where(Employee.id.in_(emp_ids))
    if zone_id:
        emp_stmt = emp_stmt.where(Employee.territory_id == zone_id)
    if area_id or cust_scope is not None:
        emp_stmt = emp_stmt.join(
            EmployeeCustomerAssignment, EmployeeCustomerAssignment.employee_id == Employee.id,
        ).join(Customer, Customer.id == EmployeeCustomerAssignment.customer_id)
        if area_id:
            emp_stmt = emp_stmt.where(Customer.area_id == area_id)
        if cust_scope is not None:
            emp_stmt = emp_stmt.where(Customer.id.in_(cust_scope or [uuid.UUID(int=0)]))
    total_employees = (await session.execute(emp_stmt)).scalar() or 0

    # 3. Visits within the filter scope (period = IST calendar days of the selected month(s))
    visit_q = select(
        func.count(Visit.id).label("total"),
        func.count(Visit.id).filter(Visit.status == VisitStatus.COMPLETED).label("completed"),
        func.count(Visit.id).filter(Visit.status == VisitStatus.PENDING).label("pending"),
        func.count(Visit.id).filter(Visit.status == VisitStatus.IN_PROGRESS).label("in_progress"),
        func.count(Visit.id).filter(Visit.status == VisitStatus.FLAGGED).label("flagged"),
        func.count(Visit.id).filter(Visit.check_in_location.isnot(None)).label("gps_verified"),
    )
    if emp_ids:
        visit_q = visit_q.where(Visit.employee_id.in_(emp_ids))
    if zone_id or area_id:
        visit_q = visit_q.join(Customer, Visit.customer_id == Customer.id)
        if zone_id:
            visit_q = visit_q.where(Customer.territory_id == zone_id)
        if area_id:
            visit_q = visit_q.where(Customer.area_id == area_id)
    if cust_scope is not None:
        visit_q = visit_q.where(Visit.customer_id.in_(cust_scope or [uuid.UUID(int=0)]))
    if has_period:
        visit_q = where_ist_window(visit_q, Visit.scheduled_at, window)
    v_row = (await session.execute(visit_q)).one()

    # 4. Exceptions
    exc_q = select(
        func.count(FieldException.id).label("total"),
        func.count(FieldException.id).filter(FieldException.status == ExceptionStatus.PENDING_REVIEW).label("pending"),
    )
    if emp_ids:
        exc_q = exc_q.where(FieldException.employee_id.in_(emp_ids))
    if cust_scope is not None:
        exc_q = exc_q.where(FieldException.customer_id.in_(cust_scope or [uuid.UUID(int=0)]))
    exc_row = (await session.execute(exc_q)).one()

    # 5. Collections. Money is counted once: receipts in Tally + verified field collections not yet in Tally.
    collected = payment_tally.collected_clause(emp_ids)
    posted = payment_tally.posted_clause_for(emp_ids)

    def _col_scope(q):
        if zone_id or area_id:
            q = q.join(Customer, Payment.customer_id == Customer.id)
            if zone_id:
                q = q.where(Customer.territory_id == zone_id)
            if area_id:
                q = q.where(Customer.area_id == area_id)
        if cust_scope is not None:
            q = q.where(Payment.customer_id.in_(cust_scope or [uuid.UUID(int=0)]))
        if has_period:
            q = q.where(in_ranges(Payment.payment_date, list(window.ranges or [(window.start, window.end)])))
        else:
            # Current Live Data: Tally receipts dated before the reporting floor are HISTORY.
            q = q.where(live_payment_clause(Payment))
        return q

    def _sums(amount_col):
        return (
            func.coalesce(func.sum(case((collected, amount_col), else_=Decimal("0.00"))), Decimal("0.00")),
            func.coalesce(func.sum(case((posted, amount_col), else_=Decimal("0.00"))), Decimal("0.00")),
            func.coalesce(func.sum(case((payment_tally.awaiting_clause(), amount_col), else_=Decimal("0.00"))),
                          Decimal("0.00")),
        )

    col_count = 0
    live_verified_col = live_posted_col = live_awaiting_col = Decimal("0.00")
    queries = []
    if brands:
        aliases = _brand_aliases(brands)
        if aliases:
            queries.append(
                select(func.count(func.distinct(Payment.id)), *_sums(PaymentBrandAllocation.allocated_amount))
                .join(PaymentBrandAllocation, PaymentBrandAllocation.payment_id == Payment.id)
                .where(func.lower(PaymentBrandAllocation.brand).in_(aliases))
            )
        if _wants_unattributed(brands):
            no_alloc = ~exists(select(literal(1)).where(PaymentBrandAllocation.payment_id == Payment.id)
                               .correlate(Payment))
            queries.append(select(func.count(Payment.id), *_sums(Payment.amount)).where(no_alloc))
    else:
        queries.append(select(func.count(Payment.id), *_sums(Payment.amount)))
    for q in queries:
        if emp_ids:
            q = q.where(Payment.employee_id.in_(emp_ids))
        n, v, p_, a = (await session.execute(_col_scope(q))).one()
        col_count += n or 0
        live_verified_col += v or 0
        live_posted_col += p_ or 0
        live_awaiting_col += a or 0

    # 5b. Customer accounts in scope (assignments / visits) - brand-aware so a brand filter never shows all outlets.
    cust_q = select(func.count(func.distinct(Customer.id)))
    if emp_ids:
        cust_q = cust_q.where(or_(
            exists(select(literal(1)).where(EmployeeCustomerAssignment.customer_id == Customer.id,
                                            EmployeeCustomerAssignment.employee_id.in_(emp_ids)).correlate(Customer)),
            exists(select(literal(1)).where(Visit.customer_id == Customer.id,
                                            Visit.employee_id.in_(emp_ids)).correlate(Customer)),
        ))
    if brands:
        from app.models.customer_brand import CustomerBrand
        aliases = _brand_aliases(brands) or []
        parts = []
        if aliases:
            parts.append(exists(select(literal(1)).where(
                CustomerBrand.customer_id == Customer.id, CustomerBrand.is_active.is_(True),
                func.lower(CustomerBrand.brand).in_(aliases)).correlate(Customer)))
        if _wants_unattributed(brands):
            parts.append(~exists(select(literal(1)).where(
                CustomerBrand.customer_id == Customer.id, CustomerBrand.is_active.is_(True)).correlate(Customer)))
        cust_q = cust_q.where(or_(*parts))
    if zone_id:
        cust_q = cust_q.where(Customer.territory_id == zone_id)
    if area_id:
        cust_q = cust_q.where(Customer.area_id == area_id)
    act_outlets_count = (await session.execute(cust_q)).scalar() or 0
    if has_period or cust_scope is not None:
        final_outlets = bi_data.total_outlets
    else:
        final_outlets = max(bi_data.total_outlets, act_outlets_count)

    # One collection figure everywhere: from live Tally invoices the BI already counted each rupee once with
    # the same filters (brand cards add up to it); snapshots keep the period / live split used before.
    if bi_data.data_source == "LIVE_INVOICES":
        final_collection = bi_data.total_collection
        live_posted_col = bi_data.total_collection_posted_in_tally
        live_awaiting_col = bi_data.total_collection_verified_awaiting_tally
    else:
        final_collection = bi_data.total_collection if has_period else live_verified_col

    # 6. Orders (order photos) in scope
    order_q = select(func.count(VisitMedia.id)).where(VisitMedia.media_type == MediaType.ORDER)
    if emp_ids:
        emp_uids = (await session.execute(select(Employee.user_id).where(Employee.id.in_(emp_ids)))).scalars().all()
        order_q = order_q.where(VisitMedia.uploaded_by.in_([u for u in emp_uids if u] or [uuid.UUID(int=0)]))
    if cust_scope is not None or zone_id or area_id:
        order_q = order_q.join(Visit, Visit.id == VisitMedia.visit_id)
        if cust_scope is not None:
            order_q = order_q.where(Visit.customer_id.in_(cust_scope or [uuid.UUID(int=0)]))
        if zone_id or area_id:
            order_q = order_q.join(Customer, Customer.id == Visit.customer_id)
            if zone_id:
                order_q = order_q.where(Customer.territory_id == zone_id)
            if area_id:
                order_q = order_q.where(Customer.area_id == area_id)
    if has_period:
        order_q = where_ist_window(order_q, VisitMedia.uploaded_at, window)
    order_count = (await session.execute(order_q)).scalar_one() or 0

    # 7. Recent exceptions (same FOS / ageing scope)
    if no_match:
        recent_exceptions = []
    else:
        recent_exceptions, _ = await field_exception_service.list_field_exceptions(
            current_user=current_user,
            session=session,
            employee_id=emp_ids[0] if emp_ids and len(emp_ids) == 1 else None,
            limit=5 if not ((emp_ids and len(emp_ids) > 1) or cust_scope is not None) else 100,
        )
        if emp_ids and len(emp_ids) > 1:
            wanted = {str(i) for i in emp_ids}
            recent_exceptions = [e for e in recent_exceptions if str(e.employee_id) in wanted]
        if cust_scope is not None:
            scope = {str(i) for i in cust_scope}
            recent_exceptions = [e for e in recent_exceptions if str(getattr(e, "customer_id", "")) in scope]
        recent_exceptions = recent_exceptions[:5]

    # 7b. Recent field operations: the latest visits in the SAME scope (FOS, zone, area, period, ageing outlets).
    rv_q = (
        select(Visit.id, Visit.customer_id, Customer.name, Employee.full_name, Visit.scheduled_at, Visit.status,
               Visit.check_in_at)
        .join(Customer, Customer.id == Visit.customer_id)
        .join(Employee, Employee.id == Visit.employee_id)
        .order_by(Visit.scheduled_at.desc(), Visit.id.desc())
        .limit(6)
    )
    if emp_ids:
        rv_q = rv_q.where(Visit.employee_id.in_(emp_ids))
    if zone_id:
        rv_q = rv_q.where(Customer.territory_id == zone_id)
    if area_id:
        rv_q = rv_q.where(Customer.area_id == area_id)
    if cust_scope is not None:
        rv_q = rv_q.where(Visit.customer_id.in_(cust_scope or [uuid.UUID(int=0)]))
    if has_period:
        rv_q = where_ist_window(rv_q, Visit.scheduled_at, window)
    recent_visits = [
        DashboardRecentVisit(id=str(r[0]), customer_id=str(r[1]), customer_name=r[2], employee_name=r[3],
                             scheduled_at=r[4], status=r[5].value if hasattr(r[5], "value") else str(r[5]),
                             check_in_at=r[6])
        for r in (await session.execute(rv_q)).all()
    ]

    # 8. 7 Ageing Buckets Distribution
    ageing_distribution = {k: Decimal("0.00") for k in ("<15", "15-30", "30-45", "45-60", "60-75", "75-90", ">90")}
    for b in bi_data.brand_summaries:
        ageing_distribution["<15"] += b.bucket_lt_15
        ageing_distribution["15-30"] += b.bucket_15_30
        ageing_distribution["30-45"] += b.bucket_30_45
        ageing_distribution["45-60"] += b.bucket_45_60
        ageing_distribution["60-75"] += b.bucket_60_75
        ageing_distribution["75-90"] += b.bucket_75_90
        ageing_distribution[">90"] += b.bucket_gt_90

    kpis = DashboardExecutiveKPIs(
        total_outlets=final_outlets,
        total_sales=bi_data.total_sales,
        total_collection=final_collection,
        total_collection_posted_in_tally=live_posted_col,
        total_collection_verified_awaiting_tally=live_awaiting_col,
        total_market_outstanding=bi_data.total_market_outstanding,
        total_overdue_gt_90=bi_data.total_overdue_gt_90,
        total_employees=total_employees,
        total_visits=v_row.total or 0,
        completed_visits=v_row.completed or 0,
        pending_visits=v_row.pending or 0,
        in_progress_visits=v_row.in_progress or 0,
        flagged_visits=v_row.flagged or 0,
        gps_verified_visits=v_row.gps_verified or 0,
        total_exceptions=exc_row.total or 0,
        pending_exceptions=exc_row.pending or 0,
        total_collections_count=col_count,
        total_orders_count=order_count,
    )

    return DashboardSummaryResponse(
        period=",".join(months) if months else "LIVE",
        is_historical=has_period,
        is_history=is_history,
        kpis=kpis,
        brand_breakdown=bi_data.brand_summaries,
        fos_breakdown=bi_data.fos_summaries,
        zone_breakdown=bi_data.zone_summaries,
        area_breakdown=bi_data.area_summaries,
        ageing_distribution=ageing_distribution,
        recent_exceptions=recent_exceptions,
        data_source=bi_data.data_source,
        data_source_note=bi_data.data_source_note,
        as_of_date=bi_data.as_of_date,
        applied_brands=brands or [],
        applied_periods=months or [],
        applied_employee_ids=[str(i) for i in emp_ids or []],
        ageing_bucket=bi_data.ageing_bucket,
        ageing_basis=bi_data.ageing_basis,
        recent_visits=recent_visits,
    )


async def get_employee_day_dashboard(
    current_user: User,
    session: AsyncSession,
) -> EmployeeDayDashboardResponse:
    """
    Mobile / Employee scoped operational "My Day" summary.
    Restricts visits, collections, and orders strictly to IST Today boundaries.
    """
    emp = await get_employee_by_user_id(current_user.id, session)
    start_utc, end_utc = get_ist_today_range()

    # Assigned outlets
    outlets_count = (
        await session.execute(
            select(func.count(EmployeeCustomerAssignment.customer_id)).where(
                EmployeeCustomerAssignment.employee_id == emp.id,
            )
        )
    ).scalar_one() or 0

    # Today's visits in IST (WEB-DASH-005)
    v_q = select(
        func.count(Visit.id).label("total"),
        func.count(Visit.id).filter(Visit.status == VisitStatus.COMPLETED).label("completed"),
        func.count(Visit.id).filter(Visit.status == VisitStatus.PENDING).label("pending"),
        func.count(Visit.id).filter(Visit.status == VisitStatus.IN_PROGRESS).label("in_progress"),
    ).where(
        Visit.employee_id == emp.id,
        Visit.scheduled_at >= start_utc,
        Visit.scheduled_at < end_utc,
    )
    v_row = (await session.execute(v_q)).one()

    # Today's Collections in IST (WEB-DASH-006)
    col_q = select(
        func.count(Payment.id),
        func.coalesce(func.sum(Payment.amount), Decimal("0.00")),
    ).where(
        Payment.employee_id == emp.id,
        Payment.created_at >= start_utc,
        Payment.created_at < end_utc,
    )
    col_count, col_sum = (await session.execute(col_q)).one()

    # Today's Orders in IST (WEB-DASH-006)
    order_q = select(func.count(VisitMedia.id)).where(
        VisitMedia.media_type == MediaType.ORDER,
        VisitMedia.uploaded_by == current_user.id,
        VisitMedia.uploaded_at >= start_utc,
        VisitMedia.uploaded_at < end_utc,
    )
    orders_count = (await session.execute(order_q)).scalar_one() or 0

    return EmployeeDayDashboardResponse(
        employee_id=str(emp.id),
        employee_name=emp.full_name,
        assigned_outlets_count=outlets_count,
        today_visits_count=v_row.total or 0,
        completed_visits_count=v_row.completed or 0,
        pending_visits_count=v_row.pending or 0,
        in_progress_visits_count=v_row.in_progress or 0,
        collections_today_count=col_count or 0,
        collections_today_amount=col_sum or Decimal("0.00"),
        orders_today_count=orders_count or 0,
    )


async def get_history_periods(session: AsyncSession) -> dict:
    """Financial years before the reporting floor that hold Tally invoices or receipts, with their months.
    Read-only; creates nothing (no reporting period, no close workflow)."""
    import calendar
    from datetime import date as _date
    from app.models.invoice import Invoice, InvoiceSource
    from app.models.payment import PaymentSource
    floor = reporting_floor()
    counts: dict[tuple[int, int], list[int]] = {}
    for model, col, src, idx in ((Invoice, Invoice.invoice_date, InvoiceSource.TALLY, 0),
                                 (Payment, Payment.payment_date, PaymentSource.TALLY, 1)):
        rows = (await session.execute(
            select(func.extract("year", col), func.extract("month", col), func.count())
            .where(model.source == src, col < floor)
            .group_by(func.extract("year", col), func.extract("month", col))
        )).all()
        for y, m, n in rows:
            counts.setdefault((int(y), int(m)), [0, 0])[idx] += int(n)
    fys: dict[int, list] = {}
    for (y, m), (ni, npay) in counts.items():
        fys.setdefault(y if m >= 4 else y - 1, []).append((y, m, ni, npay))
    periods = []
    for fy in sorted(fys, reverse=True):
        # Every month of the financial year (April .. March) is offered, also a month without Tally data.
        have = {(y, m): (ni, npay) for y, m, ni, npay in fys[fy]}
        months = [(y, m, *have.get((y, m), (0, 0)))
                  for y, m in [(fy, mm) for mm in range(4, 13)] + [(fy + 1, mm) for mm in range(1, 4)]]
        months = [r for r in months if _date(r[0], r[1], 1) < floor]
        periods.append({
            "value": f"FY{fy}-{str(fy + 1)[2:]}", "label": f"FY {fy}-{str(fy + 1)[2:]}",
            "start": _date(fy, 4, 1).isoformat(), "end": _date(fy + 1, 3, 31).isoformat(),
            "invoices": sum(r[2] for r in months), "payments": sum(r[3] for r in months),
            "months": [{"value": f"{y}-{m:02d}", "label": f"{calendar.month_name[m]} {y}", "invoices": ni, "payments": npay}
                       for y, m, ni, npay in months],
        })
    return {"reporting_floor": floor.isoformat(), "periods": periods}
