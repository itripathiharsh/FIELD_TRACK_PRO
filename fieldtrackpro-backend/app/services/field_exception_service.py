from __future__ import annotations
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions.custom import BaseAPIException
from app.models.customer import Customer
from app.models.employee import Employee
from app.models.field_exception import FieldException, ExceptionStatus, ExceptionType
from app.models.notification import NotificationType
from app.models.user import Role, User
from app.models.visit import Visit
from app.schemas.field_exception import FieldExceptionCreate, FieldExceptionReview, FieldExceptionRead
from app.services import notification_service
from app.services.employee_service import get_employee_by_user_id

logger = logging.getLogger(__name__)


def _to_read_dto(exc: FieldException) -> FieldExceptionRead:
    return FieldExceptionRead(
        id=exc.id,
        visit_id=exc.visit_id,
        employee_id=exc.employee_id,
        employee_name=exc.employee.full_name if exc.employee else None,
        customer_id=exc.customer_id,
        customer_name=exc.customer.name if exc.customer else None,
        dms_code=exc.customer.outlet_code if exc.customer else None,
        exception_type=exc.exception_type,
        description=exc.description,
        status=exc.status,
        admin_notes=exc.admin_notes,
        reviewed_by=exc.reviewed_by,
        reviewed_by_name=exc.reviewer.email if exc.reviewer else None,
        reviewed_at=exc.reviewed_at,
        created_at=exc.created_at,
        updated_at=exc.updated_at,
    )


async def create_field_exception(
    data: FieldExceptionCreate,
    current_user: User,
    session: AsyncSession,
) -> FieldExceptionRead:
    # 1. Resolve employee id
    if current_user.role == Role.EMPLOYEE:
        emp = await get_employee_by_user_id(current_user.id, session)
        employee_id = emp.id
    else:
        # If admin is creating on behalf of an employee or visit
        if data.visit_id:
            v_res = await session.execute(select(Visit).where(Visit.id == data.visit_id))
            v_obj = v_res.scalar_one_or_none()
            if not v_obj:
                raise BaseAPIException(status_code=404, detail="Visit not found", error_code="VISIT_NOT_FOUND")
            employee_id = v_obj.employee_id
        else:
            # Fallback to any active employee if admin doesn't specify
            e_res = await session.execute(select(Employee).where(Employee.is_active == True).limit(1))
            first_emp = e_res.scalar_one_or_none()
            if not first_emp:
                raise BaseAPIException(status_code=400, detail="No active employee found", error_code="NO_EMPLOYEE")
            employee_id = first_emp.id

    # 2. Verify Customer exists
    cust_res = await session.execute(select(Customer).where(Customer.id == data.customer_id))
    cust = cust_res.scalar_one_or_none()
    if not cust:
        raise BaseAPIException(status_code=404, detail="Customer outlet not found", error_code="CUSTOMER_NOT_FOUND")

    # 3. If visit_id provided, verify visit
    if data.visit_id:
        v_res = await session.execute(select(Visit).where(Visit.id == data.visit_id))
        visit_obj = v_res.scalar_one_or_none()
        if not visit_obj:
            raise BaseAPIException(status_code=404, detail="Visit not found", error_code="VISIT_NOT_FOUND")
        if current_user.role == Role.EMPLOYEE and visit_obj.employee_id != employee_id:
            raise BaseAPIException(status_code=403, detail="You are not assigned to this visit", error_code="VISIT_NOT_ASSIGNED")

    # 4. Insert FieldException
    exc = FieldException(
        visit_id=data.visit_id,
        employee_id=employee_id,
        customer_id=data.customer_id,
        exception_type=data.exception_type,
        description=data.description,
        status=ExceptionStatus.PENDING_REVIEW,
    )
    session.add(exc)
    await session.commit()
    await session.refresh(exc)

    # Reload with relationships
    q = select(FieldException).where(FieldException.id == exc.id)
    full_res = await session.execute(q)
    full_exc = full_res.scalar_one()

    return _to_read_dto(full_exc)


async def list_field_exceptions(
    current_user: User,
    session: AsyncSession,
    status: Optional[ExceptionStatus] = None,
    employee_id: Optional[uuid.UUID] = None,
    customer_id: Optional[uuid.UUID] = None,
    skip: int = 0,
    limit: int = 50,
) -> tuple[list[FieldExceptionRead], int]:
    q = select(FieldException)

    # Role scoping
    if current_user.role == Role.EMPLOYEE:
        emp = await get_employee_by_user_id(current_user.id, session)
        q = q.where(FieldException.employee_id == emp.id)
    elif employee_id:
        q = q.where(FieldException.employee_id == employee_id)

    if status:
        q = q.where(FieldException.status == status)
    if customer_id:
        q = q.where(FieldException.customer_id == customer_id)

    # Count
    count_q = select(func.count()).select_from(q.subquery())
    total_count_res = await session.execute(count_q)
    total_count = total_count_res.scalar_one() or 0

    # Paginate and order by newest first
    q = q.order_by(desc(FieldException.created_at)).offset(skip).limit(limit)
    res = await session.execute(q)
    rows = res.scalars().all()

    return [_to_read_dto(r) for r in rows], total_count


async def review_field_exception(
    exception_id: uuid.UUID,
    data: FieldExceptionReview,
    admin_user: User,
    session: AsyncSession,
) -> FieldExceptionRead:
    q = select(FieldException).where(FieldException.id == exception_id)
    res = await session.execute(q)
    exc = res.scalar_one_or_none()
    if not exc:
        raise BaseAPIException(status_code=404, detail="Field exception not found", error_code="EXCEPTION_NOT_FOUND")

    if data.status not in (ExceptionStatus.APPROVED, ExceptionStatus.REJECTED):
        raise BaseAPIException(
            status_code=400,
            detail="Status must be APPROVED or REJECTED",
            error_code="INVALID_STATUS",
        )

    exc.status = data.status
    exc.admin_notes = data.admin_notes
    exc.reviewed_by = admin_user.id
    exc.reviewed_at = datetime.now(timezone.utc)

    session.add(exc)
    await session.commit()
    await session.refresh(exc)

    # Notify employee if user account exists
    try:
        if exc.employee and exc.employee.user_id:
            await notification_service.notification_service.create_notification(
                user_id=exc.employee.user_id,
                notification_type=NotificationType.REMINDER,
                message=f"Field Exception for {exc.customer.name if exc.customer else 'outlet'} was {data.status.value}: {data.admin_notes or ''}",
                visit_id=exc.visit_id,
                session=session,
            )
    except Exception as e:
        logger.warning(f"Failed to notify employee on exception review: {e}")

    return _to_read_dto(exc)
