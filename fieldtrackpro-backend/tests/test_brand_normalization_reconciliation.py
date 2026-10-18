from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
import pytest
from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.customer import Customer
from app.models.invoice import Invoice
from app.models.outlet_financial_snapshot import OutletFinancialSnapshot
from app.models.payment import Payment, PaymentBrandAllocation, PaymentMethod, PaymentStatus
from app.models.user import Role, User
from app.models.employee import Employee
from app.models.territory import Territory
from app.models.area import Area
from app.services import brand_service, account_service
from app.services.report_service import report_service


@pytest.mark.asyncio
async def test_brand_service_resolves_aliases():
    """Verify alias normalization across casing and abbreviations."""
    assert brand_service.resolve_canonical_brand_name("ZBR") == "Zebronics"
    assert brand_service.resolve_canonical_brand_name("zbr") == "Zebronics"
    assert brand_service.resolve_canonical_brand_name("Zebronics") == "Zebronics"
    assert brand_service.resolve_canonical_brand_name("zebronics") == "Zebronics"

    assert brand_service.resolve_canonical_brand_name("Usha") == "USHA"
    assert brand_service.resolve_canonical_brand_name("usha") == "USHA"
    assert brand_service.resolve_canonical_brand_name("USHA") == "USHA"

    assert brand_service.resolve_canonical_brand_name("VU") == "VU"
    assert brand_service.resolve_canonical_brand_name("vu") == "VU"


@pytest.mark.asyncio
async def test_report_service_brand_filter_matches_aliases():
    """
    Test:
    Snapshot brand in DB was normalized to 'Zebronics' (or alias 'ZBR').
    Report filter with brand='ZBR', 'zbr', 'Zebronics', or 'zebronics' returns the record.
    """
    async with AsyncSessionLocal() as session:
        admin_user = User(
            email=f"admin_{uuid.uuid4().hex[:6]}@fieldtrack.internal",
            password_hash="hash",
            role=Role.ADMIN,
        )
        session.add(admin_user)
        await session.flush()

        code_suffix = uuid.uuid4().hex[:6].lower()
        dms_code = f"DMS_{code_suffix}"
        cust = Customer(
            name=f"Brand Test Outlet {code_suffix}",
            outlet_code=dms_code,
            location_status="VERIFIED",
            created_by=admin_user.id,
        )
        session.add(cust)
        await session.flush()

        zeb_brand = await brand_service.get_brand_by_name(session, "Zebronics")
        assert zeb_brand is not None

        snap = OutletFinancialSnapshot(
            customer_id=cust.id,
            brand=zeb_brand.name,
            brand_id=zeb_brand.id,
            snapshot_date=date.today(),
            sales=Decimal("100000.00"),
            collection=Decimal("20000.00"),
            market_outstanding=Decimal("80000.00"),
            bucket_gt_90=Decimal("10000.00"),
        )
        session.add(snap)
        await session.commit()

        # 1. Filter by canonical 'Zebronics'
        res_canon = await report_service.get_outstanding_ageing_report(
            session=session,
            brand="Zebronics",
            query=dms_code,
        )
        assert len(res_canon) >= 1
        assert any(r.customer_id == cust.id for r in res_canon)

        # 2. Filter by alias 'ZBR'
        res_alias = await report_service.get_outstanding_ageing_report(
            session=session,
            brand="ZBR",
            query=dms_code,
        )
        assert len(res_alias) >= 1
        assert any(r.customer_id == cust.id for r in res_alias)

        # 3. Filter by lowercase 'zbr'
        res_lower = await report_service.get_outstanding_ageing_report(
            session=session,
            brand="zbr",
            query=dms_code,
        )
        assert len(res_lower) >= 1
        assert any(r.customer_id == cust.id for r in res_lower)


@pytest.mark.asyncio
async def test_account_reconciliation_single_bucket_no_split():
    """
    Test:
    Snapshot baseline = ZBR (normalized to Zebronics) ₹100,000
    Payment allocation = Zebronics ₹20,000
    -> Outstanding = ₹80,000
    -> Exactly 1 brand bucket for Zebronics (no separate ZBR and Zebronics buckets).
    """
    async with AsyncSessionLocal() as session:
        admin_user = User(
            email=f"admin_{uuid.uuid4().hex[:6]}@fieldtrack.internal",
            password_hash="hash",
            role=Role.ADMIN,
        )
        session.add(admin_user)
        await session.flush()

        cust = Customer(
            name=f"Reconcile Outlet {uuid.uuid4().hex[:6]}",
            outlet_code=f"DMS_REC_{uuid.uuid4().hex[:6]}",
            location_status="VERIFIED",
            created_by=admin_user.id,
        )
        session.add(cust)
        await session.flush()

        emp = Employee(
            user_id=admin_user.id,
            employee_code=f"EMP_{uuid.uuid4().hex[:6]}",
            full_name="Collector Rep",
            working_profile="FOS",
        )
        session.add(emp)
        await session.flush()

        zeb_brand = await brand_service.get_brand_by_name(session, "Zebronics")
        assert zeb_brand is not None

        # Baseline snapshot
        snap = OutletFinancialSnapshot(
            customer_id=cust.id,
            brand="Zebronics",
            brand_id=zeb_brand.id,
            snapshot_date=date.today(),
            sales=Decimal("100000.00"),
            collection=Decimal("0.00"),
            market_outstanding=Decimal("100000.00"),
            bucket_gt_90=Decimal("0.00"),
        )
        session.add(snap)

        # Verified Payment with allocation to Zebronics
        pay = Payment(
            customer_id=cust.id,
            employee_id=emp.id,
            amount=Decimal("20000.00"),
            payment_method=PaymentMethod.CASH,
            payment_date=date.today(),
            status=PaymentStatus.VERIFIED,
            created_by=admin_user.id,
        )
        alloc = PaymentBrandAllocation(
            brand="Zebronics",
            brand_id=zeb_brand.id,
            allocated_amount=Decimal("20000.00"),
        )
        pay.allocations.append(alloc)
        session.add(pay)
        await session.commit()

        # Verified but the receipt is not in Tally yet: outstanding must NOT drop.
        pre = await account_service.get_account_summary(
            customer_id=cust.id, current_user=admin_user, session=session,
        )
        assert pre.total_outstanding == Decimal("100000.00")  # baseline-only headline
        pre_zeb = {b.brand: b for b in pre.brand_summary}["Zebronics"]
        assert pre_zeb.total_outstanding == Decimal("100000.00")
        assert pre_zeb.total_paid == Decimal("0.00")
        assert pre_zeb.verified_awaiting_tally_amount == Decimal("20000.00")

        # The sync agent posts the receipt to Tally and ACKs the write-back job.
        from tests.tally_helpers import ack_payment_in_tally
        await ack_payment_in_tally(pay.id)

        # Fetch account summary
        summary = await account_service.get_account_summary(
            customer_id=cust.id,
            current_user=admin_user,
            session=session,
        )

        # Validate single unified bucket
        brand_map = {b.brand: b for b in summary.brand_summary}
        assert "ZBR" not in brand_map
        assert "zbr" not in brand_map
        assert "Zebronics" in brand_map

        zeb_summary = brand_map["Zebronics"]
        assert zeb_summary.total_invoiced == Decimal("100000.00")
        assert zeb_summary.total_paid == Decimal("20000.00")
        assert zeb_summary.total_outstanding == Decimal("80000.00")

        # Overall totals
        assert summary.total_invoiced == Decimal("100000.00")
        assert summary.total_paid == Decimal("20000.00")
        # Tally is the final truth: the headline INCLUDES the snapshot baseline and
        # always equals the sum of the brand buckets (100,000 - 20,000 posted).
        assert sum((b.total_outstanding for b in summary.brand_summary), Decimal("0")) == Decimal("80000.00")
        assert summary.total_outstanding == Decimal("80000.00")
        assert summary.total_outstanding == sum((b.total_outstanding for b in summary.brand_summary), Decimal("0"))
        assert summary.overdue_amount == sum((b.overdue_amount for b in summary.brand_summary), Decimal("0"))
        assert summary.verified_awaiting_tally_amount == Decimal("0.00")


@pytest.mark.asyncio
async def test_headline_outstanding_equals_sum_of_brands_with_baseline_and_invoice():
    """Snapshot baseline (USHA 50,000) + invoice (VU 7,000): headline == 57,000 == sum of brands."""
    async with AsyncSessionLocal() as session:
        admin_user = User(
            email=f"admin_{uuid.uuid4().hex[:6]}@fieldtrack.internal", password_hash="hash", role=Role.ADMIN
        )
        session.add(admin_user)
        await session.flush()
        cust = Customer(
            name=f"Headline Outlet {uuid.uuid4().hex[:6]}",
            outlet_code=f"DMS_HL_{uuid.uuid4().hex[:6]}",
            location_status="VERIFIED",
            created_by=admin_user.id,
        )
        session.add(cust)
        await session.flush()
        session.add(
            OutletFinancialSnapshot(
                customer_id=cust.id, brand="USHA", snapshot_date=date.today(),
                sales=Decimal("50000.00"), collection=Decimal("0.00"),
                market_outstanding=Decimal("50000.00"), bucket_gt_90=Decimal("10000.00"),
            )
        )
        session.add(
            Invoice(
                customer_id=cust.id, invoice_number=f"INV-HL-{uuid.uuid4().hex[:6]}",
                invoice_date=date.today(), amount=Decimal("7000.00"), brand="VU", created_by=admin_user.id,
            )
        )
        await session.commit()

        summary = await account_service.get_account_summary(
            customer_id=cust.id, current_user=admin_user, session=session
        )
        brands = {b.brand: b for b in summary.brand_summary}
        assert brands["USHA"].total_outstanding == Decimal("50000.00")
        assert brands["VU"].total_outstanding == Decimal("7000.00")
        assert summary.total_outstanding == Decimal("57000.00")
        assert summary.total_outstanding == sum((b.total_outstanding for b in summary.brand_summary), Decimal("0"))
        assert summary.overdue_amount == Decimal("10000.00")


@pytest.mark.asyncio
async def test_collections_overview_outstanding_matches_account_headline():
    """Collections overview row total_outstanding uses the same rule (baseline + invoices) as the account headline."""
    from app.services import collections_service

    async with AsyncSessionLocal() as session:
        admin_user = User(
            email=f"admin_{uuid.uuid4().hex[:6]}@fieldtrack.internal", password_hash="hash", role=Role.ADMIN
        )
        session.add(admin_user)
        await session.flush()
        code = f"DMS_CO_{uuid.uuid4().hex[:6]}"
        cust = Customer(name=f"Coll Outlet {code}", outlet_code=code, location_status="VERIFIED", created_by=admin_user.id)
        session.add(cust)
        await session.flush()
        session.add(
            OutletFinancialSnapshot(
                customer_id=cust.id, brand="USHA", snapshot_date=date.today(),
                sales=Decimal("30000.00"), collection=Decimal("0.00"),
                market_outstanding=Decimal("30000.00"), bucket_gt_90=Decimal("0.00"),
            )
        )
        session.add(
            Invoice(
                customer_id=cust.id, invoice_number=f"INV-CO-{uuid.uuid4().hex[:6]}",
                invoice_date=date.today(), amount=Decimal("4000.00"), brand="Zebronics", created_by=admin_user.id,
            )
        )
        await session.commit()

        acct = await account_service.get_account_summary(customer_id=cust.id, current_user=admin_user, session=session)
        overview = await collections_service.get_collections_overview(session, search=code)
        assert overview.total_count == 1
        row = overview.outlets[0]
        assert acct.total_outstanding == Decimal("34000.00")
        assert row.total_outstanding == acct.total_outstanding
        assert overview.totals.total_outstanding == acct.total_outstanding
