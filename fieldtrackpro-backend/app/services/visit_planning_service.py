from __future__ import annotations

import logging
import uuid
from datetime import date
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.context import get_current_request_id
from app.exceptions.custom import (
    BaseAPIException,
    ForbiddenException,
    ResourceNotFoundException,
    ValidationException,
)
from app.models.customer import Customer
from app.models.employee import Employee
from app.models.monthly_visit_plan import (
    MonthlyPlanStatus,
    MonthlyVisitPlan,
    PlannedVisit,
    PlannedVisitStatus,
)
from app.models.notification import NotificationType
from app.models.user import Role, User
from app.models.visit import VisitType
from app.services.notification_service import notification_service
from app.schemas.visit_planning import (
    MonthlyPlanSummaryRead,
    MonthlyVisitPlanRead,
    PlannedVisitCreate,
    PlannedVisitRead,
    PlannedVisitUpdate,
    TeamMonthlyPlanRead,
)
from app.services.customer_service import get_customer
from app.services.employee_service import get_employee, get_employee_by_user_id

logger = logging.getLogger("fieldtrackpro")


async def _notify_admins_of_employee_change(
    notification_type: NotificationType,
    title: str,
    message: str,
    planned_visit_id: uuid.UUID,
    session: AsyncSession,
    exclude_user_id: uuid.UUID | None = None,
) -> None:
    """
    Dispatch duplicate-safe DB notifications to ALL eligible active Admins when an
    employee changes their planned schedule.

    Architecture — O(4) DB operations, regardless of admin count:
      1. ONE query to retrieve all eligible active Admin IDs (no LIMIT).
      2. ONE bulk duplicate-check + session.add_all via create_planning_notifications_bulk.
         No per-row commits — the caller's transaction commit handles persistence.
      3. ONE bulk query to retrieve device tokens for all notified admins at once.
      4. ONE asyncio background task fires send_multicast with all tokens — no new
         DB session per admin; FCM failure never touches committed DB state.

    An eligible Admin is any User with role=ADMIN and is_active=True, excluding
    the user whose action triggered the notification (exclude_user_id), e.g. the
    acting Admin so they do not receive self-notifications.
    """
    try:
        import asyncio
        from app.models.user_device import UserDevice

        # 1. Query ALL eligible active admins — no artificial LIMIT
        admin_stmt = (
            select(User.id)
            .where(User.role == Role.ADMIN, User.is_active == True)
        )
        all_admin_ids: list[uuid.UUID] = list(
            (await session.execute(admin_stmt)).scalars().all()
        )

        # Exclude the acting user (e.g. admin who made the change on behalf of employee)
        recipients: list[tuple[uuid.UUID, str, str]] = [
            (admin_id, title, message)
            for admin_id in all_admin_ids
            if not (exclude_user_id and admin_id == exclude_user_id)
        ]

        if not recipients:
            return

        recipient_user_ids = [uid for uid, _, _ in recipients]

        # 2. Bulk-stage notifications with ONE duplicate-check query + session.add_all
        #    Does NOT commit — caller's transaction handles that.
        new_notifs = await notification_service.create_planning_notifications_bulk(
            recipients=recipients,
            notification_type=notification_type,
            planned_visit_id=planned_visit_id,
            session=session,
        )

        if not new_notifs:
            return

        # 3. ONE bulk query to fetch all FCM device tokens for newly notified admins.
        #    We do this BEFORE the session is closed so we can use the request session.
        #    This avoids opening N new sessions in background tasks.
        token_stmt = (
            select(UserDevice.fcm_token)
            .where(
                UserDevice.user_id.in_(recipient_user_ids),
                UserDevice.is_active.is_(True),
            )
        )
        all_tokens: list[str] = list(
            (await session.execute(token_stmt)).scalars().all()
        )

        if not all_tokens:
            # No devices registered — nothing to push, but DB notifications are staged correctly
            return

        # 4. Fire ONE multicast push as a background task after this function returns.
        #    Caller's session.commit() will have been awaited before this task executes.
        #    The task receives pre-fetched tokens — requires zero new DB connections.
        from app.services.fcm_service import fcm_service

        notif_type_str = (
            notification_type.value
            if hasattr(notification_type, "value")
            else str(notification_type)
        )

        async def _push_admin_multicast(tokens: list[str], notif_title: str, notif_msg: str) -> None:
            try:
                await fcm_service.send_multicast(
                    tokens=tokens,
                    title=notif_title,
                    body=notif_msg,
                    data={"type": notif_type_str},
                )
            except Exception as fcm_err:
                logger.warning(
                    "Non-fatal FCM multicast failure for admin planning notification: %s", fcm_err
                )

        asyncio.create_task(_push_admin_multicast(all_tokens, title, message))

    except Exception as e:
        logger.error("Failed to notify admins of employee planning change: %s", e, exc_info=True)





def _enrich_planned_visit(pv: PlannedVisit) -> PlannedVisitRead:
    return PlannedVisitRead(
        id=pv.id,
        monthly_plan_id=pv.monthly_plan_id,
        employee_id=pv.employee_id,
        customer_id=pv.customer_id,
        planned_date=pv.planned_date,
        visit_type=pv.visit_type,
        priority=pv.priority,
        notes=pv.notes,
        status=pv.status,
        created_at=pv.created_at,
        updated_at=pv.updated_at,
        customer_name=pv.customer_name,
        customer_outlet_code=pv.customer_outlet_code,
        customer_address=pv.customer_address,
        employee_name=pv.employee_name,
        employee_code=pv.employee_code,
        area_name=pv.area_name,
        territory_name=pv.territory_name,
    )


def _enrich_monthly_plan(plan: MonthlyVisitPlan) -> MonthlyVisitPlanRead:
    visits = [_enrich_planned_visit(pv) for pv in plan.planned_visits if pv.status != PlannedVisitStatus.CANCELLED]
    active_days = len({v.planned_date for v in visits})
    return MonthlyVisitPlanRead(
        id=plan.id,
        employee_id=plan.employee_id,
        year=plan.year,
        month=plan.month,
        status=plan.status,
        notes=plan.notes,
        created_by=plan.created_by,
        created_at=plan.created_at,
        updated_at=plan.updated_at,
        employee_name=plan.employee.full_name if plan.employee else "",
        employee_code=plan.employee.employee_code if plan.employee else None,
        planned_visits=visits,
        total_planned_visits=len(visits),
        active_days_count=active_days,
    )


async def get_or_create_monthly_plan(
    employee_id: uuid.UUID,
    year: int,
    month: int,
    created_by: uuid.UUID,
    session: AsyncSession,
) -> MonthlyVisitPlan:
    """Idempotently fetch or create the MonthlyVisitPlan for an employee and month."""
    if not (1 <= month <= 12):
        raise ValidationException("Month must be between 1 and 12")
    if not (2000 <= year <= 2100):
        raise ValidationException("Year must be between 2000 and 2100")

    stmt = (
        select(MonthlyVisitPlan)
        .options(
            selectinload(MonthlyVisitPlan.planned_visits).joinedload(PlannedVisit.customer),
            selectinload(MonthlyVisitPlan.planned_visits).joinedload(PlannedVisit.employee),
        )
        .where(
            MonthlyVisitPlan.employee_id == employee_id,
            MonthlyVisitPlan.year == year,
            MonthlyVisitPlan.month == month,
        )
    )
    result = await session.execute(stmt)
    plan = result.scalar_one_or_none()
    if plan is not None:
        return plan

    # Create new plan
    new_plan = MonthlyVisitPlan(
        employee_id=employee_id,
        year=year,
        month=month,
        created_by=created_by,
        status=MonthlyPlanStatus.ACTIVE,
    )
    session.add(new_plan)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        # Race condition catch
        result = await session.execute(stmt)
        plan = result.scalar_one_or_none()
        if plan is not None:
            return plan
        raise BaseAPIException(detail="Failed to initialize monthly plan", status_code=500, error_code="PLAN_INITIALIZATION_ERROR")

    # Re-query with eager relationships
    result = await session.execute(stmt)
    return result.scalar_one()


async def get_my_plan(
    current_user: User,
    year: int,
    month: int,
    session: AsyncSession,
) -> MonthlyVisitPlanRead:
    """Employee: retrieve caller's monthly plan and planned visits for the month."""
    employee = await get_employee_by_user_id(current_user.id, session)
    plan = await get_or_create_monthly_plan(employee.id, year, month, current_user.id, session)
    return _enrich_monthly_plan(plan)


async def get_employee_plan(
    employee_id: uuid.UUID,
    year: int,
    month: int,
    current_user: User,
    session: AsyncSession,
) -> MonthlyVisitPlanRead:
    """Admin or owner: retrieve specified employee's monthly plan."""
    if current_user.role != Role.ADMIN:
        caller_emp = await get_employee_by_user_id(current_user.id, session)
        if caller_emp.id != employee_id:
            raise ForbiddenException("Access denied to another employee's plan")

    await get_employee(employee_id, session)
    plan = await get_or_create_monthly_plan(employee_id, year, month, current_user.id, session)
    return _enrich_monthly_plan(plan)


async def list_monthly_plans(
    year: int,
    month: int,
    current_user: User,
    session: AsyncSession,
) -> list[MonthlyPlanSummaryRead]:
    """Admin: list monthly planning summaries across all active employees."""
    if current_user.role != Role.ADMIN:
        raise ForbiddenException("Admin authorization required")

    # Fetch active employees
    employees_res = await session.execute(
        select(Employee).order_by(Employee.full_name.asc())
    )
    employees = employees_res.scalars().all()

    # Fetch plans for this year and month
    plans_res = await session.execute(
        select(MonthlyVisitPlan)
        .options(selectinload(MonthlyVisitPlan.planned_visits))
        .where(
            MonthlyVisitPlan.year == year,
            MonthlyVisitPlan.month == month,
        )
    )
    plans_by_emp = {p.employee_id: p for p in plans_res.scalars().all()}

    summaries: list[MonthlyPlanSummaryRead] = []
    for emp in employees:
        plan = plans_by_emp.get(emp.id)
        if plan:
            active_visits = [pv for pv in plan.planned_visits if pv.status != PlannedVisitStatus.CANCELLED]
            active_days = len({pv.planned_date for pv in active_visits})
            summaries.append(
                MonthlyPlanSummaryRead(
                    id=plan.id,
                    employee_id=emp.id,
                    employee_name=emp.full_name,
                    employee_code=emp.employee_code,
                    year=year,
                    month=month,
                    status=plan.status,
                    total_planned_visits=len(active_visits),
                    active_days_count=active_days,
                )
            )
        else:
            summaries.append(
                MonthlyPlanSummaryRead(
                    id=uuid.UUID(int=0),  # dummy indicator that plan has not been initialized yet
                    employee_id=emp.id,
                    employee_name=emp.full_name,
                    employee_code=emp.employee_code,
                    year=year,
                    month=month,
                    status=MonthlyPlanStatus.ACTIVE,
                    total_planned_visits=0,
                    active_days_count=0,
                )
            )

    return summaries


async def get_team_plan(
    year: int,
    month: int,
    current_user: User,
    session: AsyncSession,
    employee_id: Optional[uuid.UUID] = None,
) -> TeamMonthlyPlanRead:
    """Admin: retrieve planned visits across all employees (or a filtered employee) for the month."""
    if current_user.role != Role.ADMIN:
        raise ForbiddenException("Admin authorization required")

    stmt = (
        select(PlannedVisit)
        .join(MonthlyVisitPlan, PlannedVisit.monthly_plan_id == MonthlyVisitPlan.id)
        .options(
            selectinload(PlannedVisit.customer),
            selectinload(PlannedVisit.employee),
        )
        .where(
            MonthlyVisitPlan.year == year,
            MonthlyVisitPlan.month == month,
            PlannedVisit.status != PlannedVisitStatus.CANCELLED,
        )
        .order_by(PlannedVisit.planned_date.asc(), PlannedVisit.created_at.asc())
    )
    if employee_id:
        stmt = stmt.where(PlannedVisit.employee_id == employee_id)

    res = await session.execute(stmt)
    visits = res.scalars().all()
    enriched_visits = [_enrich_planned_visit(v) for v in visits]

    active_days = len({v.planned_date for v in visits})
    active_employees = len({v.employee_id for v in visits})

    return TeamMonthlyPlanRead(
        year=year,
        month=month,
        total_planned_visits=len(visits),
        active_days_count=active_days,
        active_employees_count=active_employees,
        planned_visits=enriched_visits,
    )


async def create_planned_visit(
    data: PlannedVisitCreate,
    current_user: User,
    session: AsyncSession,
) -> PlannedVisitRead:
    """Create a new planned visit for any date in the month."""
    req_id = get_current_request_id()

    # Determine target employee
    if current_user.role == Role.ADMIN:
        if data.employee_id:
            target_employee_id = data.employee_id
        else:
            try:
                emp = await get_employee_by_user_id(current_user.id, session)
                target_employee_id = emp.id
            except BaseAPIException:
                raise ValidationException("employee_id must be specified by admin")
    else:
        emp = await get_employee_by_user_id(current_user.id, session)
        target_employee_id = emp.id

    # Validate employee & customer
    await get_employee(target_employee_id, session)
    customer = await get_customer(data.customer_id, session)

    # Date validation: employees cannot plan visits in the past
    if current_user.role != Role.ADMIN and data.planned_date < date.today():
        raise ValidationException("Cannot plan visits for past dates")

    # Get or create monthly plan for the target date's month
    plan = await get_or_create_monthly_plan(
        employee_id=target_employee_id,
        year=data.planned_date.year,
        month=data.planned_date.month,
        created_by=current_user.id,
        session=session,
    )

    planned_visit = PlannedVisit(
        monthly_plan_id=plan.id,
        employee_id=target_employee_id,
        customer_id=customer.id,
        planned_date=data.planned_date,
        visit_type=data.visit_type or VisitType.PLANNED,
        priority=data.priority,
        notes=data.notes.strip() if data.notes else None,
        status=PlannedVisitStatus.PLANNED,
    )
    session.add(planned_visit)
    await session.commit()

    # Re-fetch with eager customer/employee relationships
    stmt = (
        select(PlannedVisit)
        .options(
            selectinload(PlannedVisit.customer),
            selectinload(PlannedVisit.employee),
        )
        .where(PlannedVisit.id == planned_visit.id)
    )
    full_visit = (await session.execute(stmt)).scalar_one()

    logger.info(
        "event=planned_visit_created request_id=%s planned_visit_id=%s employee_id=%s customer_id=%s planned_date=%s",
        req_id,
        full_visit.id,
        target_employee_id,
        customer.id,
        data.planned_date.isoformat(),
    )
    return _enrich_planned_visit(full_visit)


async def update_planned_visit(
    visit_id: uuid.UUID,
    data: PlannedVisitUpdate,
    current_user: User,
    session: AsyncSession,
) -> PlannedVisitRead:
    """Update details (notes, priority, visit_type) of an existing planned visit."""
    stmt = (
        select(PlannedVisit)
        .options(
            selectinload(PlannedVisit.customer),
            selectinload(PlannedVisit.employee),
        )
        .where(PlannedVisit.id == visit_id)
    )
    visit = (await session.execute(stmt)).scalar_one_or_none()
    if visit is None:
        raise ResourceNotFoundException("Planned visit not found")

    # Authorization
    if current_user.role != Role.ADMIN:
        caller_emp = await get_employee_by_user_id(current_user.id, session)
        if visit.employee_id != caller_emp.id:
            raise ForbiddenException("You cannot modify another employee's planned visit")
        if visit.planned_date < date.today():
            raise ValidationException("Cannot modify past planned visits")
        if visit.status == PlannedVisitStatus.CANCELLED:
            raise ValidationException("Cannot modify a cancelled visit")

    if data.priority is not None:
        visit.priority = data.priority
    if data.notes is not None:
        visit.notes = data.notes.strip() if data.notes.strip() else None
    if data.visit_type is not None:
        visit.visit_type = data.visit_type

    session.add(visit)
    await session.commit()
    await session.refresh(visit)

    # If an employee made the change, notify active Admins
    if current_user.role != Role.ADMIN:
        emp_name = visit.employee.full_name if visit.employee else "Employee"
        cust_name = visit.customer.name if visit.customer else "Customer"
        date_str = visit.planned_date.strftime("%d %b %Y")
        msg = f"{emp_name} updated planned visit for {cust_name} on {date_str}."
        await _notify_admins_of_employee_change(
            notification_type=NotificationType.EMPLOYEE_SCHEDULE_CHANGED,
            title="Employee Updated Schedule",
            message=msg,
            planned_visit_id=visit.id,
            session=session,
            exclude_user_id=current_user.id,
        )
        # Persist the bulk-staged notification records in one commit
        await session.commit()

    return _enrich_planned_visit(visit)


async def reschedule_planned_visit(
    visit_id: uuid.UUID,
    new_date: date,
    current_user: User,
    session: AsyncSession,
) -> PlannedVisitRead:
    """Reschedule a planned visit to a new target date."""
    req_id = get_current_request_id()
    stmt = (
        select(PlannedVisit)
        .options(
            selectinload(PlannedVisit.customer),
            selectinload(PlannedVisit.employee),
        )
        .where(PlannedVisit.id == visit_id)
    )
    visit = (await session.execute(stmt)).scalar_one_or_none()
    if visit is None:
        raise ResourceNotFoundException("Planned visit not found")

    # Authorization
    if current_user.role != Role.ADMIN:
        caller_emp = await get_employee_by_user_id(current_user.id, session)
        if visit.employee_id != caller_emp.id:
            raise ForbiddenException("You cannot reschedule another employee's planned visit")
        if visit.planned_date < date.today():
            raise ValidationException("Cannot reschedule past planned visits")
        if new_date < date.today():
            raise ValidationException("Cannot reschedule visit to a past date")
        if visit.status == PlannedVisitStatus.CANCELLED:
            raise ValidationException("Cannot reschedule a cancelled visit")

    old_date = visit.planned_date
    # If the new date falls in a different month/year, move to that month's plan
    if new_date.year != old_date.year or new_date.month != old_date.month:
        new_plan = await get_or_create_monthly_plan(
            employee_id=visit.employee_id,
            year=new_date.year,
            month=new_date.month,
            created_by=current_user.id,
            session=session,
        )
        visit.monthly_plan_id = new_plan.id

    visit.planned_date = new_date
    session.add(visit)
    await session.commit()
    await session.refresh(visit)

    logger.info(
        "event=planned_visit_rescheduled request_id=%s visit_id=%s old_date=%s new_date=%s employee_id=%s",
        req_id,
        visit.id,
        old_date.isoformat(),
        new_date.isoformat(),
        visit.employee_id,
    )

    # If an employee rescheduled the visit, notify active Admins
    if current_user.role != Role.ADMIN:
        emp_name = visit.employee.full_name if visit.employee else "Employee"
        cust_name = visit.customer.name if visit.customer else "Customer"
        old_str = old_date.strftime("%d %b %Y")
        new_str = new_date.strftime("%d %b %Y")
        msg = f"{emp_name} rescheduled planned visit for {cust_name} from {old_str} to {new_str}."
        await _notify_admins_of_employee_change(
            notification_type=NotificationType.EMPLOYEE_SCHEDULE_CHANGED,
            title="Employee Rescheduled Visit",
            message=msg,
            planned_visit_id=visit.id,
            session=session,
            exclude_user_id=current_user.id,
        )
        # Persist the bulk-staged notification records in one commit
        await session.commit()

    return _enrich_planned_visit(visit)


async def delete_planned_visit(
    visit_id: uuid.UUID,
    current_user: User,
    session: AsyncSession,
) -> None:
    """Soft-cancel a planned visit (sets status to CANCELLED for analytics history)."""
    req_id = get_current_request_id()
    stmt = (
        select(PlannedVisit)
        .options(
            selectinload(PlannedVisit.customer),
            selectinload(PlannedVisit.employee),
        )
        .where(PlannedVisit.id == visit_id)
    )
    visit = (await session.execute(stmt)).scalar_one_or_none()
    if visit is None:
        raise ResourceNotFoundException("Planned visit not found")

    # Authorization
    if current_user.role != Role.ADMIN:
        caller_emp = await get_employee_by_user_id(current_user.id, session)
        if visit.employee_id != caller_emp.id:
            raise ForbiddenException("You cannot delete another employee's planned visit")
        if visit.planned_date < date.today():
            raise ValidationException("Cannot delete past planned visits")

    if visit.status == PlannedVisitStatus.CANCELLED:
        # Already cancelled — idempotent
        logger.info("event=planned_visit_already_cancelled request_id=%s visit_id=%s", req_id, visit_id)
        return

    visit.status = PlannedVisitStatus.CANCELLED
    session.add(visit)
    await session.commit()
    logger.info("event=planned_visit_cancelled request_id=%s visit_id=%s", req_id, visit_id)

    # If an employee cancelled the visit, notify active Admins
    if current_user.role != Role.ADMIN:
        emp_name = visit.employee.full_name if visit.employee else "Employee"
        cust_name = visit.customer.name if visit.customer else "Customer"
        date_str = visit.planned_date.strftime("%d %b %Y")
        msg = f"{emp_name} cancelled planned visit for {cust_name} scheduled on {date_str}."
        await _notify_admins_of_employee_change(
            notification_type=NotificationType.PLANNED_VISIT_CANCELLED,
            title="Planned Visit Cancelled",
            message=msg,
            planned_visit_id=visit.id,
            session=session,
            exclude_user_id=current_user.id,
        )
        # Persist the bulk-staged notification records in one commit
        await session.commit()




async def reassign_planned_visit(
    visit_id: uuid.UUID,
    new_employee_id: uuid.UUID,
    current_user: User,
    session: AsyncSession,
) -> PlannedVisitRead:
    """Admin: reassign a planned visit to another employee."""
    if current_user.role != Role.ADMIN:
        raise ForbiddenException("Only administrators can reassign planned visits")

    stmt = (
        select(PlannedVisit)
        .options(
            selectinload(PlannedVisit.customer),
            selectinload(PlannedVisit.employee),
        )
        .where(PlannedVisit.id == visit_id)
    )
    visit = (await session.execute(stmt)).scalar_one_or_none()
    if visit is None:
        raise ResourceNotFoundException("Planned visit not found")

    # Validate new employee exists
    new_emp = await get_employee(new_employee_id, session)

    # Move to new employee's monthly plan
    target_plan = await get_or_create_monthly_plan(
        employee_id=new_emp.id,
        year=visit.planned_date.year,
        month=visit.planned_date.month,
        created_by=current_user.id,
        session=session,
    )

    old_emp_id = visit.employee_id
    visit.employee_id = new_emp.id
    visit.monthly_plan_id = target_plan.id
    session.add(visit)
    await session.commit()

    # Re-fetch with eager relationships
    stmt = (
        select(PlannedVisit)
        .options(
            selectinload(PlannedVisit.customer),
            selectinload(PlannedVisit.employee),
        )
        .where(PlannedVisit.id == visit.id)
    )
    updated_visit = (await session.execute(stmt)).scalar_one()

    logger.info(
        "event=planned_visit_reassigned visit_id=%s old_employee_id=%s new_employee_id=%s",
        visit.id,
        old_emp_id,
        new_emp.id,
    )
    return _enrich_planned_visit(updated_visit)
