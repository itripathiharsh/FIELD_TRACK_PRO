from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.context import get_current_request_id
from app.exceptions.custom import BaseAPIException
from app.models.customer import Customer
from app.models.customer_location_proposal import CustomerLocationProposal, LocationProposalStatus
from app.models.employee import Employee
from app.models.user import Role, User
from app.schemas.location_proposal import (
    LocationProposalCreate,
    LocationProposalRead,
    LocationProposalReview,
)
from app.services.customer_service import calculate_distance_meters, extract_coords

logger = logging.getLogger("fieldtrackpro")


async def _enrich_proposal_read(
    proposal: CustomerLocationProposal,
    session: AsyncSession,
) -> LocationProposalRead:
    cust_query = select(Customer).where(Customer.id == proposal.customer_id)
    cust_res = await session.execute(cust_query)
    customer = cust_res.scalar_one_or_none()

    curr_lat, curr_lng = None, None
    dist_m = None
    if customer and customer.location is not None:
        curr_lat, curr_lng = extract_coords(customer.location)
        dist_m = calculate_distance_meters(curr_lat, curr_lng, proposal.proposed_latitude, proposal.proposed_longitude)

    submitter_name = None
    if proposal.submitted_by_employee_id:
        emp_res = await session.execute(
            select(Employee).where(Employee.id == proposal.submitted_by_employee_id)
        )
        emp = emp_res.scalar_one_or_none()
        if emp:
            submitter_name = emp.full_name
    elif proposal.submitted_by:
        user_res = await session.execute(
            select(User).where(User.id == proposal.submitted_by)
        )
        u = user_res.scalar_one_or_none()
        if u:
            submitter_name = u.email

    reviewer_name = None
    if proposal.reviewed_by:
        rev_res = await session.execute(
            select(User).where(User.id == proposal.reviewed_by)
        )
        rev = rev_res.scalar_one_or_none()
        if rev:
            reviewer_name = rev.email

    return LocationProposalRead(
        id=proposal.id,
        customer_id=proposal.customer_id,
        customer_name=customer.name if customer else None,
        customer_outlet_code=customer.outlet_code if customer else None,
        current_latitude=curr_lat,
        current_longitude=curr_lng,
        proposed_latitude=proposal.proposed_latitude,
        proposed_longitude=proposal.proposed_longitude,
        gps_accuracy_meters=proposal.gps_accuracy_meters,
        distance_meters=dist_m,
        submitted_by=proposal.submitted_by,
        submitter_name=submitter_name,
        submitted_by_employee_id=proposal.submitted_by_employee_id,
        submitted_at=proposal.submitted_at,
        status=proposal.status,
        reviewed_by=proposal.reviewed_by,
        reviewer_name=reviewer_name,
        reviewed_at=proposal.reviewed_at,
        rejection_reason=proposal.rejection_reason,
        notes=proposal.notes,
        created_at=proposal.created_at,
        updated_at=proposal.updated_at,
    )


async def create_location_proposal(
    customer_id: uuid.UUID,
    data: LocationProposalCreate,
    current_user: User,
    session: AsyncSession,
) -> LocationProposalRead:
    # 1. Validate customer exists
    cust_res = await session.execute(select(Customer).where(Customer.id == customer_id))
    customer = cust_res.scalar_one_or_none()
    if customer is None:
        raise BaseAPIException(
            status_code=404,
            detail="Customer not found",
            error_code="CUSTOMER_NOT_FOUND",
        )

    # 2. Check single active pending proposal guard
    existing_pending = await session.execute(
        select(CustomerLocationProposal).where(
            and_(
                CustomerLocationProposal.customer_id == customer_id,
                CustomerLocationProposal.status == LocationProposalStatus.PENDING,
            )
        )
    )
    if existing_pending.scalar_one_or_none() is not None:
        raise BaseAPIException(
            status_code=409,
            detail="A pending location proposal already exists for this customer. Please wait for Admin review.",
            error_code="DUPLICATE_PENDING_PROPOSAL",
        )

    # 3. Resolve employee if caller is an employee
    employee_id = None
    if current_user.role == Role.EMPLOYEE:
        emp_res = await session.execute(
            select(Employee).where(Employee.user_id == current_user.id)
        )
        emp = emp_res.scalar_one_or_none()
        if emp:
            employee_id = emp.id

    # 4. Create proposal
    proposal = CustomerLocationProposal(
        customer_id=customer_id,
        proposed_latitude=data.proposed_latitude,
        proposed_longitude=data.proposed_longitude,
        gps_accuracy_meters=data.gps_accuracy_meters,
        submitted_by=current_user.id,
        submitted_by_employee_id=employee_id,
        notes=data.notes,
        status=LocationProposalStatus.PENDING,
    )
    session.add(proposal)

    # 5. Update customer location_status to indicate pending proposal
    customer.location_status = "PENDING_APPROVAL"
    session.add(customer)

    await session.commit()
    await session.refresh(proposal)

    req_id = get_current_request_id()
    logger.info(
        "event=location_proposal result=submitted request_id=%s proposal_id=%s customer_id=%s submitted_by=%s accuracy_m=%s",
        req_id,
        proposal.id,
        customer_id,
        current_user.id,
        data.gps_accuracy_meters,
    )

    return await _enrich_proposal_read(proposal, session)


async def list_location_proposals(
    session: AsyncSession,
    status: Optional[str] = None,
    customer_id: Optional[uuid.UUID] = None,
    skip: int = 0,
    limit: int = 50,
) -> list[LocationProposalRead]:
    query = select(CustomerLocationProposal).order_by(CustomerLocationProposal.created_at.desc())

    if status and status.upper() != "ALL":
        try:
            status_enum = LocationProposalStatus(status.upper())
            query = query.where(CustomerLocationProposal.status == status_enum)
        except ValueError:
            pass

    if customer_id:
        query = query.where(CustomerLocationProposal.customer_id == customer_id)

    query = query.offset(skip).limit(limit)
    res = await session.execute(query)
    proposals = res.scalars().all()

    enriched = []
    for p in proposals:
        read_obj = await _enrich_proposal_read(p, session)
        enriched.append(read_obj)

    return enriched


async def approve_location_proposal(
    proposal_id: uuid.UUID,
    admin_user: User,
    session: AsyncSession,
) -> LocationProposalRead:
    req_id = get_current_request_id()
    if admin_user.role != Role.ADMIN:
        logger.warning("event=location_approval result=rejected reason=FORBIDDEN_APPROVAL request_id=%s user_id=%s", req_id, admin_user.id)
        raise BaseAPIException(
            status_code=403,
            detail="Only administrators can approve location proposals.",
            error_code="FORBIDDEN_APPROVAL",
        )

    res = await session.execute(
        select(CustomerLocationProposal).where(CustomerLocationProposal.id == proposal_id)
    )
    proposal = res.scalar_one_or_none()
    if proposal is None:
        logger.warning("event=location_approval result=rejected reason=PROPOSAL_NOT_FOUND request_id=%s proposal_id=%s", req_id, proposal_id)
        raise BaseAPIException(
            status_code=404,
            detail="Location proposal not found",
            error_code="PROPOSAL_NOT_FOUND",
        )

    if proposal.status != LocationProposalStatus.PENDING:
        logger.warning(
            "event=location_approval result=rejected reason=INVALID_PROPOSAL_STATUS request_id=%s proposal_id=%s status=%s",
            req_id,
            proposal.id,
            proposal.status.value,
        )
        raise BaseAPIException(
            status_code=400,
            detail=f"Cannot approve proposal with status '{proposal.status.value}'. Only PENDING proposals can be approved.",
            error_code="INVALID_PROPOSAL_STATUS",
        )

    # 1. Update proposal status
    now_utc = datetime.now(tz=timezone.utc)
    proposal.status = LocationProposalStatus.APPROVED
    proposal.reviewed_by = admin_user.id
    proposal.reviewed_at = now_utc
    session.add(proposal)

    # 2. Update official customer coordinates
    cust_res = await session.execute(
        select(Customer).where(Customer.id == proposal.customer_id)
    )
    customer = cust_res.scalar_one_or_none()
    if customer:
        customer.location = f"POINT({proposal.proposed_longitude} {proposal.proposed_latitude})"
        customer.location_status = "VERIFIED"
        session.add(customer)

    await session.commit()
    await session.refresh(proposal)

    logger.info(
        "event=location_approval result=approved request_id=%s proposal_id=%s customer_id=%s approved_by=%s",
        req_id,
        proposal.id,
        proposal.customer_id,
        admin_user.id,
    )

    return await _enrich_proposal_read(proposal, session)


async def reject_location_proposal(
    proposal_id: uuid.UUID,
    review_data: LocationProposalReview,
    admin_user: User,
    session: AsyncSession,
) -> LocationProposalRead:
    req_id = get_current_request_id()
    if admin_user.role != Role.ADMIN:
        logger.warning("event=location_rejection result=rejected reason=FORBIDDEN_REJECTION request_id=%s user_id=%s", req_id, admin_user.id)
        raise BaseAPIException(
            status_code=403,
            detail="Only administrators can reject location proposals.",
            error_code="FORBIDDEN_REJECTION",
        )

    rejection_reason = (review_data.rejection_reason or "").strip()
    if not rejection_reason or len(rejection_reason) < 3:
        logger.warning("event=location_rejection result=rejected reason=REJECTION_REASON_REQUIRED request_id=%s proposal_id=%s", req_id, proposal_id)
        raise BaseAPIException(
            status_code=422,
            detail="A rejection reason of at least 3 characters is required to reject a location proposal.",
            error_code="REJECTION_REASON_REQUIRED",
        )

    res = await session.execute(
        select(CustomerLocationProposal).where(CustomerLocationProposal.id == proposal_id)
    )
    proposal = res.scalar_one_or_none()
    if proposal is None:
        logger.warning("event=location_rejection result=rejected reason=PROPOSAL_NOT_FOUND request_id=%s proposal_id=%s", req_id, proposal_id)
        raise BaseAPIException(
            status_code=404,
            detail="Location proposal not found",
            error_code="PROPOSAL_NOT_FOUND",
        )

    if proposal.status != LocationProposalStatus.PENDING:
        logger.warning(
            "event=location_rejection result=rejected reason=INVALID_PROPOSAL_STATUS request_id=%s proposal_id=%s status=%s",
            req_id,
            proposal.id,
            proposal.status.value,
        )
        raise BaseAPIException(
            status_code=400,
            detail=f"Cannot reject proposal with status '{proposal.status.value}'. Only PENDING proposals can be rejected.",
            error_code="INVALID_PROPOSAL_STATUS",
        )

    # 1. Update proposal status and rejection reason
    now_utc = datetime.now(tz=timezone.utc)
    proposal.status = LocationProposalStatus.REJECTED
    proposal.reviewed_by = admin_user.id
    proposal.reviewed_at = now_utc
    proposal.rejection_reason = rejection_reason
    session.add(proposal)

    # 2. Revert customer location_status if no other verified location
    cust_res = await session.execute(
        select(Customer).where(Customer.id == proposal.customer_id)
    )
    customer = cust_res.scalar_one_or_none()
    if customer:
        if customer.location is None:
            customer.location_status = "MISSING"
        else:
            customer.location_status = "VERIFIED"
        session.add(customer)

    await session.commit()
    await session.refresh(proposal)

    logger.info(
        "event=location_approval result=rejected request_id=%s proposal_id=%s customer_id=%s rejected_by=%s reason=%s",
        req_id,
        proposal.id,
        proposal.customer_id,
        admin_user.id,
        rejection_reason,
    )

    return await _enrich_proposal_read(proposal, session)
