"""
Field Exceptions Router — /api/v1/field-exceptions
"""
from __future__ import annotations
import uuid
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps.auth import CurrentUser, require_role
from app.database import get_async_session
from app.models.field_exception import ExceptionStatus
from app.models.user import Role
from app.schemas.field_exception import FieldExceptionCreate, FieldExceptionRead, FieldExceptionReview
from app.services import field_exception_service

router = APIRouter(prefix="/field-exceptions", tags=["field-exceptions"])

DbSession = Annotated[AsyncSession, Depends(get_async_session)]
AdminOnly = Depends(require_role(Role.ADMIN))
AnyAuth = Depends(require_role(Role.ADMIN, Role.EMPLOYEE))


@router.post("", response_model=FieldExceptionRead, status_code=201, dependencies=[AnyAuth])
async def file_field_exception(
    data: FieldExceptionCreate,
    current_user: CurrentUser,
    session: DbSession,
):
    """Employee / Admin: File a field exception when unable to check in or perform visit."""
    return await field_exception_service.create_field_exception(data, current_user, session)


@router.get("", response_model=list[FieldExceptionRead], dependencies=[AnyAuth])
async def list_field_exceptions(
    response: Response,
    current_user: CurrentUser,
    session: DbSession,
    status: Optional[ExceptionStatus] = Query(default=None),
    employee_id: Optional[uuid.UUID] = Query(default=None),
    customer_id: Optional[uuid.UUID] = Query(default=None),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
):
    """
    List filed exceptions with role scoping (employee sees own, admin sees all).
    """
    items, total_count = await field_exception_service.list_field_exceptions(
        current_user=current_user,
        session=session,
        status=status,
        employee_id=employee_id,
        customer_id=customer_id,
        skip=skip,
        limit=limit,
    )
    response.headers["X-Total-Count"] = str(total_count)
    return items


@router.patch("/{exception_id}/review", response_model=FieldExceptionRead, dependencies=[AdminOnly])
async def review_field_exception(
    exception_id: uuid.UUID,
    data: FieldExceptionReview,
    current_user: CurrentUser,
    session: DbSession,
):
    """Admin: Approve or reject a field exception with reviewer notes."""
    return await field_exception_service.review_field_exception(exception_id, data, current_user, session)
