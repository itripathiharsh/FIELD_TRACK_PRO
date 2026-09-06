"""
Visit analytics service — Planned vs Actual matching and metrics.

Matching strategy (deterministic, query-time):
  A planned visit is matched to an actual visit when:
    - Same employee_id
    - Same customer_id
    - Actual visit scheduled_at falls on the same calendar date as planned_date
    - Actual visit status IN (COMPLETED, IN_PROGRESS)
  This match is computed at query time, NOT stored as a FK.

Metric definitions:
  - total_planned: Count of planned visits with status IN (PLANNED, COMPLETED, MISSED)
  - completed: Planned visits with a matching completed/in-progress actual visit
  - missed: Planned visits where planned_date < today AND no matching actual visit
  - cancelled: Planned visits with status = CANCELLED (excluded from active counts)
  - extra_unplanned: Actual visits for the employee+month with NO matching planned visit
  - completion_rate: completed / total_planned * 100 (None if total_planned = 0)
  - behind_schedule: total_planned > 0 AND completed < count(planned where date <= today)
"""
from __future__ import annotations

import logging
import uuid
from collections import defaultdict
from datetime import date, timedelta
from typing import Optional

from sqlalchemy import Date, and_, case, cast, distinct, exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.datetime_utils import get_ist_now
from app.exceptions.custom import ForbiddenException, ValidationException
from app.models.employee import Employee
from app.models.monthly_visit_plan import (
    MonthlyVisitPlan,
    PlannedVisit,
    PlannedVisitStatus,
)
from app.models.user import Role, User
from app.models.visit import Visit, VisitStatus, VisitType
from app.schemas.visit_analytics import (
    DailyAnalytics,
    EmployeeMonthlyAnalytics,
    TeamMonthlyAnalytics,
)
from app.services.employee_service import get_employee, get_employee_by_user_id

logger = logging.getLogger("fieldtrackpro")

# Actual visit statuses that count as "executed" against a planned visit
_EXECUTED_STATUSES = (VisitStatus.COMPLETED, VisitStatus.IN_PROGRESS)

# Planned visit statuses that count as "active" (not cancelled)
_ACTIVE_PLANNED = (PlannedVisitStatus.PLANNED, PlannedVisitStatus.COMPLETED, PlannedVisitStatus.MISSED)


def _month_date_range(year: int, month: int) -> tuple[date, date]:
    """Return (first_day, last_day) for a calendar month."""
    first = date(year, month, 1)
    if month == 12:
        last = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        last = date(year, month + 1, 1) - timedelta(days=1)
    return first, last


async def get_employee_monthly_analytics(
    employee_id: uuid.UUID,
    year: int,
    month: int,
    session: AsyncSession,
) -> EmployeeMonthlyAnalytics:
    """Compute planned vs actual analytics for a single employee/month."""
    employee = await get_employee(employee_id, session)
    first_day, last_day = _month_date_range(year, month)
    today = get_ist_now().date()

    # ── 1. Planned visits for this employee/month ──
    planned_stmt = (
        select(PlannedVisit)
        .join(MonthlyVisitPlan, PlannedVisit.monthly_plan_id == MonthlyVisitPlan.id)
        .where(
            PlannedVisit.employee_id == employee_id,
            MonthlyVisitPlan.year == year,
            MonthlyVisitPlan.month == month,
        )
    )
    planned_result = await session.execute(planned_stmt)
    planned_visits = planned_result.scalars().all()

    # Separate by status
    active_planned = [pv for pv in planned_visits if pv.status in _ACTIVE_PLANNED]
    cancelled = [pv for pv in planned_visits if pv.status == PlannedVisitStatus.CANCELLED]

    # ── 2. Actual visits for this employee in the month's date range ──
    # Convert date range to UTC timestamps for scheduled_at comparison.
    # Use IST (UTC+5:30) boundaries for date matching.
    from datetime import datetime, timezone

    # Build a set of actual visits for the month
    # We match on calendar date (IST), so we need the full month range
    ist_month_start = datetime(year, month, 1, 0, 0, 0, tzinfo=timezone(timedelta(hours=5, minutes=30)))
    if month == 12:
        ist_month_end = datetime(year + 1, 1, 1, 0, 0, 0, tzinfo=timezone(timedelta(hours=5, minutes=30)))
    else:
        ist_month_end = datetime(year, month + 1, 1, 0, 0, 0, tzinfo=timezone(timedelta(hours=5, minutes=30)))

    actual_stmt = (
        select(Visit)
        .where(
            Visit.employee_id == employee_id,
            Visit.scheduled_at >= ist_month_start.astimezone(timezone.utc),
            Visit.scheduled_at < ist_month_end.astimezone(timezone.utc),
        )
    )
    actual_result = await session.execute(actual_stmt)
    actual_visits = actual_result.scalars().all()

    # ── 3. Matching logic ──
    # Build a lookup: (customer_id, calendar_date) -> list of actual visits
    from collections import defaultdict
    actual_by_key: dict[tuple[uuid.UUID, date], list[Visit]] = defaultdict(list)
    ist_offset = timedelta(hours=5, minutes=30)
    for av in actual_visits:
        # Convert scheduled_at to IST date for matching
        scheduled_utc = av.scheduled_at
        if scheduled_utc.tzinfo is None:
            scheduled_utc = scheduled_utc.replace(tzinfo=timezone.utc)
        ist_dt = scheduled_utc.astimezone(timezone(ist_offset))
        cal_date = ist_dt.date()
        actual_by_key[(av.customer_id, cal_date)].append(av)

    # Count completed planned visits
    completed_count = 0
    missed_count = 0
    matched_actual_ids: set[uuid.UUID] = set()

    for pv in active_planned:
        key = (pv.customer_id, pv.planned_date)
        matching_actuals = actual_by_key.get(key, [])
        # A planned visit is completed if ANY matching actual is in an executed status
        executed_matches = [a for a in matching_actuals if a.status in _EXECUTED_STATUSES]
        if executed_matches:
            completed_count += 1
            # Track matched actual visit IDs to exclude from "extra" count
            for em in executed_matches:
                matched_actual_ids.add(em.id)
        elif pv.planned_date < today:
            # Past date with no execution → missed
            missed_count += 1
        # Future planned visits that haven't been executed yet are just "planned" — not missed

    # ── 4. Extra/unplanned visits ──
    # Actual visits not matched to any planned visit
    # Build a set of (customer_id, date) keys from active planned visits
    planned_keys = {(pv.customer_id, pv.planned_date) for pv in active_planned}
    extra_count = 0
    for av in actual_visits:
        scheduled_utc = av.scheduled_at
        if scheduled_utc.tzinfo is None:
            scheduled_utc = scheduled_utc.replace(tzinfo=timezone.utc)
        ist_dt = scheduled_utc.astimezone(timezone(ist_offset))
        cal_date = ist_dt.date()
        key = (av.customer_id, cal_date)
        if key not in planned_keys:
            extra_count += 1

    # ── 5. Compute metrics ──
    total_planned = len(active_planned)
    active_planned_days = len({pv.planned_date for pv in active_planned})

    # Execution days: distinct calendar dates with at least one actual visit
    execution_dates: set[date] = set()
    for av in actual_visits:
        scheduled_utc = av.scheduled_at
        if scheduled_utc.tzinfo is None:
            scheduled_utc = scheduled_utc.replace(tzinfo=timezone.utc)
        ist_dt = scheduled_utc.astimezone(timezone(ist_offset))
        execution_dates.add(ist_dt.date())
    active_execution_days = len(execution_dates)

    completion_rate = round((completed_count / total_planned) * 100, 1) if total_planned > 0 else None

    avg_planned = round(total_planned / active_planned_days, 1) if active_planned_days > 0 else None
    avg_completed = round(
        len([a for a in actual_visits if a.status in _EXECUTED_STATUSES]) / active_execution_days, 1
    ) if active_execution_days > 0 else None

    # Behind schedule: has due planned visits AND completed < due
    due_planned = len([pv for pv in active_planned if pv.planned_date <= today])
    behind = total_planned > 0 and completed_count < due_planned

    return EmployeeMonthlyAnalytics(
        employee_id=employee_id,
        employee_name=employee.full_name,
        employee_code=employee.employee_code,
        year=year,
        month=month,
        total_planned=total_planned,
        completed=completed_count,
        missed=missed_count,
        cancelled=len(cancelled),
        extra_unplanned=extra_count,
        completion_rate=completion_rate,
        active_planned_days=active_planned_days,
        active_execution_days=active_execution_days,
        avg_planned_per_active_day=avg_planned,
        avg_completed_per_execution_day=avg_completed,
        behind_schedule=behind,
    )


async def get_team_monthly_analytics(
    year: int,
    month: int,
    session: AsyncSession,
    employee_id: Optional[uuid.UUID] = None,
) -> TeamMonthlyAnalytics:
    """Compute team-wide analytics for all employees (or a single employee) for a month."""
    if employee_id:
        emp_analytics = await get_employee_monthly_analytics(employee_id, year, month, session)
        return TeamMonthlyAnalytics(
            year=year,
            month=month,
            employees=[emp_analytics],
            team_total_planned=emp_analytics.total_planned,
            team_completed=emp_analytics.completed,
            team_missed=emp_analytics.missed,
            team_cancelled=emp_analytics.cancelled,
            team_extra=emp_analytics.extra_unplanned,
            team_completion_rate=emp_analytics.completion_rate,
        )

    # Fetch employees that have at least one planned visit OR actual visit in the month
    first_day, last_day = _month_date_range(year, month)
    from datetime import datetime, timezone

    ist_offset = timedelta(hours=5, minutes=30)
    ist_month_start = datetime(year, month, 1, 0, 0, 0, tzinfo=timezone(ist_offset))
    if month == 12:
        ist_month_end = datetime(year + 1, 1, 1, 0, 0, 0, tzinfo=timezone(ist_offset))
    else:
        ist_month_end = datetime(year, month + 1, 1, 0, 0, 0, tzinfo=timezone(ist_offset))

    # 1. Bulk fetch all planned visits for the month
    planned_stmt = (
        select(PlannedVisit)
        .join(MonthlyVisitPlan, PlannedVisit.monthly_plan_id == MonthlyVisitPlan.id)
        .where(
            MonthlyVisitPlan.year == year,
            MonthlyVisitPlan.month == month,
        )
    )
    p_res = await session.execute(planned_stmt)
    all_planned = p_res.scalars().all()

    # 2. Bulk fetch all actual visits for the month
    actual_stmt = (
        select(Visit)
        .where(
            Visit.scheduled_at >= ist_month_start.astimezone(timezone.utc),
            Visit.scheduled_at < ist_month_end.astimezone(timezone.utc),
        )
    )
    a_res = await session.execute(actual_stmt)
    all_actual = a_res.scalars().all()

    from collections import defaultdict
    planned_by_emp: dict[uuid.UUID, list[PlannedVisit]] = defaultdict(list)
    for pv in all_planned:
        planned_by_emp[pv.employee_id].append(pv)

    actual_by_emp: dict[uuid.UUID, list[Visit]] = defaultdict(list)
    for av in all_actual:
        actual_by_emp[av.employee_id].append(av)

    all_emp_ids = set(planned_by_emp.keys()) | set(actual_by_emp.keys())
    if not all_emp_ids:
        return TeamMonthlyAnalytics(
            year=year,
            month=month,
            employees=[],
            team_total_planned=0,
            team_completed=0,
            team_missed=0,
            team_cancelled=0,
            team_extra=0,
            team_completion_rate=None,
        )

    # 3. Bulk fetch employees
    emp_stmt = select(Employee).where(Employee.id.in_(all_emp_ids))
    e_res = await session.execute(emp_stmt)
    employees_map = {e.id: e for e in e_res.scalars().all()}

    today_ist = (datetime.now(timezone.utc) + ist_offset).date()

    employees_analytics: list[EmployeeMonthlyAnalytics] = []
    for eid in all_emp_ids:
        emp = employees_map.get(eid)
        if not emp:
            continue

        pv_list = planned_by_emp[eid]
        av_list = actual_by_emp[eid]

        active_planned = [p for p in pv_list if p.status != PlannedVisitStatus.CANCELLED]
        total_planned = len(active_planned)
        cancelled_count = len(pv_list) - total_planned
        active_planned_days = len({p.planned_date for p in active_planned})

        actual_by_cust_date = set()
        execution_dates = set()
        for a in av_list:
            scheduled_utc = a.scheduled_at
            if scheduled_utc.tzinfo is None:
                scheduled_utc = scheduled_utc.replace(tzinfo=timezone.utc)
            a_ist = scheduled_utc.astimezone(timezone(ist_offset)).date()
            execution_dates.add(a_ist)
            if a.status in _EXECUTED_STATUSES:
                actual_by_cust_date.add((a.customer_id, a_ist))

        active_execution_days = len(execution_dates)
        completed_count = sum(1 for p in active_planned if (p.customer_id, p.planned_date) in actual_by_cust_date)
        missed_count = sum(1 for p in active_planned if p.planned_date < today_ist and (p.customer_id, p.planned_date) not in actual_by_cust_date)

        planned_keys = {(p.customer_id, p.planned_date) for p in active_planned}
        extra_count = sum(1 for a in av_list if a.status in _EXECUTED_STATUSES and (a.customer_id, a.scheduled_at.astimezone(timezone(ist_offset)).date()) not in planned_keys)

        rate = round((completed_count / total_planned) * 100.0, 1) if total_planned > 0 else None
        avg_planned = round(total_planned / active_planned_days, 1) if active_planned_days > 0 else None
        executed_visits = [a for a in av_list if a.status in _EXECUTED_STATUSES]
        avg_completed = round(len(executed_visits) / active_execution_days, 1) if active_execution_days > 0 else None

        due_planned = len([p for p in active_planned if p.planned_date <= today_ist])
        behind = total_planned > 0 and completed_count < due_planned

        employees_analytics.append(
            EmployeeMonthlyAnalytics(
                employee_id=emp.id,
                employee_name=emp.full_name,
                employee_code=emp.employee_code,
                year=year,
                month=month,
                total_planned=total_planned,
                completed=completed_count,
                missed=missed_count,
                cancelled=cancelled_count,
                extra_unplanned=extra_count,
                completion_rate=rate,
                active_planned_days=active_planned_days,
                active_execution_days=active_execution_days,
                avg_planned_per_active_day=avg_planned,
                avg_completed_per_execution_day=avg_completed,
                behind_schedule=behind,
            )
        )

    # Sort by employee name
    employees_analytics.sort(key=lambda e: e.employee_name)

    team_planned = sum(e.total_planned for e in employees_analytics)
    team_completed = sum(e.completed for e in employees_analytics)
    team_missed = sum(e.missed for e in employees_analytics)
    team_cancelled = sum(e.cancelled for e in employees_analytics)
    team_extra = sum(e.extra_unplanned for e in employees_analytics)
    team_rate = round((team_completed / team_planned) * 100, 1) if team_planned > 0 else None

    return TeamMonthlyAnalytics(
        year=year,
        month=month,
        employees=employees_analytics,
        team_total_planned=team_planned,
        team_completed=team_completed,
        team_missed=team_missed,
        team_cancelled=team_cancelled,
        team_extra=team_extra,
        team_completion_rate=team_rate,
    )


async def get_daily_analytics(
    employee_id: uuid.UUID,
    target_date: date,
    session: AsyncSession,
) -> DailyAnalytics:
    """Compute planned vs actual metrics for a specific employee+date."""
    employee = await get_employee(employee_id, session)
    today = get_ist_now().date()

    # Planned visits for this employee on this date
    planned_stmt = (
        select(PlannedVisit)
        .join(MonthlyVisitPlan, PlannedVisit.monthly_plan_id == MonthlyVisitPlan.id)
        .where(
            PlannedVisit.employee_id == employee_id,
            PlannedVisit.planned_date == target_date,
            PlannedVisit.status.in_([s.value for s in _ACTIVE_PLANNED]),
        )
    )
    planned_result = await session.execute(planned_stmt)
    planned_visits = planned_result.scalars().all()

    # Actual visits for this employee on this date
    from datetime import datetime, timezone
    ist_offset = timedelta(hours=5, minutes=30)
    ist_start = datetime(target_date.year, target_date.month, target_date.day, 0, 0, 0, tzinfo=timezone(ist_offset))
    ist_end = ist_start + timedelta(days=1)

    actual_stmt = (
        select(Visit)
        .where(
            Visit.employee_id == employee_id,
            Visit.scheduled_at >= ist_start.astimezone(timezone.utc),
            Visit.scheduled_at < ist_end.astimezone(timezone.utc),
        )
    )
    actual_result = await session.execute(actual_stmt)
    actual_visits = actual_result.scalars().all()

    # Match
    actual_by_customer: dict[uuid.UUID, list[Visit]] = defaultdict(list)
    for av in actual_visits:
        actual_by_customer[av.customer_id].append(av)

    completed = 0
    missed = 0
    planned_customer_ids: set[uuid.UUID] = set()

    for pv in planned_visits:
        planned_customer_ids.add(pv.customer_id)
        matches = actual_by_customer.get(pv.customer_id, [])
        executed = [a for a in matches if a.status in _EXECUTED_STATUSES]
        if executed:
            completed += 1
        elif target_date < today:
            missed += 1

    extra = sum(1 for av in actual_visits if av.customer_id not in planned_customer_ids)

    return DailyAnalytics(
        date=target_date,
        employee_id=employee_id,
        employee_name=employee.full_name,
        planned=len(planned_visits),
        completed=completed,
        missed=missed,
        extra_unplanned=extra,
    )


async def sweep_missed_planned_visits(session: AsyncSession) -> int:
    """
    Query past planned visits (planned_date < today in IST) that are still PLANNED.
    If no executed actual visit exists on that date, mark them as MISSED and dispatch
    duplicate-protected notifications to the employee and admins.

    Returns the count of missed planned visits processed.
    """
    today = get_ist_now().date()
    from datetime import datetime, timezone
    from sqlalchemy.orm import selectinload
    from app.models.notification import Notification, NotificationType

    # Look at rolling 60-day window
    window_start = today - timedelta(days=60)

    stmt = (
        select(PlannedVisit)
        .options(
            selectinload(PlannedVisit.customer),
            selectinload(PlannedVisit.employee),
        )
        .where(
            PlannedVisit.planned_date < today,
            PlannedVisit.planned_date >= window_start,
            PlannedVisit.status == PlannedVisitStatus.PLANNED,
        )
    )
    candidate_visits = (await session.execute(stmt)).scalars().all()
    if not candidate_visits:
        return 0

    ist_offset = timedelta(hours=5, minutes=30)
    # Query ALL eligible active admins — no artificial LIMIT
    admin_stmt = (
        select(User.id)
        .where(User.role == Role.ADMIN, User.is_active == True)
    )
    admin_ids = (await session.execute(admin_stmt)).scalars().all()

    missed_count = 0
    pv_ids_to_check: list[uuid.UUID] = []

    for pv in candidate_visits:
        cal_date = pv.planned_date
        ist_start = datetime(cal_date.year, cal_date.month, cal_date.day, 0, 0, 0, tzinfo=timezone(ist_offset))
        ist_end = ist_start + timedelta(days=1)

        actual_stmt = select(Visit.id).where(
            Visit.employee_id == pv.employee_id,
            Visit.customer_id == pv.customer_id,
            Visit.scheduled_at >= ist_start.astimezone(timezone.utc),
            Visit.scheduled_at < ist_end.astimezone(timezone.utc),
            Visit.status.in_(_EXECUTED_STATUSES),
        ).limit(1)
        actual_match = (await session.execute(actual_stmt)).scalar_one_or_none()

        if actual_match is None:
            pv.status = PlannedVisitStatus.MISSED
            missed_count += 1
            pv_ids_to_check.append(pv.id)

    if not pv_ids_to_check:
        await session.commit()
        return 0

    # Query existing missed notifications in ONE query for duplicate prevention
    existing_stmt = select(Notification.user_id, Notification.planned_visit_id).where(
        Notification.planned_visit_id.in_(pv_ids_to_check),
        Notification.type == NotificationType.PLANNED_VISIT_MISSED,
    )
    existing_pairs = set((await session.execute(existing_stmt)).all())

    notifications_to_add: list[Notification] = []

    for pv in candidate_visits:
        if pv.status != PlannedVisitStatus.MISSED:
            continue

        cust_name = pv.customer.name if pv.customer else "Customer"
        outlet_code = f" ({pv.customer.outlet_code})" if pv.customer and pv.customer.outlet_code else ""
        date_str = pv.planned_date.strftime("%d %b %Y")
        emp_name = pv.employee.full_name if pv.employee else "Employee"

        # 1. Notify employee
        if pv.employee and pv.employee.user_id:
            pair = (pv.employee.user_id, pv.id)
            if pair not in existing_pairs:
                emp_msg = f"Planned visit for {cust_name}{outlet_code} on {date_str} was missed."
                notifications_to_add.append(
                    Notification(
                        user_id=pv.employee.user_id,
                        type=NotificationType.PLANNED_VISIT_MISSED,
                        title="Planned Visit Missed",
                        message=emp_msg,
                        planned_visit_id=pv.id,
                    )
                )
                existing_pairs.add(pair)

        # 2. Notify all eligible active admins
        admin_msg = f"{emp_name} missed a planned visit for {cust_name}{outlet_code} scheduled on {date_str}."
        for a_id in admin_ids:
            pair = (a_id, pv.id)
            if pair not in existing_pairs:
                notifications_to_add.append(
                    Notification(
                        user_id=a_id,
                        type=NotificationType.PLANNED_VISIT_MISSED,
                        title="Planned Visit Missed",
                        message=admin_msg,
                        planned_visit_id=pv.id,
                    )
                )
                existing_pairs.add(pair)

    if notifications_to_add:
        session.add_all(notifications_to_add)

    await session.commit()
    logger.info("sweep_missed_planned_visits processed %s missed visits, %s notifications created", missed_count, len(notifications_to_add))
    return missed_count


