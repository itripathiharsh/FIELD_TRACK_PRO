from __future__ import annotations

import logging
import mimetypes
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import select, or_, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.exceptions.custom import BaseAPIException
from app.models.customer import Customer
from app.models.customer_requirement import CustomerRequirement
from app.models.employee import Employee
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.requirement_item import RequirementItem
from app.models.tally_writeback import TallyWritebackQueue, WritebackStatus
from app.models.user import Role, User
from app.models.visit import Visit
from app.models.visit_media import MediaType, VisitMedia
from app.schemas.customer_requirement import (
    CustomerRequirementCreate,
    CustomerRequirementRead,
    CustomerRequirementUpdate,
    OrderItemRead,
    OrderRead,
    RequirementConfirmOrderRequest,
    RequirementDecisionAction,
    RequirementDecisionRequest,
    RequirementItemCreate,
    RequirementItemRead,
)
from app.services.storage_service import storage_service

logger = logging.getLogger("fieldtrackpro")


async def _enrich_requirement_read(
    req: CustomerRequirement,
    session: AsyncSession,
) -> CustomerRequirementRead:
    cust_res = await session.execute(select(Customer).where(Customer.id == req.customer_id))
    customer = cust_res.scalar_one_or_none()

    creator_name = None
    if req.created_by:
        user_res = await session.execute(select(User).where(User.id == req.created_by))
        user = user_res.scalar_one_or_none()
        if user:
            emp_res = await session.execute(select(Employee).where(Employee.user_id == user.id))
            emp = emp_res.scalar_one_or_none()
            creator_name = emp.full_name if emp else user.email

    decider_name = None
    if req.decided_by:
        d_user_res = await session.execute(select(User).where(User.id == req.decided_by))
        d_user = d_user_res.scalar_one_or_none()
        if d_user:
            d_emp_res = await session.execute(select(Employee).where(Employee.user_id == d_user.id))
            d_emp = d_emp_res.scalar_one_or_none()
            decider_name = d_emp.full_name if d_emp else d_user.email

    visit_date = None
    if req.visit_id:
        v_res = await session.execute(select(Visit).where(Visit.id == req.visit_id))
        visit = v_res.scalar_one_or_none()
        if visit and visit.scheduled_at:
            visit_date = visit.scheduled_at.date()

    # Generate presigned URL for photo if available
    photo_url = None
    storage_key = req.photo_storage_key
    if not storage_key and req.photo_media_id:
        vm_res = await session.execute(select(VisitMedia).where(VisitMedia.id == req.photo_media_id))
        vm = vm_res.scalar_one_or_none()
        if vm:
            storage_key = vm.storage_key

    if storage_key:
        try:
            photo_url = await storage_service.generate_presigned_url(storage_key, expiry_minutes=60)
        except Exception as ex:
            logger.warning(f"Failed to generate presigned URL for requirement {req.id}: {ex}")

    # Standardize legacy OPEN status to PENDING
    status_display = req.status
    if status_display.upper() == "OPEN":
        status_display = "PENDING"

    # Fetch multi-item line items
    items_res = await session.execute(
        select(RequirementItem)
        .where(RequirementItem.requirement_id == req.id)
        .order_by(RequirementItem.created_at.asc())
    )
    raw_items = items_res.scalars().all()
    read_items = [
        RequirementItemRead(
            id=it.id,
            requirement_id=it.requirement_id,
            brand_id=it.brand_id,
            brand_name=it.brand_name,
            product_model=it.product_model,
            requested_quantity=it.requested_quantity,
            expected_rate=float(it.expected_rate),
            requested_amount=float(it.requested_amount),
            approved_quantity=it.approved_quantity,
            approved_rate=float(it.approved_rate) if it.approved_rate is not None else None,
            approved_amount=float(it.approved_amount) if it.approved_amount is not None else None,
            tally_stock_item_name=it.tally_stock_item_name,
            notes=it.notes,
            created_at=it.created_at,
            updated_at=it.updated_at,
        )
        for it in raw_items
    ]

    total_req_val = float(req.total_requested_value) if req.total_requested_value is not None else (
        float(req.expected_value) if req.expected_value is not None else (
            sum(i.requested_amount for i in read_items) if read_items else None
        )
    )
    total_app_val = float(req.total_approved_value) if req.total_approved_value is not None else (
        float(req.approved_value) if req.approved_value is not None else (
            sum(i.approved_amount for i in read_items if i.approved_amount is not None) if read_items else None
        )
    )

    return CustomerRequirementRead(
        id=req.id,
        customer_id=req.customer_id,
        customer_name=customer.name if customer else None,
        outlet_code=customer.outlet_code if customer else None,
        visit_id=req.visit_id,
        visit_date=visit_date,
        brand=req.brand,
        requirement_type=req.requirement_type,
        product_details=req.product_details,
        quantity=req.quantity,
        expected_value=float(req.expected_value) if req.expected_value is not None else None,
        total_requested_value=total_req_val,
        total_approved_value=total_app_val,
        follow_up_date=req.follow_up_date,
        notes=req.notes,
        photo_storage_key=storage_key,
        photo_media_id=req.photo_media_id,
        photo_url=photo_url,
        status=status_display,
        approved_quantity=req.approved_quantity,
        approved_value=total_app_val,
        admin_notes=req.admin_notes,
        decided_by=req.decided_by,
        decider_name=decider_name,
        decided_at=req.decided_at,
        created_by=req.created_by,
        creator_name=creator_name,
        created_at=req.created_at,
        updated_at=req.updated_at,
        items=read_items,
    )


async def create_requirement(
    customer_id: uuid.UUID,
    data: CustomerRequirementCreate,
    current_user: User,
    session: AsyncSession,
) -> CustomerRequirementRead:
    cust_res = await session.execute(select(Customer).where(Customer.id == customer_id))
    customer = cust_res.scalar_one_or_none()
    if customer is None:
        raise BaseAPIException(
            status_code=404,
            detail="Customer not found",
            error_code="CUSTOMER_NOT_FOUND",
        )

    # Optional visit validation
    visit_id = data.visit_id
    if visit_id:
        v_res = await session.execute(select(Visit).where(Visit.id == visit_id))
        if v_res.scalar_one_or_none() is None:
            raise BaseAPIException(
                status_code=404,
                detail="Visit not found",
                error_code="VISIT_NOT_FOUND",
            )

    req_brand = data.brand
    photo_storage_key = None
    if data.photo_media_id:
        vm_res = await session.execute(select(VisitMedia).where(VisitMedia.id == data.photo_media_id))
        vm = vm_res.scalar_one_or_none()
        if vm:
            photo_storage_key = vm.storage_key

    # Calculate multi-item summary and total requested value
    total_requested_val = Decimal("0.00")
    total_qty = 0
    product_summary_parts = []

    if data.items and len(data.items) > 0:
        for it in data.items:
            rate_dec = Decimal(str(it.expected_rate))
            line_amt = Decimal(str(it.requested_amount)) if it.requested_amount is not None else (rate_dec * it.requested_quantity)
            total_requested_val += line_amt
            total_qty += it.requested_quantity
            product_summary_parts.append(f"{it.brand_name} {it.product_model} ({it.requested_quantity}x)")
        product_details_str = ", ".join(product_summary_parts)
        if not req_brand and len(data.items) == 1:
            req_brand = data.items[0].brand_name
        elif not req_brand:
            unique_brands = list({it.brand_name for it in data.items})
            req_brand = "/".join(unique_brands[:2])
    else:
        product_details_str = data.product_details
        total_qty = data.quantity or 1
        total_requested_val = Decimal(str(data.expected_value)) if data.expected_value is not None else Decimal("0.00")

    req = CustomerRequirement(
        customer_id=customer_id,
        visit_id=visit_id,
        brand=req_brand,
        requirement_type=data.requirement_type or "Sales Order Requirement",
        product_details=product_details_str,
        quantity=total_qty,
        expected_value=float(total_requested_val),
        total_requested_value=total_requested_val,
        total_approved_value=None,
        follow_up_date=data.follow_up_date,
        notes=data.notes,
        photo_media_id=data.photo_media_id,
        photo_storage_key=photo_storage_key,
        status="NEW",
        created_by=current_user.id,
    )
    session.add(req)
    await session.flush()

    # Add line items if provided
    if data.items and len(data.items) > 0:
        for it in data.items:
            rate_dec = Decimal(str(it.expected_rate))
            line_amt = Decimal(str(it.requested_amount)) if it.requested_amount is not None else (rate_dec * it.requested_quantity)
            item_obj = RequirementItem(
                requirement_id=req.id,
                brand_id=it.brand_id,
                brand_name=it.brand_name,
                product_model=it.product_model,
                requested_quantity=it.requested_quantity,
                expected_rate=rate_dec,
                requested_amount=line_amt,
                tally_stock_item_name=f"{it.brand_name} {it.product_model}",
                notes=it.notes,
            )
            session.add(item_obj)
    elif data.product_details:
        # Create a single default line item for legacy callers
        item_obj = RequirementItem(
            requirement_id=req.id,
            brand_name=req_brand or "General",
            product_model=data.product_details,
            requested_quantity=data.quantity or 1,
            expected_rate=Decimal(str(data.expected_value or 0)) / (data.quantity or 1),
            requested_amount=Decimal(str(data.expected_value or 0)),
            notes=data.notes,
        )
        session.add(item_obj)

    await session.commit()
    await session.refresh(req)

    return await _enrich_requirement_read(req, session)


async def get_requirement_by_id(
    requirement_id: uuid.UUID,
    session: AsyncSession,
) -> CustomerRequirementRead:
    res = await session.execute(
        select(CustomerRequirement).where(CustomerRequirement.id == requirement_id)
    )
    req = res.scalar_one_or_none()
    if req is None:
        raise BaseAPIException(
            status_code=404,
            detail="Requirement not found",
            error_code="REQUIREMENT_NOT_FOUND",
        )
    return await _enrich_requirement_read(req, session)


async def list_all_requirements(
    session: AsyncSession,
    brand: Optional[str] = None,
    status: Optional[str] = None,
    customer_id: Optional[uuid.UUID] = None,
    created_by: Optional[uuid.UUID] = None,
    follow_up_date: Optional[date] = None,
    search: Optional[str] = None,
    skip: int = 0,
    limit: int = 50,
) -> list[CustomerRequirementRead]:
    query = select(CustomerRequirement).order_by(CustomerRequirement.created_at.desc())

    if customer_id:
        query = query.where(CustomerRequirement.customer_id == customer_id)
    if created_by:
        query = query.where(CustomerRequirement.created_by == created_by)
    if brand:
        query = query.where(CustomerRequirement.brand.ilike(f"%{brand}%"))
    if follow_up_date:
        query = query.where(CustomerRequirement.follow_up_date == follow_up_date)

    if status and status.upper() != "ALL":
        target_status = status.upper()
        if target_status in ("PENDING", "NEW"):
            query = query.where(
                or_(
                    CustomerRequirement.status == "PENDING",
                    CustomerRequirement.status == "NEW",
                    CustomerRequirement.status == "OPEN",
                    CustomerRequirement.status == "UNDER_REVIEW",
                )
            )
        else:
            query = query.where(CustomerRequirement.status == target_status)

    if search and search.strip():
        term = f"%{search.strip()}%"
        query = query.join(Customer, CustomerRequirement.customer_id == Customer.id, isouter=True)
        query = query.where(
            or_(
                CustomerRequirement.product_details.ilike(term),
                CustomerRequirement.notes.ilike(term),
                CustomerRequirement.brand.ilike(term),
                Customer.name.ilike(term),
            )
        )

    query = query.offset(skip).limit(limit)
    res = await session.execute(query)
    reqs = res.scalars().all()
    return [await _enrich_requirement_read(r, session) for r in reqs]


async def decide_requirement(
    requirement_id: uuid.UUID,
    decision: RequirementDecisionRequest,
    admin_user: User,
    session: AsyncSession,
) -> CustomerRequirementRead:
    """
    Admin decision on requirement: Approve, Partially Approve, Reject, or Line-by-Line review.
    Calculates requested vs approved vs unapproved amounts.
    """
    res = await session.execute(
        select(CustomerRequirement).where(CustomerRequirement.id == requirement_id)
    )
    req = res.scalar_one_or_none()
    if req is None:
        raise BaseAPIException(
            status_code=404,
            detail="Requirement not found",
            error_code="REQUIREMENT_NOT_FOUND",
        )

    action = decision.action
    now_utc = datetime.now(timezone.utc)

    # Fetch existing items
    it_res = await session.execute(
        select(RequirementItem).where(RequirementItem.requirement_id == req.id)
    )
    existing_items = it_res.scalars().all()
    item_map = {item.id: item for item in existing_items}

    # If decision specifies line items, apply them
    if decision.items:
        for it_dec in decision.items:
            if it_dec.id in item_map:
                it_obj = item_map[it_dec.id]
                it_obj.approved_quantity = it_dec.approved_quantity
                if it_dec.approved_rate is not None:
                    it_obj.approved_rate = Decimal(str(it_dec.approved_rate))
                else:
                    it_obj.approved_rate = it_obj.expected_rate

                if it_obj.approved_quantity is not None:
                    it_obj.approved_amount = Decimal(str(it_obj.approved_quantity)) * it_obj.approved_rate

                if it_dec.tally_stock_item_name:
                    it_obj.tally_stock_item_name = it_dec.tally_stock_item_name
                if it_dec.notes:
                    it_obj.notes = it_dec.notes

    # Compute totals
    total_approved = Decimal("0.00")
    total_approved_qty = 0
    for item in existing_items:
        if item.approved_quantity is not None and item.approved_quantity > 0:
            rate = item.approved_rate if item.approved_rate is not None else item.expected_rate
            amt = item.approved_amount if item.approved_amount is not None else (Decimal(str(item.approved_quantity)) * rate)
            total_approved += amt
            total_approved_qty += item.approved_quantity

    if action == RequirementDecisionAction.APPROVE:
        req.status = "APPROVED"
        if not decision.items and existing_items:
            # Auto-approve all line items as requested
            for it in existing_items:
                it.approved_quantity = it.requested_quantity
                it.approved_rate = it.expected_rate
                it.approved_amount = it.requested_amount
            total_approved = sum(it.requested_amount for it in existing_items)
            total_approved_qty = sum(it.requested_quantity for it in existing_items)

        req.approved_quantity = total_approved_qty or req.quantity
        req.approved_value = float(total_approved) if total_approved > 0 else req.expected_value
        req.total_approved_value = total_approved if total_approved > 0 else Decimal(str(req.expected_value or 0))

    elif action == RequirementDecisionAction.PARTIALLY_APPROVE:
        req.status = "PARTIALLY_APPROVED"
        req.approved_quantity = total_approved_qty or decision.approved_quantity
        req.approved_value = float(total_approved) if total_approved > 0 else decision.approved_value
        req.total_approved_value = total_approved if total_approved > 0 else (Decimal(str(decision.approved_value)) if decision.approved_value else None)

    elif action == RequirementDecisionAction.REJECT:
        req.status = "REJECTED"
        req.approved_quantity = 0
        req.approved_value = 0.0
        req.total_approved_value = Decimal("0.00")
        for it in existing_items:
            it.approved_quantity = 0
            it.approved_amount = Decimal("0.00")

    if decision.admin_notes:
        req.admin_notes = decision.admin_notes.strip()
    req.decided_by = admin_user.id
    req.decided_at = now_utc

    await session.commit()
    await session.refresh(req)
    return await _enrich_requirement_read(req, session)


async def confirm_and_create_order(
    requirement_id: uuid.UUID,
    payload: Optional[RequirementConfirmOrderRequest],
    admin_user: User,
    session: AsyncSession,
) -> OrderRead:
    """
    Converts an approved/partially-approved CustomerRequirement into a formal confirmed Order,
    and enqueues a CREATE_SALES_ORDER write-back job in tally_writeback_queue.
    """
    res = await session.execute(
        select(CustomerRequirement).where(CustomerRequirement.id == requirement_id)
    )
    req = res.scalar_one_or_none()
    if req is None:
        raise BaseAPIException(
            status_code=404,
            detail="Requirement not found",
            error_code="REQUIREMENT_NOT_FOUND",
        )

    # Load items
    it_res = await session.execute(
        select(RequirementItem).where(RequirementItem.requirement_id == req.id)
    )
    items = it_res.scalars().all()

    # If payload contains overrides, apply them first
    if payload and payload.items:
        it_map = {it.id: it for it in items}
        for it_dec in payload.items:
            if it_dec.id in it_map:
                it_obj = it_map[it_dec.id]
                it_obj.approved_quantity = it_dec.approved_quantity
                if it_dec.approved_rate is not None:
                    it_obj.approved_rate = Decimal(str(it_dec.approved_rate))
                if it_obj.approved_quantity is not None:
                    it_obj.approved_amount = Decimal(str(it_obj.approved_quantity)) * (it_obj.approved_rate or it_obj.expected_rate)
                if it_dec.tally_stock_item_name:
                    it_obj.tally_stock_item_name = it_dec.tally_stock_item_name

    # Filter to items with approved_quantity > 0
    approved_items = [
        it for it in items 
        if it.approved_quantity is not None and it.approved_quantity > 0
    ]

    # If no items were explicitly approved yet, fall back to requested items
    if not approved_items and items:
        for it in items:
            it.approved_quantity = it.requested_quantity
            it.approved_rate = it.expected_rate
            it.approved_amount = it.requested_amount
        approved_items = items

    if not approved_items:
        raise BaseAPIException(
            status_code=400,
            detail="Cannot confirm an order with 0 approved items.",
            error_code="NO_APPROVED_ITEMS",
        )

    # Compute order total
    order_total = Decimal("0.00")
    for it in approved_items:
        order_total += it.approved_amount or (Decimal(str(it.approved_quantity)) * (it.approved_rate or it.expected_rate))

    # Generate sequential unique order number
    now_ts = datetime.now()
    order_number = f"SO-{now_ts.strftime('%Y%m%d')}-{str(uuid.uuid4())[:4].upper()}"

    # Resolve customer & employee
    cust_res = await session.execute(select(Customer).where(Customer.id == req.customer_id))
    customer = cust_res.scalar_one_or_none()
    if customer is None:
        raise BaseAPIException(status_code=404, detail="Customer not found")

    employee_id = None
    if req.visit_id:
        v_res = await session.execute(select(Visit).where(Visit.id == req.visit_id))
        visit = v_res.scalar_one_or_none()
        if visit:
            employee_id = visit.employee_id

    # Create Order
    order = Order(
        order_number=order_number,
        customer_id=req.customer_id,
        requirement_id=req.id,
        visit_id=req.visit_id,
        employee_id=employee_id,
        total_amount=order_total,
        status="PENDING_TALLY",
        admin_notes=payload.admin_notes if payload else None,
        created_by=admin_user.id,
    )
    session.add(order)
    await session.flush()

    # Create OrderItems
    order_item_payloads = []
    for it in approved_items:
        qty = it.approved_quantity or it.requested_quantity
        rate = it.approved_rate or it.expected_rate
        amount = it.approved_amount or (Decimal(str(qty)) * rate)
        stock_item = it.tally_stock_item_name or f"{it.brand_name} {it.product_model}"

        order_item = OrderItem(
            order_id=order.id,
            brand_name=it.brand_name,
            product_model=it.product_model,
            stock_item_name=stock_item,
            quantity=qty,
            unit="PCS",
            rate=rate,
            amount=amount,
        )
        session.add(order_item)
        order_item_payloads.append({
            "stock_item_name": stock_item,
            "brand_name": it.brand_name,
            "product_model": it.product_model,
            "quantity": qty,
            "unit": "PCS",
            "rate": float(rate),
            "amount": float(amount),
        })

    # Update requirement status
    req.status = "CONVERTED_TO_ORDER"
    req.total_approved_value = order_total

    # Enqueue Tally Writeback Job
    writeback_payload = {
        "order_id": str(order.id),
        "order_number": order.order_number,
        "customer_id": str(order.customer_id),
        "customer_name": customer.name,
        "order_date": now_ts.strftime("%Y-%m-%d"),
        "total_amount": float(order_total),
        "items": order_item_payloads,
    }

    idempotency_key = f"so_writeback_{order.id}"
    wb_job = TallyWritebackQueue(
        idempotency_key=idempotency_key,
        entity_type="SALES_ORDER",
        entity_id=order.id,
        operation="CREATE",
        payload=writeback_payload,
        status=WritebackStatus.PENDING,
    )
    session.add(wb_job)

    await session.commit()
    await session.refresh(order)

    # Return OrderRead
    order_items_res = await session.execute(
        select(OrderItem).where(OrderItem.order_id == order.id)
    )
    saved_items = order_items_res.scalars().all()

    emp_name = None
    if order.employee_id:
        emp_res = await session.execute(select(Employee).where(Employee.id == order.employee_id))
        emp = emp_res.scalar_one_or_none()
        if emp:
            emp_name = emp.full_name

    return OrderRead(
        id=order.id,
        order_number=order.order_number,
        customer_id=order.customer_id,
        customer_name=customer.name,
        outlet_code=customer.outlet_code,
        requirement_id=order.requirement_id,
        visit_id=order.visit_id,
        employee_id=order.employee_id,
        employee_name=emp_name,
        total_amount=float(order.total_amount),
        status=order.status,
        tally_guid=order.tally_guid,
        tally_master_id=order.tally_master_id,
        tally_voucher_number=order.tally_voucher_number,
        admin_notes=order.admin_notes,
        created_by=order.created_by,
        creator_name=admin_user.email,
        created_at=order.created_at,
        updated_at=order.updated_at,
        items=[
            OrderItemRead(
                id=oi.id,
                order_id=oi.order_id,
                brand_name=oi.brand_name,
                product_model=oi.product_model,
                stock_item_name=oi.stock_item_name,
                quantity=oi.quantity,
                unit=oi.unit,
                rate=float(oi.rate),
                amount=float(oi.amount),
                created_at=oi.created_at,
            )
            for oi in saved_items
        ],
    )


async def list_orders(
    session: AsyncSession,
    customer_id: Optional[uuid.UUID] = None,
    status: Optional[str] = None,
    skip: int = 0,
    limit: int = 50,
) -> list[OrderRead]:
    query = select(Order).order_by(Order.created_at.desc())
    if customer_id:
        query = query.where(Order.customer_id == customer_id)
    if status and status.upper() != "ALL":
        query = query.where(Order.status == status.upper())

    query = query.offset(skip).limit(limit)
    res = await session.execute(query)
    orders = res.scalars().all()

    results = []
    for o in orders:
        cust_res = await session.execute(select(Customer).where(Customer.id == o.customer_id))
        cust = cust_res.scalar_one_or_none()
        
        items_res = await session.execute(select(OrderItem).where(OrderItem.order_id == o.id))
        ois = items_res.scalars().all()

        emp_name = None
        if o.employee_id:
            emp_res = await session.execute(select(Employee).where(Employee.id == o.employee_id))
            emp = emp_res.scalar_one_or_none()
            if emp:
                emp_name = emp.full_name

        user_res = await session.execute(select(User).where(User.id == o.created_by))
        user = user_res.scalar_one_or_none()

        results.append(
            OrderRead(
                id=o.id,
                order_number=o.order_number,
                customer_id=o.customer_id,
                customer_name=cust.name if cust else None,
                outlet_code=cust.outlet_code if cust else None,
                requirement_id=o.requirement_id,
                visit_id=o.visit_id,
                employee_id=o.employee_id,
                employee_name=emp_name,
                total_amount=float(o.total_amount),
                status=o.status,
                tally_guid=o.tally_guid,
                tally_master_id=o.tally_master_id,
                tally_voucher_number=o.tally_voucher_number,
                admin_notes=o.admin_notes,
                created_by=o.created_by,
                creator_name=user.email if user else None,
                created_at=o.created_at,
                updated_at=o.updated_at,
                items=[
                    OrderItemRead(
                        id=oi.id,
                        order_id=oi.order_id,
                        brand_name=oi.brand_name,
                        product_model=oi.product_model,
                        stock_item_name=oi.stock_item_name,
                        quantity=oi.quantity,
                        unit=oi.unit,
                        rate=float(oi.rate),
                        amount=float(oi.amount),
                        created_at=oi.created_at,
                    )
                    for oi in ois
                ],
            )
        )

    return results


async def update_requirement(
    requirement_id: uuid.UUID,
    data: CustomerRequirementUpdate,
    session: AsyncSession,
) -> CustomerRequirementRead:
    res = await session.execute(
        select(CustomerRequirement).where(CustomerRequirement.id == requirement_id)
    )
    req = res.scalar_one_or_none()
    if req is None:
        raise BaseAPIException(
            status_code=404,
            detail="Requirement not found",
            error_code="REQUIREMENT_NOT_FOUND",
        )

    if data.brand is not None:
        req.brand = data.brand
    if data.requirement_type is not None:
        req.requirement_type = data.requirement_type
    if data.product_details is not None:
        req.product_details = data.product_details
    if data.quantity is not None:
        req.quantity = data.quantity
    if data.expected_value is not None:
        req.expected_value = data.expected_value
        req.total_requested_value = Decimal(str(data.expected_value))
    if data.follow_up_date is not None:
        req.follow_up_date = data.follow_up_date
    if data.notes is not None:
        req.notes = data.notes
    if data.status is not None:
        req.status = data.status

    await session.commit()
    await session.refresh(req)
    return await _enrich_requirement_read(req, session)


async def attach_requirement_photo(
    requirement_id: uuid.UUID,
    file_bytes: bytes,
    filename: str,
    current_user: User,
    session: AsyncSession,
) -> CustomerRequirementRead:
    res = await session.execute(
        select(CustomerRequirement).where(CustomerRequirement.id == requirement_id)
    )
    req = res.scalar_one_or_none()
    if req is None:
        raise BaseAPIException(
            status_code=404,
            detail="Requirement not found",
            error_code="REQUIREMENT_NOT_FOUND",
        )

    mime_type, _ = mimetypes.guess_type(filename)
    if not mime_type or not mime_type.startswith("image/"):
        mime_type = "image/jpeg"

    # Auto-compress image to standard <500KB JPEG
    from app.services.media_service import _compress_image
    compressed_bytes = _compress_image(file_bytes)
    storage_key = f"requirements/{req.id}/{uuid.uuid4()}.jpg"

    await storage_service.upload_file(
        storage_key=storage_key,
        data=compressed_bytes,
        content_type="image/jpeg",
    )

    req.photo_storage_key = storage_key
    await session.commit()
    await session.refresh(req)
    return await _enrich_requirement_read(req, session)
