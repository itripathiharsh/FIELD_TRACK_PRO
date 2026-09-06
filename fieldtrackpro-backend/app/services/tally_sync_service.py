from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.brand import Brand
from app.models.customer import Customer
from app.models.customer_brand import CustomerBrand
from app.models.employee import Employee
from app.models.invoice import Invoice, InvoiceSource
from app.models.payment import (
    Payment,
    PaymentBrandAllocation,
    PaymentMethod,
    PaymentSource,
    PaymentStatus,
)
from app.models.payment_invoice_allocation import PaymentInvoiceAllocation
from app.models.sync_agent import SyncAgent
from app.models.territory import Territory
from app.models.area import Area
from app.models.user import Role, User
from app.schemas.tally_sync import (
    CustomerSyncBatch,
    HeartbeatRequest,
    HeartbeatResponse,
    InvoiceSyncBatch,
    PaymentSyncBatch,
    SyncAgentCreate,
    SyncErrorDetail,
    SyncResultResponse,
    TallyIntegrationStatusResponse,
)
from app.services.brand_service import ensure_brand, resolve_brand, resolve_canonical_brand_name


async def _get_system_user_id(session: AsyncSession) -> uuid.UUID:
    """Resolve an active ADMIN user ID to satisfy created_by foreign keys for automated sync."""
    stmt = select(User.id).where(User.role == Role.ADMIN, User.is_active == True).limit(1)
    admin_id = (await session.execute(stmt)).scalar_one_or_none()
    if admin_id:
        return admin_id

    # Fallback to any active user if no admin exists
    any_stmt = select(User.id).where(User.is_active == True).limit(1)
    any_id = (await session.execute(any_stmt)).scalar_one_or_none()
    if any_id:
        return any_id

    raise RuntimeError("No active user found in database to attribute automated sync records.")


async def _get_system_employee_id(session: AsyncSession) -> Optional[uuid.UUID]:
    """Resolve an employee ID to satisfy payment employee_id foreign key if any exists."""
    stmt = (
        select(Employee.id)
        .join(User, Employee.user_id == User.id)
        .where(User.is_active == True)
        .limit(1)
    )
    emp_id = (await session.execute(stmt)).scalar_one_or_none()
    if emp_id:
        return emp_id

    any_emp_stmt = select(Employee.id).limit(1)
    any_emp = (await session.execute(any_emp_stmt)).scalar_one_or_none()
    return any_emp


# ---------------------------------------------------------------------------
# Agent Registration & Heartbeat
# ---------------------------------------------------------------------------

async def register_agent(data: SyncAgentCreate, session: AsyncSession) -> tuple[SyncAgent, str]:
    """
    Registers a new sync agent, generating a one-time high-entropy raw secret key.
    Stores the bcrypt hash in the database.
    """
    raw_key = f"ft_agent_{secrets.token_urlsafe(32)}"
    key_hash = hash_password(raw_key)

    agent = SyncAgent(
        name=data.name,
        organization_id=data.organization_id,
        api_key_hash=key_hash,
        tally_company_guid=data.tally_company_guid,
        tally_company_name=data.tally_company_name,
        is_active=True,
    )
    session.add(agent)
    await session.commit()
    await session.refresh(agent)
    return agent, raw_key


async def record_heartbeat(
    agent: SyncAgent, data: HeartbeatRequest, session: AsyncSession
) -> HeartbeatResponse:
    """Updates agent liveness, version, and optional company metadata."""
    now = datetime.now(timezone.utc)
    agent.last_heartbeat_at = now
    agent.agent_version = data.agent_version
    if data.company_name:
        agent.tally_company_name = data.company_name
    if data.company_guid:
        agent.tally_company_guid = data.company_guid

    await session.commit()
    return HeartbeatResponse(
        status="OK",
        server_time=now,
        agent_id=agent.id,
        organization_id=agent.organization_id,
    )


async def get_integration_status(session: AsyncSession) -> TallyIntegrationStatusResponse:
    """Returns live connection, agent heartbeat, and sync statistics."""
    # Find latest active SyncAgent
    stmt = select(SyncAgent).order_by(SyncAgent.updated_at.desc()).limit(1)
    agent = (await session.execute(stmt)).scalar_one_or_none()

    # Query counts of Tally records
    inv_stmt = select(func.count(Invoice.id)).where(Invoice.source == InvoiceSource.TALLY)
    total_inv = (await session.execute(inv_stmt)).scalar() or 0

    pay_stmt = select(func.count(Payment.id)).where(Payment.source == PaymentSource.TALLY)
    total_pay = (await session.execute(pay_stmt)).scalar() or 0

    cust_stmt = select(func.count(Customer.id)).where(Customer.outlet_code.isnot(None))
    total_cust = (await session.execute(cust_stmt)).scalar() or 0

    if not agent:
        return TallyIntegrationStatusResponse(
            is_connected=False,
            agent_status="NOT_CONFIGURED",
            total_invoices_synced=total_inv,
            total_payments_synced=total_pay,
            total_customers_synced=total_cust,
            message="No Tally Sync Agent is registered.",
        )

    now = datetime.now(timezone.utc)
    # Heartbeat considered online if received within last 3 minutes (180s)
    is_online = False
    if agent.last_heartbeat_at:
        diff = (now - agent.last_heartbeat_at).total_seconds()
        if diff <= 180:
            is_online = True

    return TallyIntegrationStatusResponse(
        is_connected=is_online,
        agent_status="ONLINE" if is_online else "OFFLINE",
        agent_id=agent.id,
        agent_name=agent.name,
        agent_version=agent.agent_version,
        tally_company_name=agent.tally_company_name,
        tally_company_guid=agent.tally_company_guid,
        last_heartbeat_at=agent.last_heartbeat_at,
        last_sync_at=agent.last_sync_at,
        total_invoices_synced=total_inv,
        total_payments_synced=total_pay,
        total_customers_synced=total_cust,
        message="Tally Sync Agent active and communicating." if is_online else "Tally Sync Agent offline or waiting for heartbeat.",
    )


# ---------------------------------------------------------------------------
# Customer Sync
# ---------------------------------------------------------------------------

async def ensure_territory(session: AsyncSession, zone_name: str) -> Territory:
    clean_name = zone_name.strip().title()
    stmt = select(Territory).where(func.lower(Territory.name) == clean_name.lower())
    terr = (await session.execute(stmt)).scalar_one_or_none()
    if not terr:
        terr = Territory(name=clean_name, status="ACTIVE")
        session.add(terr)
        await session.flush()
    return terr


async def ensure_area(session: AsyncSession, area_name: str, territory_id: uuid.UUID) -> Area:
    clean_name = area_name.strip().title()
    stmt = select(Area).where(
        func.lower(Area.name) == clean_name.lower(),
        Area.territory_id == territory_id
    )
    area = (await session.execute(stmt)).scalar_one_or_none()
    if not area:
        area = Area(name=clean_name, territory_id=territory_id)
        session.add(area)
        await session.flush()
    return area


async def sync_customers(
    agent: SyncAgent, batch: CustomerSyncBatch, session: AsyncSession
) -> SyncResultResponse:
    """
    Idempotently upsert customer / outlet records from Tally Sundry Debtors.
    Matches primarily on outlet_code (DMS code) or clean name.
    """
    system_user_id = await _get_system_user_id(session)
    created_count = 0
    updated_count = 0
    failed_count = 0
    errors: list[SyncErrorDetail] = []

    for item in batch.customers:
        # Use a SAVEPOINT per record so a constraint error on one customer
        # (e.g. duplicate customer_brands entry) does not abort the whole
        # batch transaction.  The outer try/except catches any error that
        # leaks past the nested rollback.
        try:
            async with session.begin_nested():  # SAVEPOINT
                cust_name = item.name.strip()
                if not cust_name:
                    continue

                clean_code = item.outlet_code.strip() if item.outlet_code else None

                # Look for existing customer
                existing_cust: Optional[Customer] = None
                if clean_code:
                    stmt = select(Customer).where(Customer.outlet_code == clean_code)
                    existing_cust = (await session.execute(stmt)).scalar_one_or_none()

                if not existing_cust:
                    stmt_name = select(Customer).where(func.lower(Customer.name) == cust_name.lower())
                    existing_cust = (await session.execute(stmt_name)).scalar_one_or_none()

                if existing_cust:
                    # Update existing
                    if clean_code and not existing_cust.outlet_code:
                        existing_cust.outlet_code = clean_code
                    if item.address and not existing_cust.address:
                        existing_cust.address = item.address
                    if item.contact_number and not existing_cust.contact_number:
                        existing_cust.contact_number = item.contact_number
                    if item.contact_person and not existing_cust.contact_person:
                        existing_cust.contact_person = item.contact_person
                    if item.gst_number and not existing_cust.gst_number:
                        existing_cust.gst_number = item.gst_number
                    customer_obj = existing_cust
                    updated_count += 1
                else:
                    # Create new
                    customer_obj = Customer(
                        name=cust_name,
                        outlet_code=clean_code,
                        address=item.address or "",
                        contact_number=item.contact_number or "",
                        contact_person=item.contact_person,
                        gst_number=item.gst_number,
                        location_status="MISSING",
                        created_by=system_user_id,
                    )
                    session.add(customer_obj)
                    await session.flush()
                    created_count += 1

                # Resolve and attach Zone (Territory) & Area if provided
                if item.zone and item.zone.strip():
                    terr_obj = await ensure_territory(session, item.zone)
                    customer_obj.territory_id = terr_obj.id
                    if item.area and item.area.strip():
                        area_obj = await ensure_area(session, item.area, terr_obj.id)
                        customer_obj.area_id = area_obj.id

                # Resolve and attach Brand if provided
                if item.brand:
                    brand_obj = await ensure_brand(session, item.brand)
                    canonical_brand = brand_obj.name if brand_obj else resolve_canonical_brand_name(item.brand)
                    brand_id_val = brand_obj.id if brand_obj else None

                    cb_stmt = select(CustomerBrand).where(
                        CustomerBrand.customer_id == customer_obj.id,
                        CustomerBrand.brand == canonical_brand,
                    )
                    existing_cb = (await session.execute(cb_stmt)).scalar_one_or_none()
                    if not existing_cb:
                        new_cb = CustomerBrand(
                            customer_id=customer_obj.id,
                            brand=canonical_brand,
                            brand_id=brand_id_val,
                            is_active=True,
                        )
                        session.add(new_cb)
                        await session.flush()  # surface constraint errors inside SAVEPOINT

        except Exception as ex:
            failed_count += 1
            errors.append(SyncErrorDetail(identifier=item.name, error=str(ex)))

    agent.last_sync_at = datetime.now(timezone.utc)
    await session.commit()

    return SyncResultResponse(
        status="COMPLETED",
        batch_id=batch.batch_id,
        total_received=len(batch.customers),
        created_count=created_count,
        updated_count=updated_count,
        failed_count=failed_count,
        errors=errors,
    )


# ---------------------------------------------------------------------------
# Invoice Sync
# ---------------------------------------------------------------------------

async def sync_invoices(
    agent: SyncAgent, batch: InvoiceSyncBatch, session: AsyncSession
) -> SyncResultResponse:
    """
    Idempotently upsert Sales Invoices.
    Matches by (customer_id, invoice_number) or source_reference.
    """
    system_user_id = await _get_system_user_id(session)
    created_count = 0
    updated_count = 0
    failed_count = 0
    errors: list[SyncErrorDetail] = []

    for item in batch.invoices:
        try:
            inv_num = item.invoice_number.strip()
            cust_name = item.customer_name.strip()
            clean_code = item.outlet_code.strip() if item.outlet_code else None

            # Resolve customer
            customer: Optional[Customer] = None
            if clean_code:
                c_stmt = select(Customer).where(Customer.outlet_code == clean_code)
                customer = (await session.execute(c_stmt)).scalar_one_or_none()

            if not customer:
                c_stmt_name = select(Customer).where(func.lower(Customer.name) == cust_name.lower())
                customer = (await session.execute(c_stmt_name)).scalar_one_or_none()

            if not customer:
                # Auto-provision customer stub if not yet synced
                customer = Customer(
                    name=cust_name,
                    outlet_code=clean_code,
                    address="",
                    contact_number="",
                    location_status="MISSING",
                    created_by=system_user_id,
                )
                session.add(customer)
                await session.flush()

            # Resolve brand
            brand_id_val = None
            canonical_brand = None
            if item.brand:
                brand_obj = await ensure_brand(session, item.brand)
                canonical_brand = brand_obj.name if brand_obj else resolve_canonical_brand_name(item.brand)
                brand_id_val = brand_obj.id if brand_obj else None

            # Find existing invoice
            inv_stmt = select(Invoice).where(
                Invoice.customer_id == customer.id,
                Invoice.invoice_number == inv_num,
            )
            existing_inv = (await session.execute(inv_stmt)).scalar_one_or_none()

            if not existing_inv and item.source_reference:
                ref_stmt = select(Invoice).where(Invoice.source_reference == item.source_reference)
                existing_inv = (await session.execute(ref_stmt)).scalar_one_or_none()

            if existing_inv:
                # Update existing invoice
                existing_inv.due_date = item.due_date or existing_inv.due_date
                existing_inv.amount = item.amount
                if canonical_brand:
                    existing_inv.brand = canonical_brand
                    existing_inv.brand_id = brand_id_val
                if item.imported_outstanding_amount is not None:
                    existing_inv.imported_outstanding_amount = item.imported_outstanding_amount
                if item.source_reference:
                    existing_inv.source_reference = item.source_reference
                updated_count += 1
            else:
                # Create invoice
                new_inv = Invoice(
                    customer_id=customer.id,
                    invoice_number=inv_num,
                    invoice_date=item.invoice_date,
                    due_date=item.due_date,
                    amount=item.amount,
                    brand=canonical_brand,
                    brand_id=brand_id_val,
                    source=InvoiceSource.TALLY,
                    source_reference=item.source_reference,
                    imported_outstanding_amount=item.imported_outstanding_amount,
                    created_by=system_user_id,
                )
                session.add(new_inv)
                created_count += 1

        except Exception as ex:
            failed_count += 1
            errors.append(SyncErrorDetail(identifier=item.invoice_number, error=str(ex)))

    agent.last_sync_at = datetime.now(timezone.utc)
    await session.commit()

    try:
        from app.services.period_service import ensure_monthly_periods_synced
        await ensure_monthly_periods_synced(session)
    except Exception:
        pass

    return SyncResultResponse(
        status="COMPLETED",
        batch_id=batch.batch_id,
        total_received=len(batch.invoices),
        created_count=created_count,
        updated_count=updated_count,
        failed_count=failed_count,
        errors=errors,
    )


# ---------------------------------------------------------------------------
# Payment Sync
# ---------------------------------------------------------------------------

async def sync_payments(
    agent: SyncAgent, batch: PaymentSyncBatch, session: AsyncSession
) -> SyncResultResponse:
    """
    Idempotently upsert Receipt vouchers from Tally.
    Deduplicates strictly by source_reference.
    """
    system_user_id = await _get_system_user_id(session)
    system_emp_id = await _get_system_employee_id(session)
    created_count = 0
    updated_count = 0
    failed_count = 0
    errors: list[SyncErrorDetail] = []

    for item in batch.payments:
        try:
            cust_name = item.customer_name.strip()
            clean_code = item.outlet_code.strip() if item.outlet_code else None

            # Resolve customer
            customer: Optional[Customer] = None
            if clean_code:
                c_stmt = select(Customer).where(Customer.outlet_code == clean_code)
                customer = (await session.execute(c_stmt)).scalar_one_or_none()

            if not customer:
                c_stmt_name = select(Customer).where(func.lower(Customer.name) == cust_name.lower())
                customer = (await session.execute(c_stmt_name)).scalar_one_or_none()

            if not customer:
                customer = Customer(
                    name=cust_name,
                    outlet_code=clean_code,
                    address="",
                    contact_number="",
                    location_status="MISSING",
                    created_by=system_user_id,
                )
                session.add(customer)
                await session.flush()

            # Payment method parsing
            raw_method = (item.payment_method or "ONLINE").upper()
            if "CHEQUE" in raw_method or "CHECK" in raw_method:
                method = PaymentMethod.CHEQUE
            elif "CASH" in raw_method:
                method = PaymentMethod.CASH
            else:
                method = PaymentMethod.ONLINE

            # Match existing payment by source_reference
            p_stmt = select(Payment).where(Payment.source_reference == item.source_reference)
            existing_payment = (await session.execute(p_stmt)).scalar_one_or_none()

            # Loop Prevention Fallback: check if narration contains FT:{payment_id}
            if not existing_payment and item.notes:
                import re
                ft_match = re.search(r"FT:([0-9a-fA-F-]{36})", item.notes)
                if ft_match:
                    try:
                        ft_pid = uuid.UUID(ft_match.group(1))
                        p_stmt_ft = select(Payment).where(Payment.id == ft_pid)
                        existing_payment = (await session.execute(p_stmt_ft)).scalar_one_or_none()
                        if existing_payment:
                            existing_payment.source_reference = item.source_reference
                    except ValueError:
                        pass


            if existing_payment:
                # Update existing
                existing_payment.amount = item.amount
                existing_payment.payment_date = item.payment_date
                existing_payment.payment_method = method
                existing_payment.cheque_number = item.cheque_number
                existing_payment.cheque_bank_name = item.cheque_bank_name
                existing_payment.utr_reference = item.utr_reference
                payment_obj = existing_payment
                updated_count += 1
            else:
                # Create payment — employee_id is intentionally None for Tally
                # receipts: the column is nullable for TALLY/EXCEL_IMPORT sources.
                payment_obj = Payment(
                    customer_id=customer.id,
                    employee_id=None,  # No field employee for Tally receipts
                    amount=item.amount,
                    payment_method=method,
                    payment_date=item.payment_date,
                    cheque_number=item.cheque_number,
                    cheque_bank_name=item.cheque_bank_name,
                    utr_reference=item.utr_reference,
                    notes=item.notes or f"Tally Receipt {item.receipt_number or ''}".strip(),
                    status=PaymentStatus.VERIFIED,
                    source=PaymentSource.TALLY,
                    source_reference=item.source_reference,
                    created_by=system_user_id,
                )
                session.add(payment_obj)
                await session.flush()
                created_count += 1

            # Handle Brand Allocations
            if item.brand_allocations:
                for alloc in item.brand_allocations:
                    brand_obj = await ensure_brand(session, alloc.brand)
                    canonical_brand = brand_obj.name if brand_obj else resolve_canonical_brand_name(alloc.brand)
                    brand_id_val = brand_obj.id if brand_obj else None

                    alloc_stmt = select(PaymentBrandAllocation).where(
                        PaymentBrandAllocation.payment_id == payment_obj.id,
                        PaymentBrandAllocation.brand == canonical_brand,
                    )
                    existing_alloc = (await session.execute(alloc_stmt)).scalar_one_or_none()
                    if existing_alloc:
                        existing_alloc.allocated_amount = alloc.allocated_amount
                    else:
                        session.add(PaymentBrandAllocation(
                            payment_id=payment_obj.id,
                            brand=canonical_brand,
                            brand_id=brand_id_val,
                            allocated_amount=alloc.allocated_amount,
                        ))

            # Handle Bill Allocations (Explicit Agst Ref or Deterministic FIFO)
            if item.bill_allocations:
                for b_alloc in item.bill_allocations:
                    # Match invoice by invoice_number or source_reference for this customer
                    inv_match_stmt = select(Invoice).where(
                        Invoice.customer_id == customer.id,
                        or_(
                            func.lower(Invoice.invoice_number) == b_alloc.bill_name.strip().lower(),
                            Invoice.source_reference == b_alloc.bill_name.strip(),
                        ),
                    )
                    target_inv = (await session.execute(inv_match_stmt)).scalar_one_or_none()
                    if target_inv:
                        alloc_stmt = select(PaymentInvoiceAllocation).where(
                            PaymentInvoiceAllocation.payment_id == payment_obj.id,
                            PaymentInvoiceAllocation.invoice_id == target_inv.id,
                        )
                        existing_pia = (await session.execute(alloc_stmt)).scalar_one_or_none()
                        if existing_pia:
                            existing_pia.allocated_amount = b_alloc.amount
                            existing_pia.bill_name = b_alloc.bill_name
                            existing_pia.bill_type = b_alloc.bill_type
                        else:
                            session.add(PaymentInvoiceAllocation(
                                payment_id=payment_obj.id,
                                invoice_id=target_inv.id,
                                bill_name=b_alloc.bill_name,
                                bill_type=b_alloc.bill_type or "Agst Ref",
                                allocated_amount=b_alloc.amount,
                            ))
                        if len(item.bill_allocations) == 1:
                            payment_obj.invoice_id = target_inv.id
            else:
                # Deterministic account-level FIFO settlement for on-account receipts
                # Only allocate against open invoices belonging to this exact customer
                cust_inv_stmt = select(Invoice).where(
                    Invoice.customer_id == customer.id
                ).order_by(Invoice.invoice_date.asc(), Invoice.created_at.asc())
                cust_invoices = (await session.execute(cust_inv_stmt)).scalars().all()
                
                remaining_pay_amt = item.amount
                for inv in cust_invoices:
                    if remaining_pay_amt <= Decimal("0.00"):
                        break
                    alloc_sum_stmt = select(
                        func.coalesce(func.sum(PaymentInvoiceAllocation.allocated_amount), Decimal("0.00"))
                    ).where(
                        PaymentInvoiceAllocation.invoice_id == inv.id,
                        PaymentInvoiceAllocation.payment_id != payment_obj.id,
                    )
                    already_settled = (await session.execute(alloc_sum_stmt)).scalar() or Decimal("0.00")
                    inv_unpaid = max(inv.amount - already_settled, Decimal("0.00"))
                    if inv_unpaid > Decimal("0.00"):
                        settle_amt = min(remaining_pay_amt, inv_unpaid)
                        alloc_stmt = select(PaymentInvoiceAllocation).where(
                            PaymentInvoiceAllocation.payment_id == payment_obj.id,
                            PaymentInvoiceAllocation.invoice_id == inv.id,
                        )
                        existing_pia = (await session.execute(alloc_stmt)).scalar_one_or_none()
                        if existing_pia:
                            existing_pia.allocated_amount = settle_amt
                            existing_pia.bill_name = inv.invoice_number
                            existing_pia.bill_type = "FIFO_ON_ACCOUNT"
                        else:
                            session.add(PaymentInvoiceAllocation(
                                payment_id=payment_obj.id,
                                invoice_id=inv.id,
                                bill_name=inv.invoice_number,
                                bill_type="FIFO_ON_ACCOUNT",
                                allocated_amount=settle_amt,
                            ))
                        remaining_pay_amt -= settle_amt

        except Exception as ex:
            failed_count += 1
            errors.append(SyncErrorDetail(identifier=item.source_reference, error=str(ex)))

    agent.last_sync_at = datetime.now(timezone.utc)
    await session.commit()

    try:
        from app.services.period_service import ensure_monthly_periods_synced
        await ensure_monthly_periods_synced(session)
    except Exception:
        pass

    return SyncResultResponse(
        status="COMPLETED",
        batch_id=batch.batch_id,
        total_received=len(batch.payments),
        created_count=created_count,
        updated_count=updated_count,
        failed_count=failed_count,
        errors=errors,
    )
