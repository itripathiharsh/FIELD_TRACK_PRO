from __future__ import annotations

import secrets
import time
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import delete, select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import tally_audit_service

from app.core.security import hash_password
from app.models.brand import Brand
from app.models.customer import Customer
from app.models.customer_brand import CustomerBrand
from app.models.employee import Employee
from app.models.invoice import Invoice, InvoiceSource, financial_year_of
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
from app.models.user import Role, User, ADMIN_ROLES
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
    stmt = select(User.id).where(User.role.in_(ADMIN_ROLES), User.is_active == True).limit(1)
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
    agent.tally_status = data.tally_status or "OFFLINE"
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

    today_summary = await tally_audit_service.get_today_summary(session)

    if not agent:
        return TallyIntegrationStatusResponse(
            is_connected=False,
            agent_status="NOT_CONFIGURED",
            tally_status="OFFLINE",
            today_read_count=today_summary["today_read_count"],
            today_write_count=today_summary["today_write_count"],
            failed_operation_count=today_summary["failed_operation_count"],
            last_successful_sync_at=today_summary["last_successful_sync_at"],
            total_invoices_synced=total_inv,
            total_payments_synced=total_pay,
            total_customers_synced=total_cust,
            message="No Tally Sync Agent is registered.",
        )

    now = datetime.now(timezone.utc)
    # Heartbeat considered online if received within last 3 minutes (180s)
    is_agent_online = False
    if agent.last_heartbeat_at:
        diff = (now - agent.last_heartbeat_at).total_seconds()
        if diff <= 180:
            is_agent_online = True

    # TallyPrime is only considered online if the agent is active AND reporting Tally running
    tally_status_val = (agent.tally_status or "OFFLINE").upper()
    is_tally_online = is_agent_online and (tally_status_val in ["RUNNING", "ONLINE", "CONNECTED"])

    if is_tally_online:
        msg = "TallyPrime live & bi-directional sync operational."
    elif is_agent_online:
        msg = "Sync Agent online, but local TallyPrime application is closed / port 9000 unreachable."
    else:
        msg = "Tally Sync Agent offline or waiting for heartbeat."

    return TallyIntegrationStatusResponse(
        is_connected=is_tally_online,
        agent_status="ONLINE" if is_agent_online else "OFFLINE",
        tally_status="ONLINE" if is_tally_online else "OFFLINE",
        agent_id=agent.id,
        agent_name=agent.name,
        agent_version=agent.agent_version,
        tally_company_name=agent.tally_company_name,
        tally_company_guid=agent.tally_company_guid,
        last_heartbeat_at=agent.last_heartbeat_at,
        last_sync_at=agent.last_sync_at,
        last_successful_sync_at=today_summary["last_successful_sync_at"],
        today_read_count=today_summary["today_read_count"],
        today_write_count=today_summary["today_write_count"],
        failed_operation_count=today_summary["failed_operation_count"],
        total_invoices_synced=total_inv,
        total_payments_synced=total_pay,
        total_customers_synced=total_cust,
        message=msg,
    )


# ---------------------------------------------------------------------------
# Customer Sync
# ---------------------------------------------------------------------------

def _ledger_guid(source_reference: Optional[str]) -> Optional[str]:
    """The ledger's Tally GUID; the agent's name-based fallback ("TALLY_LEDGER_<name>",
    used only when Tally returned no GUID) is not an identity."""
    ref = (source_reference or "").strip()
    if not ref or ref.startswith("TALLY_LEDGER_"):
        return None
    return ref


def _ledger_details(item) -> dict:
    """Non-empty master fields from Tally, clipped to their column sizes."""
    raw = {
        "address": (item.address, None),
        "contact_number": (item.contact_number or item.mobile, 20),
        "contact_person": (item.contact_person, 150),
        "gst_number": (item.gst_number, 20),
        "email": (item.email, 255),
        "mobile_number": (item.mobile, 50),
    }
    out = {}
    for attr, (value, size) in raw.items():
        value = (value or "").strip()
        if value:
            out[attr] = value[:size] if size else value
    return out


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
    start_time = time.time()
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
                guid = _ledger_guid(item.source_reference)
                details = _ledger_details(item)

                # Match: Tally ledger GUID (survives renames) -> outlet code -> exact name.
                existing_cust: Optional[Customer] = None
                matched_by_guid = False
                if guid:
                    existing_cust = (await session.execute(
                        select(Customer).where(Customer.tally_guid == guid)
                    )).scalar_one_or_none()
                    matched_by_guid = existing_cust is not None
                if not existing_cust and clean_code:
                    stmt = select(Customer).where(Customer.outlet_code == clean_code)
                    existing_cust = (await session.execute(stmt)).scalar_one_or_none()

                if not existing_cust:
                    stmt_name = select(Customer).where(func.lower(Customer.name) == cust_name.lower())
                    existing_cust = (await session.execute(stmt_name)).scalar_one_or_none()

                if existing_cust:
                    if guid and not existing_cust.tally_guid:
                        existing_cust.tally_guid = guid
                    if matched_by_guid and existing_cust.name != cust_name:
                        existing_cust.name = cust_name  # ledger renamed in Tally
                    if clean_code and not existing_cust.outlet_code:
                        existing_cust.outlet_code = clean_code
                    # Tally is authoritative for the ledger's master details: a value
                    # Tally has replaces the stored one; an empty Tally field changes nothing.
                    for attr, value in details.items():
                        setattr(existing_cust, attr, value)
                    # The outlet now exists in Tally: the manual-entry reminder is done.
                    existing_cust.needs_tally_entry = False
                    customer_obj = existing_cust
                    updated_count += 1
                else:
                    customer_obj = Customer(
                        name=cust_name,
                        outlet_code=clean_code,
                        tally_guid=guid,
                        address=details.pop("address", ""),
                        contact_number=details.pop("contact_number", ""),
                        location_status="MISSING",
                        created_by=system_user_id,
                        **details,
                    )
                    session.add(customer_obj)
                    await session.flush()
                    created_count += 1

                if item.closing_balance is not None:
                    customer_obj.tally_closing_balance = item.closing_balance
                    customer_obj.tally_closing_balance_at = datetime.now(timezone.utc)

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

    duration_ms = int((time.time() - start_time) * 1000)
    audit_status = "SUCCESS" if failed_count == 0 else ("PARTIAL" if (created_count > 0 or updated_count > 0) else "FAILED")
    err_msg = "; ".join([e.error for e in errors[:3]]) if errors else None
    await tally_audit_service.record_read_audit(
        session=session,
        agent=agent,
        operation="SYNC_CUSTOMERS",
        entity_type="CUSTOMERS",
        record_count=len(batch.customers),
        status=audit_status,
        duration_ms=duration_ms,
        error_message=err_msg,
        details={
            "batch_id": batch.batch_id,
            "created_count": created_count,
            "updated_count": updated_count,
            "failed_count": failed_count,
        },
    )

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
    start_time = time.time()
    system_user_id = await _get_system_user_id(session)
    created_count = 0
    updated_count = 0
    failed_count = 0
    relabelled_count = 0
    moved_count = 0
    errors: list[SyncErrorDetail] = []

    for item in batch.invoices:
        try:
            # SAVEPOINT per invoice: one bad voucher (e.g. a database constraint error)
            # fails on its own instead of aborting the whole batch.
            async with session.begin_nested():
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

                # Find existing invoice: the Tally voucher GUID is its identity. A
                # (customer, number) match is only accepted for a row that has no GUID
                # yet (a legacy copy) - never one carrying a different voucher's GUID,
                # so a number reused in a later financial year is a new invoice.
                existing_inv: Optional[Invoice] = None
                if item.source_reference:
                    ref_stmt = select(Invoice).where(Invoice.source_reference == item.source_reference)
                    existing_inv = (await session.execute(ref_stmt)).scalar_one_or_none()
                if not existing_inv:
                    inv_stmt = select(Invoice).where(
                        Invoice.customer_id == customer.id,
                        Invoice.invoice_number == inv_num,
                        Invoice.financial_year == financial_year_of(item.invoice_date),
                        or_(Invoice.source_reference.is_(None), Invoice.source_reference == (item.source_reference or "")),
                    )
                    existing_inv = (await session.execute(inv_stmt)).scalars().first()

                if existing_inv:
                    # The voucher's party was changed in Tally: the invoice follows it.
                    moved = existing_inv.customer_id != customer.id
                    existing_inv.customer_id = customer.id
                    # Tally now owns this row: an earlier non-Tally copy (manual /
                    # import) must not keep claiming that origin.
                    relabelled = existing_inv.source != InvoiceSource.TALLY
                    existing_inv.source = InvoiceSource.TALLY
                    # Tally's due date replaces whatever was stored (including an earlier
                    # agent default); None means Tally gives none.
                    existing_inv.due_date = item.due_date
                    existing_inv.invoice_date = item.invoice_date
                    existing_inv.invoice_number = inv_num
                    existing_inv.tally_bill_name = item.bill_name
                    existing_inv.amount = item.amount
                    if canonical_brand:
                        existing_inv.brand = canonical_brand
                        existing_inv.brand_id = brand_id_val
                    if item.imported_outstanding_amount is not None:
                        existing_inv.imported_outstanding_amount = item.imported_outstanding_amount
                    if item.source_reference:
                        existing_inv.source_reference = item.source_reference
                    await session.flush()
                    updated_count += 1
                    moved_count += int(moved)
                    relabelled_count += int(relabelled)
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
                        tally_bill_name=item.bill_name,
                        imported_outstanding_amount=item.imported_outstanding_amount,
                        created_by=system_user_id,
                    )
                    session.add(new_inv)
                    await session.flush()
                    created_count += 1

        except Exception as ex:
            failed_count += 1
            errors.append(SyncErrorDetail(identifier=item.invoice_number, error=str(ex)))

    agent.last_sync_at = datetime.now(timezone.utc)
    await session.commit()

    duration_ms = int((time.time() - start_time) * 1000)
    audit_status = "SUCCESS" if failed_count == 0 else ("PARTIAL" if (created_count > 0 or updated_count > 0) else "FAILED")
    err_msg = "; ".join([e.error for e in errors[:3]]) if errors else None
    await tally_audit_service.record_read_audit(
        session=session,
        agent=agent,
        operation="SYNC_INVOICES",
        entity_type="INVOICES",
        record_count=len(batch.invoices),
        status=audit_status,
        duration_ms=duration_ms,
        error_message=err_msg,
        details={
            "batch_id": batch.batch_id,
            "created_count": created_count,
            "updated_count": updated_count,
            "failed_count": failed_count,
            "relabelled_to_tally_count": relabelled_count,
            "moved_to_other_party_count": moved_count,
        },
    )

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
    start_time = time.time()
    system_user_id = await _get_system_user_id(session)
    system_emp_id = await _get_system_employee_id(session)
    created_count = 0
    updated_count = 0
    failed_count = 0
    relabelled_count = 0
    replaced_allocation_count = 0
    unresolved_bill_count = 0
    unresolved_bill_amount = Decimal("0.00")
    unallocated_count = 0
    unallocated_amount = Decimal("0.00")
    guessed_links_removed = 0
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
                # Update existing. A legacy import row is now owned by Tally. A
                # MANUAL field collection read back via write-back stays MANUAL:
                # it is the employee's operational record of the same money.
                if existing_payment.source not in (PaymentSource.TALLY, PaymentSource.MANUAL):
                    existing_payment.source = PaymentSource.TALLY
                    relabelled_count += 1
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

            # Bill allocations: Tally's own bill-wise settlement replaces every earlier
            # (guessed FIFO or older Tally) link of this receipt - once validated. Only
            # this sync creates these rows, so nothing user-entered is touched; the
            # payment row and its amount are never changed by this step.
            if item.bill_allocations:
                alloc_total = sum((b.amount for b in item.bill_allocations), Decimal("0.00"))
                if alloc_total - item.amount > Decimal("0.01"):
                    errors.append(SyncErrorDetail(
                        identifier=item.source_reference,
                        error=f"Bill allocations ({alloc_total}) exceed the receipt amount ({item.amount}); "
                              "existing allocations kept unchanged.",
                    ))
                else:
                    await session.execute(
                        delete(PaymentInvoiceAllocation).where(PaymentInvoiceAllocation.payment_id == payment_obj.id)
                    )
                    resolved: dict[uuid.UUID, Decimal] = {}
                    names: dict[uuid.UUID, tuple[str, Optional[str]]] = {}
                    for b_alloc in item.bill_allocations:
                        name = b_alloc.bill_name.strip()
                        if (b_alloc.bill_type or "").strip().lower() in ("on account", "advance"):
                            continue  # Tally itself keeps this part unapplied to any bill
                        target_inv = (await session.execute(
                            select(Invoice).where(
                                Invoice.customer_id == customer.id,
                                Invoice.source == InvoiceSource.TALLY,
                                or_(
                                    Invoice.tally_bill_name == name,
                                    func.lower(Invoice.invoice_number) == name.lower(),
                                    Invoice.source_reference == name,
                                ),
                            ).order_by(Invoice.invoice_date.desc())
                        )).scalars().first()
                        if target_inv is None:
                            # A bill not in Field Track Pro (e.g. dated before the sync
                            # start, part of the opening balance) or on-account money:
                            # deliberately NOT re-assigned to some other invoice.
                            unresolved_bill_count += 1
                            unresolved_bill_amount += b_alloc.amount
                            continue
                        resolved[target_inv.id] = resolved.get(target_inv.id, Decimal("0.00")) + b_alloc.amount
                        names[target_inv.id] = (name, b_alloc.bill_type)
                    for inv_id, amt in resolved.items():
                        bill_name, bill_type = names[inv_id]
                        session.add(PaymentInvoiceAllocation(
                            payment_id=payment_obj.id,
                            invoice_id=inv_id,
                            bill_name=bill_name,
                            bill_type=bill_type or "Agst Ref",
                            allocated_amount=amt,
                        ))
                    payment_obj.invoice_id = next(iter(resolved)) if len(resolved) == 1 else None
                    replaced_allocation_count += 1
            else:
                # Tally has no bill-wise allocation for this receipt: it stays
                # unallocated (no guessed oldest-first links) and is reported for
                # reconciliation. It still counts against the outlet's balance as
                # on-account money (account_position). Any earlier guessed link of
                # this receipt is removed - only this sync creates these rows.
                removed = (await session.execute(
                    delete(PaymentInvoiceAllocation).where(PaymentInvoiceAllocation.payment_id == payment_obj.id)
                )).rowcount or 0
                if removed:
                    guessed_links_removed += removed
                if payment_obj.source == PaymentSource.TALLY:
                    payment_obj.invoice_id = None
                unallocated_count += 1
                unallocated_amount += item.amount

        except Exception as ex:
            failed_count += 1
            errors.append(SyncErrorDetail(identifier=item.source_reference, error=str(ex)))

    agent.last_sync_at = datetime.now(timezone.utc)
    await session.commit()

    duration_ms = int((time.time() - start_time) * 1000)
    audit_status = "SUCCESS" if failed_count == 0 else ("PARTIAL" if (created_count > 0 or updated_count > 0) else "FAILED")
    err_msg = "; ".join([e.error for e in errors[:3]]) if errors else None
    await tally_audit_service.record_read_audit(
        session=session,
        agent=agent,
        operation="SYNC_PAYMENTS",
        entity_type="PAYMENTS",
        record_count=len(batch.payments),
        status=audit_status,
        duration_ms=duration_ms,
        error_message=err_msg,
        details={
            "batch_id": batch.batch_id,
            "created_count": created_count,
            "updated_count": updated_count,
            "failed_count": failed_count,
            "relabelled_to_tally_count": relabelled_count,
            "bill_allocations_replaced_count": replaced_allocation_count,
            "unresolved_bill_count": unresolved_bill_count,
            "unresolved_bill_amount": str(unresolved_bill_amount),
            "receipts_without_bill_allocation_count": unallocated_count,
            "receipts_without_bill_allocation_amount": str(unallocated_amount),
            "guessed_links_removed": guessed_links_removed,
        },
    )

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
