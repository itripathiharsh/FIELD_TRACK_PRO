"""
Customer prospect approval workflow.

A new outlet submitted by a field EMPLOYEE is held here (PENDING) instead of
becoming a live Customer row immediately - an admin reviews name/contacts/
brands/GPS/initial requirement together and either approves (creates the real
Customer, with needs_tally_entry=True since there is no Tally writeback for
customers) or rejects (nothing is created; the employee is told why).

An ADMIN submitting the same form is NOT subject to this - see
customer_service.create_customer_prospect, which still creates the Customer
immediately for an admin caller. Only the employee path routes through here.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from geoalchemy2.shape import from_shape
from shapely.geometry import Point
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.context import get_current_request_id
from app.exceptions.custom import BaseAPIException
from app.models.customer import Customer
from app.models.customer_brand import CustomerBrand
from app.models.customer_prospect import CustomerProspect, ProspectStatus
from app.models.customer_requirement import CustomerRequirement
from app.models.employee_customer_assignment import EmployeeCustomerAssignment
from app.models.notification import NotificationType
from app.models.user import Role, User
from app.schemas.customer import CustomerProspectCreate
from app.schemas.customer_prospect import CustomerProspectUpdate
from app.config import settings  # live outlet proof flag
from app.services import outlet_proof_service  # live outlet proof
from app.services.employee_service import get_employee_by_user_id

logger = logging.getLogger("fieldtrackpro")

_EAGER = (
    selectinload(CustomerProspect.territory),
    selectinload(CustomerProspect.area),
    selectinload(CustomerProspect.submitter_user),
    selectinload(CustomerProspect.submitter_employee),
    selectinload(CustomerProspect.reviewer_user),
)


async def _check_duplicate(
    session: AsyncSession,
    contact_number: str | None,
    gst_number: str | None,
    outlet_code: str | None,
    exclude_prospect_id: Optional[uuid.UUID] = None,
) -> None:
    """
    Checks both live Customers AND other PENDING prospects. Checking only Customers
    would miss the obvious case of two submissions for the same outlet both sitting
    PENDING at once - neither is a live Customer yet, so neither would ever trip a
    Customer-only check, and an admin could approve both as separate outlets.
    """
    cust_conditions = []
    if contact_number:
        cust_conditions.append(Customer.contact_number == contact_number)
    if gst_number:
        cust_conditions.append(Customer.gst_number == gst_number)
    if outlet_code:
        cust_conditions.append(Customer.outlet_code == outlet_code)
    if cust_conditions:
        dup = (await session.execute(select(Customer).where(or_(*cust_conditions)).limit(1))).scalar_one_or_none()
        if dup is not None:
            raise BaseAPIException(
                status_code=409,
                detail=f"Possible existing customer found: '{dup.name}'. Search for it by name and start an ad-hoc visit instead.",
                error_code="DUPLICATE_CUSTOMER",
            )

    prospect_conditions = []
    if contact_number:
        prospect_conditions.append(CustomerProspect.contact_number == contact_number)
    if gst_number:
        prospect_conditions.append(CustomerProspect.gst_number == gst_number)
    if outlet_code:
        prospect_conditions.append(CustomerProspect.outlet_code == outlet_code)
    if prospect_conditions:
        stmt = select(CustomerProspect).where(
            CustomerProspect.status == ProspectStatus.PENDING, or_(*prospect_conditions)
        )
        if exclude_prospect_id is not None:
            stmt = stmt.where(CustomerProspect.id != exclude_prospect_id)
        dup_prospect = (await session.execute(stmt.limit(1))).scalar_one_or_none()
        if dup_prospect is not None:
            raise BaseAPIException(
                status_code=409,
                detail=f"Possible duplicate submission already pending review: '{dup_prospect.name}'.",
                error_code="DUPLICATE_CUSTOMER",
            )


async def submit_prospect(
    data: CustomerProspectCreate, current_user: User, session: AsyncSession
) -> CustomerProspect:
    """Employee submission: holds the outlet for admin review, creates nothing live yet."""
    req_id = get_current_request_id()

    # --- live outlet proof: required for employee submissions unless the flag is off ---
    proof = None
    if data.outlet_proof_id is not None:
        proof = await outlet_proof_service.claim_unattached_proof(data.outlet_proof_id, current_user, session)
    elif settings.outlet_proof_required_for_new_outlet:
        raise BaseAPIException(
            status_code=422,
            detail="A live outlet photo with GPS (outlet_proof_id) is required to submit a new outlet.",
            error_code="OUTLET_PROOF_REQUIRED",
        )

    if not data.force:
        await _check_duplicate(
            session,
            data.contact_number,
            data.gst_number,
            data.outlet_code.strip().upper() if data.outlet_code else None,
        )

    employee = await get_employee_by_user_id(current_user.id, session)

    requirement_payload = None
    if data.requirement is not None:
        requirement_payload = data.requirement.model_dump(mode="json", exclude={"customer_id", "visit_id", "items", "photo_media_id"})

    prospect = CustomerProspect(
        name=data.name,
        contact_number=data.contact_number,
        contact_person=data.contact_person,
        gst_number=data.gst_number,
        address=data.address,
        outlet_code=data.outlet_code.strip().upper() if data.outlet_code else None,
        territory_id=data.territory_id,
        area_id=data.area_id,
        brand_names=[b.strip() for b in data.brands if b.strip()] if data.brands else [],
        # With a live outlet proof the proof's own GPS wins; client-supplied coordinates are ignored.
        proposed_latitude=proof.latitude if proof else (data.location.latitude if data.location else None),
        proposed_longitude=proof.longitude if proof else (data.location.longitude if data.location else None),
        gps_accuracy_meters=proof.accuracy_m if proof else data.gps_accuracy_meters,
        location_notes=data.notes,
        requirement_payload=requirement_payload,
        submitted_by=current_user.id,
        submitted_by_employee_id=employee.id,
        status=ProspectStatus.PENDING,
    )
    session.add(prospect)
    if proof is not None:
        await session.flush()
        outlet_proof_service.link_proof_to_prospect(proof, prospect)
    await session.commit()
    await session.refresh(prospect, attribute_names=["territory", "area", "submitter_user", "submitter_employee"])

    logger.info(
        "event=customer_prospect_submit result=success request_id=%s prospect_id=%s name=%s employee_id=%s",
        req_id, prospect.id, prospect.name, employee.id,
    )
    return prospect


async def list_prospects(
    session: AsyncSession, current_user: User, status: Optional[ProspectStatus] = None
) -> list[CustomerProspect]:
    stmt = select(CustomerProspect).options(*_EAGER).order_by(CustomerProspect.submitted_at.desc())
    if not current_user.is_admin:
        stmt = stmt.where(CustomerProspect.submitted_by == current_user.id)
    if status is not None:
        stmt = stmt.where(CustomerProspect.status == status)
    return list((await session.execute(stmt)).scalars().all())


async def get_prospect(prospect_id: uuid.UUID, current_user: User, session: AsyncSession) -> CustomerProspect:
    stmt = select(CustomerProspect).options(*_EAGER).where(CustomerProspect.id == prospect_id)
    prospect = (await session.execute(stmt)).scalar_one_or_none()
    if prospect is None:
        raise BaseAPIException(status_code=404, detail="Prospect not found", error_code="PROSPECT_NOT_FOUND")
    if not current_user.is_admin and prospect.submitted_by != current_user.id:
        raise BaseAPIException(status_code=403, detail="Not your submission", error_code="FORBIDDEN")
    return prospect


async def _get_pending_for_admin(prospect_id: uuid.UUID, session: AsyncSession) -> CustomerProspect:
    stmt = select(CustomerProspect).options(*_EAGER).where(CustomerProspect.id == prospect_id).with_for_update()
    prospect = (await session.execute(stmt)).scalar_one_or_none()
    if prospect is None:
        raise BaseAPIException(status_code=404, detail="Prospect not found", error_code="PROSPECT_NOT_FOUND")
    if prospect.status != ProspectStatus.PENDING:
        # Read before rollback() - rollback() expires the ORM instance, and touching an
        # expired attribute afterwards needs a sync lazy-load the async session can't do here.
        # status is a plain String column (ProspectStatus mixes in str), so .lower() alone
        # works whether this came back as a raw DB string or a freshly-assigned enum member.
        current_status = prospect.status.lower()
        await session.rollback()
        raise BaseAPIException(
            status_code=409,
            detail=f"This submission is already {current_status}.",
            error_code="PROSPECT_NOT_PENDING",
        )
    return prospect


async def update_prospect(
    prospect_id: uuid.UUID, data: CustomerProspectUpdate, session: AsyncSession
) -> CustomerProspect:
    """Admin edits a pending submission before approving (fix a typo, assign the outlet code)."""
    prospect = await _get_pending_for_admin(prospect_id, session)

    if data.name is not None:
        prospect.name = data.name
    if data.contact_number is not None:
        prospect.contact_number = data.contact_number
    if data.contact_person is not None:
        prospect.contact_person = data.contact_person
    if data.gst_number is not None:
        prospect.gst_number = data.gst_number
    if data.address is not None:
        prospect.address = data.address
    if data.outlet_code is not None:
        prospect.outlet_code = data.outlet_code
    if data.territory_id is not None:
        prospect.territory_id = data.territory_id
    if data.area_id is not None:
        prospect.area_id = data.area_id
    if data.brands is not None:
        prospect.brand_names = [b.strip() for b in data.brands if b.strip()]
    if data.requirement is not None:
        prospect.requirement_payload = data.requirement.model_dump(mode="json")
    if data.proposed_latitude is not None:
        prospect.proposed_latitude = data.proposed_latitude
    if data.proposed_longitude is not None:
        prospect.proposed_longitude = data.proposed_longitude

    await session.commit()
    await session.refresh(prospect, attribute_names=["territory", "area", "submitter_user", "submitter_employee"])
    return prospect


async def approve_prospect(prospect_id: uuid.UUID, current_user: User, session: AsyncSession) -> Customer:
    """
    Creates the real Customer (and its brands/assignment/requirement) from a pending
    prospect, in one step - this review IS the location approval too, so the
    customer's location is written straight to VERIFIED rather than going through a
    separate CustomerLocationProposal (that mechanism is for re-pinning an
    ALREADY-LIVE customer's location later, not for a brand-new one under review here).
    """
    req_id = get_current_request_id()
    prospect = await _get_pending_for_admin(prospect_id, session)

    # Re-check for a duplicate created in the meantime (another prospect approved,
    # or an admin created the same outlet directly, since this one was submitted).
    # exclude_prospect_id=prospect.id: it is still PENDING at this point (flipped to
    # APPROVED further down) and must not be flagged as a duplicate of itself.
    await _check_duplicate(
        session, prospect.contact_number, prospect.gst_number, prospect.outlet_code, exclude_prospect_id=prospect.id
    )

    official_location = None
    loc_status = "MISSING"
    if prospect.proposed_latitude is not None and prospect.proposed_longitude is not None:
        official_location = from_shape(Point(prospect.proposed_longitude, prospect.proposed_latitude), srid=4326)
        loc_status = "VERIFIED"

    customer = Customer(
        name=prospect.name,
        contact_number=prospect.contact_number,
        contact_person=prospect.contact_person,
        gst_number=prospect.gst_number,
        address=prospect.address,
        location=official_location,
        geofence_radius_m=75,
        location_status=loc_status,
        territory_id=prospect.territory_id,
        area_id=prospect.area_id,
        outlet_code=prospect.outlet_code,
        created_by=prospect.submitted_by,
        needs_tally_entry=True,
    )
    session.add(customer)
    await session.flush()

    # Live outlet proof: link it to the new customer and make it the APPROVED primary photo.
    await outlet_proof_service.on_prospect_approved(prospect.id, customer, current_user, session)

    if prospect.submitted_by_employee_id is not None:
        session.add(EmployeeCustomerAssignment(
            employee_id=prospect.submitted_by_employee_id,
            customer_id=customer.id,
            created_by=current_user.id,
        ))

    for brand_name in (prospect.brand_names or []):
        from app.services import brand_service
        from app.schemas.brand import BrandCreate

        b_stripped = brand_name.strip()
        if not b_stripped:
            continue
        brand_obj = await brand_service.get_brand_by_name(session, b_stripped)
        if brand_obj is None:
            brand_obj = await brand_service.create_brand(session, BrandCreate(name=b_stripped))
        session.add(CustomerBrand(customer_id=customer.id, brand=brand_obj.name, brand_id=brand_obj.id, is_active=True))

    if prospect.requirement_payload:
        # Re-parse through the schema (not a raw dict) so follow_up_date comes back as an
        # actual `date` object - it was serialized to an ISO string in requirement_payload
        # (model_dump(mode="json")), and the CustomerRequirement.follow_up_date column needs
        # a real date, not a string.
        from app.schemas.customer_prospect import ProspectRequirementPayload

        req = ProspectRequirementPayload(**prospect.requirement_payload)
        req_brand = req.brand
        if req_brand:
            from app.services import brand_service
            from app.schemas.brand import BrandCreate

            req_b_obj = await brand_service.get_brand_by_name(session, req_brand.strip())
            if req_b_obj is None:
                req_b_obj = await brand_service.create_brand(session, BrandCreate(name=req_brand.strip()))
            req_brand = req_b_obj.name
        session.add(CustomerRequirement(
            customer_id=customer.id,
            brand=req_brand,
            requirement_type=req.requirement_type,
            product_details=req.product_details,
            quantity=req.quantity,
            expected_value=req.expected_value,
            follow_up_date=req.follow_up_date,
            notes=req.notes,
            status="OPEN",
            created_by=current_user.id,
        ))

    prospect.status = ProspectStatus.APPROVED
    prospect.reviewed_by = current_user.id
    prospect.reviewed_at = datetime.now(timezone.utc)
    prospect.resulting_customer_id = customer.id

    await session.commit()
    await session.refresh(customer)

    await _notify_submitter(
        session, prospect,
        title="Outlet approved",
        message=f"Your submission for '{prospect.name}' was approved and is now live.",
    )

    logger.info(
        "event=customer_prospect_approve result=success request_id=%s prospect_id=%s customer_id=%s reviewed_by=%s",
        req_id, prospect.id, customer.id, current_user.id,
    )
    return customer


async def reject_prospect(
    prospect_id: uuid.UUID, reason: str, current_user: User, session: AsyncSession
) -> CustomerProspect:
    req_id = get_current_request_id()
    prospect = await _get_pending_for_admin(prospect_id, session)

    prospect.status = ProspectStatus.REJECTED
    prospect.reviewed_by = current_user.id
    prospect.reviewed_at = datetime.now(timezone.utc)
    prospect.rejection_reason = reason
    # Live outlet proof: mark REJECTED (object kept for audit).
    await outlet_proof_service.on_prospect_rejected(prospect.id, reason, current_user, session)

    await session.commit()
    await session.refresh(prospect, attribute_names=["territory", "area", "submitter_user", "submitter_employee"])

    await _notify_submitter(
        session, prospect,
        title="Outlet submission rejected",
        message=f"Your submission for '{prospect.name}' was rejected: {reason}",
    )

    logger.info(
        "event=customer_prospect_reject result=success request_id=%s prospect_id=%s reviewed_by=%s",
        req_id, prospect.id, current_user.id,
    )
    return prospect


async def _notify_submitter(session: AsyncSession, prospect: CustomerProspect, title: str, message: str) -> None:
    """Best-effort; a notification failure must never undo the approve/reject decision already committed."""
    try:
        from app.services.notification_service import notification_service

        await notification_service.create_notification(
            user_id=prospect.submitted_by,
            notification_type=NotificationType.REMINDER,
            title=title,
            message=message,
            session=session,
        )
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("event=customer_prospect_notify_failed prospect_id=%s error=%s", prospect.id, exc)


async def mark_tally_entry_done(customer_id: uuid.UUID, current_user: User, session: AsyncSession) -> Customer:
    # Customer.territory/area are lazy="joined", so a plain .with_for_update() here would try
    # to lock across that LEFT OUTER JOIN too and Postgres rejects locking the nullable side of
    # an outer join. of=Customer scopes the lock to just the customers row being updated.
    stmt = select(Customer).where(Customer.id == customer_id).with_for_update(of=Customer)
    customer = (await session.execute(stmt)).scalar_one_or_none()
    if customer is None:
        raise BaseAPIException(status_code=404, detail="Customer not found", error_code="CUSTOMER_NOT_FOUND")
    customer.needs_tally_entry = False
    customer.tally_entry_marked_by = current_user.id
    customer.tally_entry_marked_at = datetime.now(timezone.utc)
    await session.commit()
    await session.refresh(customer)
    return customer
