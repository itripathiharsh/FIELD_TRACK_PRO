import logging
import uuid
from datetime import date, datetime, time, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import cast, Date, func, select, or_, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import get_current_request_id
from app.exceptions.custom import (
    BaseAPIException,
    DuplicateResourceException,
    ResourceNotFoundException,
)
from app.models.customer import Customer
from app.models.customer_location_proposal import (
    CustomerLocationProposal,
    LocationProposalStatus,
)
from app.models.customer_requirement import CustomerRequirement
from app.models.employee import Employee
from app.models.employee_work_session import EmployeeWorkSession, WorkSessionStatus
from app.models.payment import Payment, PaymentStatus
from app.models.user import User
from app.models.visit import Visit, VisitStatus, VisitType
from app.schemas.workday import (
    DailyFieldActivitySummary,
    EmployeeWorkdayResponse,
    EmployeeWorkdaySessionItem,
    RequirementFollowUpItem,
    TodayFieldActivityOverview,
    WorkSessionEndRequest,
    WorkSessionRead,
    WorkSessionStartRequest,
)
from app.services.employee_service import get_employee_by_user_id

logger = logging.getLogger("fieldtrackpro")


async def compute_daily_activity_summary(
    employee_id: uuid.UUID,
    target_date: date,
    session: AsyncSession,
) -> DailyFieldActivitySummary:
    """
    Computes real-time dynamic summary of an employee's field activity for a given date.
    Calculates metrics directly from visits and payments without duplicating data.
    """
    start_dt = datetime.combine(target_date, time.min, tzinfo=timezone.utc)
    end_dt = datetime.combine(target_date, time.max, tzinfo=timezone.utc)

    # 1. Visits metrics for target date (scheduled for target_date OR performed/completed on target_date)
    visit_query = select(
        func.count(Visit.id).label("total"),
        func.count(Visit.id).filter(Visit.visit_type == VisitType.PLANNED).label("planned"),
        func.count(Visit.id).filter(Visit.visit_type == VisitType.AD_HOC).label("adhoc"),
        func.count(Visit.id).filter(Visit.status == VisitStatus.COMPLETED).label("completed"),
        func.count(Visit.id).filter(Visit.status == VisitStatus.MISSED).label("missed"),
        func.count(Visit.id).filter(Visit.status == VisitStatus.FLAGGED).label("flagged"),
    ).where(
        Visit.employee_id == employee_id,
        or_(
            and_(Visit.scheduled_at >= start_dt, Visit.scheduled_at <= end_dt),
            and_(Visit.check_in_at >= start_dt, Visit.check_in_at <= end_dt),
            and_(Visit.check_out_at >= start_dt, Visit.check_out_at <= end_dt),
            and_(Visit.status == VisitStatus.COMPLETED, Visit.updated_at >= start_dt, Visit.updated_at <= end_dt),
        )
    )
    v_res = await session.execute(visit_query)
    v_row = v_res.one()

    # 2. Payments metrics for target date
    payment_query = select(
        func.count(Payment.id).label("cnt"),
        func.coalesce(func.sum(Payment.amount), Decimal(0)).label("total_amt"),
        func.coalesce(
            func.sum(Payment.amount).filter(Payment.status == PaymentStatus.VERIFIED),
            Decimal(0),
        ).label("verified_amt"),
    ).where(
        Payment.employee_id == employee_id,
        Payment.created_at >= start_dt,
        Payment.created_at <= end_dt,
    )
    p_res = await session.execute(payment_query)
    p_row = p_res.one()

    return DailyFieldActivitySummary(
        work_date=target_date,
        total_visits=v_row.total or 0,
        planned_visits=v_row.planned or 0,
        adhoc_visits=v_row.adhoc or 0,
        completed_visits=v_row.completed or 0,
        missed_visits=v_row.missed or 0,
        flagged_visits=v_row.flagged or 0,
        collections_count=p_row.cnt or 0,
        collections_total_amount=Decimal(str(p_row.total_amt or 0)),
        collections_verified_amount=Decimal(str(p_row.verified_amt or 0)),
    )


async def start_workday(
    current_user: User,
    req: WorkSessionStartRequest,
    session: AsyncSession,
) -> EmployeeWorkdayResponse:
    """
    Start employee workday. Captures start GPS coordinates, timestamp, and marks day STARTED.
    Enforces single active work session per date.
    """
    req_id = get_current_request_id()
    employee = await get_employee_by_user_id(current_user.id, session)

    start_time = req.client_timestamp or datetime.now(timezone.utc)
    work_date = start_time.date()

    # Check for existing session on this work_date
    stmt = select(EmployeeWorkSession).where(
        EmployeeWorkSession.employee_id == employee.id,
        EmployeeWorkSession.work_date == work_date,
    )
    res = await session.execute(stmt)
    existing_session = res.scalar_one_or_none()

    if existing_session:
        if existing_session.status == WorkSessionStatus.STARTED:
            logger.warning("event=workday_start result=rejected reason=WORKDAY_ALREADY_STARTED request_id=%s employee_id=%s date=%s", req_id, employee.id, work_date)
            raise BaseAPIException("Workday has already been started for today.", status_code=409, error_code="WORKDAY_ALREADY_STARTED")
        elif existing_session.status == WorkSessionStatus.COMPLETED:
            logger.warning("event=workday_start result=rejected reason=WORKDAY_ALREADY_COMPLETED request_id=%s employee_id=%s date=%s", req_id, employee.id, work_date)
            raise BaseAPIException("Workday has already been completed for today.", status_code=409, error_code="WORKDAY_ALREADY_COMPLETED")

    work_session = EmployeeWorkSession(
        id=uuid.uuid4(),
        employee_id=employee.id,
        work_date=work_date,
        status=WorkSessionStatus.STARTED,
        start_time=start_time,
        start_latitude=req.latitude,
        start_longitude=req.longitude,
        start_accuracy_meters=req.accuracy_meters,
        start_notes=req.notes,
    )
    session.add(work_session)
    await session.commit()
    await session.refresh(work_session)

    summary = await compute_daily_activity_summary(employee.id, work_date, session)

    logger.info(
        "event=workday_start result=success request_id=%s employee_id=%s session_id=%s accuracy_m=%s date=%s",
        req_id,
        employee.id,
        work_session.id,
        req.accuracy_meters,
        work_date,
    )

    return EmployeeWorkdayResponse(
        employee_id=employee.id,
        employee_name=employee.full_name,
        work_date=work_date,
        session=WorkSessionRead.model_validate(work_session),
        summary=summary,
    )


async def end_workday(
    current_user: User,
    req: WorkSessionEndRequest,
    session: AsyncSession,
) -> EmployeeWorkdayResponse:
    """
    End employee workday. Captures end GPS coordinates, timestamp, and marks session COMPLETED.
    """
    req_id = get_current_request_id()
    employee = await get_employee_by_user_id(current_user.id, session)

    end_time = req.client_timestamp or datetime.now(timezone.utc)
    work_date = end_time.date()

    stmt = select(EmployeeWorkSession).where(
        EmployeeWorkSession.employee_id == employee.id,
        EmployeeWorkSession.work_date == work_date,
    )
    res = await session.execute(stmt)
    work_session = res.scalar_one_or_none()

    if not work_session or work_session.status == WorkSessionStatus.NOT_STARTED:
        logger.warning("event=workday_end result=rejected reason=WORKDAY_NOT_STARTED request_id=%s employee_id=%s date=%s", req_id, employee.id, work_date)
        raise BaseAPIException("Cannot end workday before starting it.", status_code=400, error_code="WORKDAY_NOT_STARTED")

    if work_session.status == WorkSessionStatus.COMPLETED:
        logger.warning("event=workday_end result=rejected reason=WORKDAY_ALREADY_COMPLETED request_id=%s employee_id=%s date=%s", req_id, employee.id, work_date)
        raise BaseAPIException("Workday has already been completed for today.", status_code=409, error_code="WORKDAY_ALREADY_COMPLETED")

    work_session.status = WorkSessionStatus.COMPLETED
    work_session.end_time = end_time
    work_session.end_latitude = req.latitude
    work_session.end_longitude = req.longitude
    work_session.end_accuracy_meters = req.accuracy_meters
    work_session.end_notes = req.notes

    await session.commit()
    await session.refresh(work_session)

    summary = await compute_daily_activity_summary(employee.id, work_date, session)

    logger.info(
        "event=workday_end result=success request_id=%s employee_id=%s session_id=%s accuracy_m=%s visits_completed=%s collections_total=%s",
        req_id,
        employee.id,
        work_session.id,
        req.accuracy_meters,
        summary.completed_visits,
        summary.collections_total_amount,
    )

    return EmployeeWorkdayResponse(
        employee_id=employee.id,
        employee_name=employee.full_name,
        work_date=work_date,
        session=WorkSessionRead.model_validate(work_session),
        summary=summary,
    )


async def get_today_workday(
    current_user: User,
    work_date: Optional[date],
    session: AsyncSession,
) -> EmployeeWorkdayResponse:
    """
    Returns current workday status and dynamic daily summary for caller.
    """
    employee = await get_employee_by_user_id(current_user.id, session)
    target_date = work_date or datetime.now(timezone.utc).date()

    stmt = select(EmployeeWorkSession).where(
        EmployeeWorkSession.employee_id == employee.id,
        EmployeeWorkSession.work_date == target_date,
    )
    res = await session.execute(stmt)
    work_session = res.scalar_one_or_none()

    summary = await compute_daily_activity_summary(employee.id, target_date, session)

    return EmployeeWorkdayResponse(
        employee_id=employee.id,
        employee_name=employee.full_name,
        work_date=target_date,
        session=WorkSessionRead.model_validate(work_session) if work_session else None,
        summary=summary,
    )


async def get_employee_workday_by_admin(
    employee_id: uuid.UUID,
    work_date: Optional[date],
    session: AsyncSession,
) -> EmployeeWorkdayResponse:
    """
    Admin lookup of an employee's workday session and daily summary by date.
    """
    emp_stmt = select(Employee).where(Employee.id == employee_id)
    emp_res = await session.execute(emp_stmt)
    employee = emp_res.scalar_one_or_none()
    if not employee:
        raise ResourceNotFoundException(f"Employee {employee_id} not found")

    target_date = work_date or datetime.now(timezone.utc).date()

    stmt = select(EmployeeWorkSession).where(
        EmployeeWorkSession.employee_id == employee.id,
        EmployeeWorkSession.work_date == target_date,
    )
    res = await session.execute(stmt)
    work_session = res.scalar_one_or_none()

    summary = await compute_daily_activity_summary(employee.id, target_date, session)

    return EmployeeWorkdayResponse(
        employee_id=employee.id,
        employee_name=employee.full_name,
        work_date=target_date,
        session=WorkSessionRead.model_validate(work_session) if work_session else None,
        summary=summary,
    )


async def get_today_field_overview(
    work_date: Optional[date],
    session: AsyncSession,
) -> TodayFieldActivityOverview:
    """
    Aggregates organization-wide field activity for today's admin overview.
    """
    target_date = work_date or datetime.now(timezone.utc).date()
    start_dt = datetime.combine(target_date, time.min, tzinfo=timezone.utc)
    end_dt = datetime.combine(target_date, time.max, tzinfo=timezone.utc)

    # 1. All active employees
    emp_stmt = select(Employee).order_by(Employee.full_name)
    emp_res = await session.execute(emp_stmt)
    all_employees = emp_res.scalars().all()
    total_employees = len(all_employees)

    # 2. Work sessions for target date
    sess_stmt = (
        select(EmployeeWorkSession)
        .where(EmployeeWorkSession.work_date == target_date)
    )
    sess_res = await session.execute(sess_stmt)
    sess_by_emp_id = {ws.employee_id: ws for ws in sess_res.scalars().all()}

    employees_started = sum(1 for ws in sess_by_emp_id.values() if ws.status == WorkSessionStatus.STARTED)
    employees_completed = sum(1 for ws in sess_by_emp_id.values() if ws.status == WorkSessionStatus.COMPLETED)
    employees_active = employees_started
    employees_not_started = max(0, total_employees - (employees_started + employees_completed))

    # 3. Overall Visits metrics
    v_stmt = select(
        func.count(Visit.id).label("total"),
        func.count(Visit.id).filter(Visit.visit_type == VisitType.PLANNED).label("planned"),
        func.count(Visit.id).filter(Visit.visit_type == VisitType.AD_HOC).label("adhoc"),
        func.count(Visit.id).filter(Visit.status == VisitStatus.COMPLETED).label("completed"),
    ).where(
        or_(
            and_(Visit.scheduled_at >= start_dt, Visit.scheduled_at <= end_dt),
            and_(Visit.check_in_at >= start_dt, Visit.check_in_at <= end_dt),
            and_(Visit.check_out_at >= start_dt, Visit.check_out_at <= end_dt),
            and_(Visit.status == VisitStatus.COMPLETED, Visit.updated_at >= start_dt, Visit.updated_at <= end_dt),
        )
    )
    v_res = await session.execute(v_stmt)
    v_row = v_res.one()

    # 4. Overall Collections Breakdown
    p_stmt = select(
        func.coalesce(func.sum(Payment.amount), Decimal(0)).label("total_amt"),
        func.coalesce(
            func.sum(Payment.amount).filter(Payment.status == PaymentStatus.PENDING_VERIFICATION),
            Decimal(0),
        ).label("pending_amt"),
        func.coalesce(
            func.sum(Payment.amount).filter(Payment.status == PaymentStatus.VERIFIED),
            Decimal(0),
        ).label("verified_amt"),
    ).where(
        Payment.created_at >= start_dt,
        Payment.created_at <= end_dt,
    )
    p_res = await session.execute(p_stmt)
    p_row = p_res.one()

    # 5. Attention Counters
    loc_prop_stmt = select(func.count(CustomerLocationProposal.id)).where(
        CustomerLocationProposal.status == LocationProposalStatus.PENDING
    )
    pending_loc_count = (await session.execute(loc_prop_stmt)).scalar_one() or 0

    pending_pay_stmt = select(func.count(Payment.id)).where(
        Payment.status == PaymentStatus.PENDING_VERIFICATION
    )
    pending_pay_count = (await session.execute(pending_pay_stmt)).scalar_one() or 0

    recent_prospect_stmt = select(func.count(Customer.id)).where(
        Customer.location_status == "PENDING_APPROVAL"
    )
    recent_prospects_count = (await session.execute(recent_prospect_stmt)).scalar_one() or 0

    # 6. Upcoming Requirements / Follow-ups
    req_stmt = (
        select(CustomerRequirement, Customer.name)
        .join(Customer, Customer.id == CustomerRequirement.customer_id)
        .where(CustomerRequirement.follow_up_date >= target_date)
        .order_by(CustomerRequirement.follow_up_date.asc())
        .limit(5)
    )
    req_res = await session.execute(req_stmt)
    upcoming_follow_ups = [
        RequirementFollowUpItem(
            id=cr.id,
            customer_id=cr.customer_id,
            customer_name=c_name,
            brand=cr.brand,
            product_details=cr.product_details,
            expected_value=cr.expected_value,
            follow_up_date=cr.follow_up_date,
        )
        for cr, c_name in req_res.all()
    ]

    # 7. Session items for all active employees
    session_items: list[EmployeeWorkdaySessionItem] = []
    for emp in all_employees:
        ws = sess_by_emp_id.get(emp.id)
        emp_summary = await compute_daily_activity_summary(emp.id, target_date, session)
        session_items.append(
            EmployeeWorkdaySessionItem(
                employee_id=emp.id,
                employee_name=emp.full_name,
                employee_code=emp.employee_code,
                work_date=target_date,
                status=ws.status if ws else WorkSessionStatus.NOT_STARTED,
                start_time=ws.start_time if ws else None,
                end_time=ws.end_time if ws else None,
                start_latitude=ws.start_latitude if ws else None,
                start_longitude=ws.start_longitude if ws else None,
                start_accuracy_meters=ws.start_accuracy_meters if ws else None,
                end_latitude=ws.end_latitude if ws else None,
                end_longitude=ws.end_longitude if ws else None,
                end_accuracy_meters=ws.end_accuracy_meters if ws else None,
                visits_total=emp_summary.total_visits,
                visits_planned=emp_summary.planned_visits,
                visits_adhoc=emp_summary.adhoc_visits,
                visits_completed=emp_summary.completed_visits,
                collections_amount=emp_summary.collections_total_amount,
            )
        )

    # Sort session items: Active first, then Completed, then Not Started
    def session_sort_key(item: EmployeeWorkdaySessionItem) -> int:
        if item.status == WorkSessionStatus.STARTED:
            return 0
        if item.status == WorkSessionStatus.COMPLETED:
            return 1
        return 2

    session_items.sort(key=session_sort_key)

    return TodayFieldActivityOverview(
        work_date=target_date,
        total_employees=total_employees,
        employees_started=employees_started + employees_completed,
        employees_completed=employees_completed,
        employees_active=employees_active,
        employees_not_started=employees_not_started,
        total_visits=v_row.total or 0,
        planned_visits=v_row.planned or 0,
        adhoc_visits=v_row.adhoc or 0,
        completed_visits=v_row.completed or 0,
        total_collections_amount=Decimal(str(p_row.total_amt or 0)),
        collections_pending_verification=Decimal(str(p_row.pending_amt or 0)),
        collections_verified=Decimal(str(p_row.verified_amt or 0)),
        pending_location_proposals_count=pending_loc_count,
        pending_payments_count=pending_pay_count,
        recent_prospects_count=recent_prospects_count,
        upcoming_follow_ups=upcoming_follow_ups,
        sessions=session_items,
    )
