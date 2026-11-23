"""Check-in verification requests (employee) and the admin review queue."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select

from app.core.deps.auth import CurrentUser, require_role
from typing import Annotated

from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_async_session
from app.models.customer import Customer
from app.models.employee import Employee
from app.models.user import Role
from app.schemas.checkin_review import (
    CheckInReviewApprove, CheckInReviewRead, CheckInReviewReject, VerificationRequestCreate,
)
from app.services import checkin_review_service as svc

DbSession = Annotated[AsyncSession, Depends(get_async_session)]

router = APIRouter(prefix="/checkin-reviews", tags=["checkin-reviews"])

AdminOnly = Depends(require_role(Role.ADMIN))
EmployeeOrAdmin = Depends(require_role(Role.ADMIN, Role.EMPLOYEE))


async def _named(session, reviews) -> list[CheckInReviewRead]:
    out = [CheckInReviewRead.model_validate(r) for r in reviews]
    cids = {r.customer_id for r in reviews}
    eids = {r.employee_id for r in reviews if r.employee_id}
    cn = dict((await session.execute(select(Customer.id, Customer.name).where(Customer.id.in_(cids)))).all()) if cids else {}
    en = dict((await session.execute(select(Employee.id, Employee.full_name).where(Employee.id.in_(eids)))).all()) if eids else {}
    for o in out:
        o.customer_name = cn.get(o.customer_id)
        o.employee_name = en.get(o.employee_id) if o.employee_id else None
    return out


@router.post("/request", response_model=CheckInReviewRead, status_code=201, dependencies=[EmployeeOrAdmin])
async def request_verification(data: VerificationRequestCreate, current_user: CurrentUser, session: DbSession):
    review = await svc.create_verification_request(session, current_user, data)
    return (await _named(session, [review]))[0]


@router.get("", response_model=list[CheckInReviewRead], dependencies=[AdminOnly])
async def list_reviews(
    session: DbSession,
    status: str | None = Query(default="PENDING", pattern="^(PENDING|APPROVED|REJECTED)$"),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    return await _named(session, await svc.list_reviews(session, status, limit, offset))


@router.post("/{review_id}/approve", response_model=CheckInReviewRead, dependencies=[AdminOnly])
async def approve_review(review_id: uuid.UUID, current_user: CurrentUser, session: DbSession, body: CheckInReviewApprove | None = None):
    review = await svc.approve(session, current_user, review_id, body.note if body else None)
    return (await _named(session, [review]))[0]


@router.post("/{review_id}/reject", response_model=CheckInReviewRead, dependencies=[AdminOnly])
async def reject_review(review_id: uuid.UUID, body: CheckInReviewReject, current_user: CurrentUser, session: DbSession):
    review = await svc.reject(session, current_user, review_id, body.reason)
    return (await _named(session, [review]))[0]
