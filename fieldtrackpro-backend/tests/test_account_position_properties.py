"""
Property-style tests for the ONE shared account/collections calculation
(app/services/account_position.py).

  (1) opening + invoiced - paid_in_tally == outstanding   (every outlet & brand)
  (2) sum(brand outstanding) == outlet headline == collections row == totals sum
  (3) ageing buckets sum to outstanding
  (4) awaiting (verified, not in Tally) never changes outstanding
  (5) account summary and collections row agree on every shared quantity
"""
from __future__ import annotations

import random
import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
import pytest_asyncio

from app.database import AsyncSessionLocal
from app.models.customer import Customer
from app.models.employee import Employee
from app.models.invoice import Invoice
from app.models.outlet_financial_snapshot import OutletFinancialSnapshot
from app.models.payment import Payment, PaymentBrandAllocation, PaymentMethod, PaymentSource, PaymentStatus
from app.models.user import Role, User
from app.services import account_service, collections_service
from app.services.account_position import (
    BrandInputs,
    InvoiceLine,
    compute_brand_position,
    sum_positions,
)
from app.services.aging_service import AgingStatus, classify_age_days
from tests.conftest import requires_db
from tests.tally_helpers import ack_payment_in_tally

D = Decimal


# ---------------------------------------------------------------------------
# Pure property tests (no DB)
# ---------------------------------------------------------------------------

def _random_inputs(rng: random.Random) -> BrandInputs:
    lines = []
    for _ in range(rng.randint(0, 4)):
        amount = D(rng.randint(1, 50000))
        remaining = D(rng.randint(0, int(amount)))
        days = rng.randint(0, 120)
        lines.append(InvoiceLine(amount, remaining, days, classify_age_days(days) if remaining > 0 else AgingStatus.PAID))
    snap_os = D(rng.choice([0, 0, rng.randint(0, 90000), -rng.randint(1, 5000)]))
    return BrandInputs(
        snapshot_sales=D(rng.randint(0, 100000)),
        snapshot_collection=D(rng.randint(0, 100000)),
        snapshot_outstanding=snap_os,
        snapshot_aged_30_plus=D(rng.randint(0, 100000)) if rng.random() < 0.5 else D(0),
        invoices=lines,
        posted_payments=D(rng.randint(0, 40000)),
        awaiting=D(rng.randint(0, 40000)),
        on_account_credit=D(rng.choice([0, 0, rng.randint(1, 120000)])),
    )


def test_pure_position_invariants_hold_for_random_inputs():
    rng = random.Random(20261010)
    for _ in range(2000):
        brands = [compute_brand_position(_random_inputs(rng)) for _ in range(rng.randint(1, 4))]
        outlet = sum_positions(brands)
        for p in [*brands, outlet]:
            assert p.opening_balance + p.invoiced - p.paid_in_tally == p.outstanding      # (1)
            assert p.ageing.total == p.outstanding                                        # (3)
            assert p.outstanding >= 0 and 0 <= p.overdue <= p.outstanding
            assert p.reconciles is True
        assert outlet.outstanding == sum((b.outstanding for b in brands), D(0))           # (2)
        assert outlet.ageing.total == outlet.outstanding


def test_pure_awaiting_never_changes_outstanding_or_buckets():
    rng = random.Random(7)
    for _ in range(300):
        base = _random_inputs(rng)
        base.awaiting = D(0)
        a = compute_brand_position(base)
        base.awaiting = D(rng.randint(1, 99999))
        b = compute_brand_position(base)
        assert (a.outstanding, a.ageing, a.paid_in_tally, a.overdue, a.opening_balance) == (
            b.outstanding, b.ageing, b.paid_in_tally, b.overdue, b.opening_balance,
        )
        assert b.verified_awaiting_tally == base.awaiting


def test_pure_age_classification_uses_the_shared_thresholds():
    lines = [
        InvoiceLine(D(100), D(100), 20, classify_age_days(20)),
        InvoiceLine(D(200), D(200), 21, classify_age_days(21)),
        InvoiceLine(D(300), D(300), 25, classify_age_days(25)),
        InvoiceLine(D(400), D(400), 26, classify_age_days(26)),
    ]
    p = compute_brand_position(BrandInputs(invoices=lines))
    assert (p.ageing.normal, p.ageing.warning, p.ageing.overdue) == (D(100), D(500), D(400))
    assert p.overdue == D(400) and p.collection_status == AgingStatus.OVERDUE and p.max_days_outstanding == 26


def test_pure_baseline_buckets_and_credit_netting_oldest_first():
    p = compute_brand_position(BrandInputs(
        snapshot_outstanding=D(1000), snapshot_aged_30_plus=D(400),
        invoices=[InvoiceLine(D(500), D(500), 30, AgingStatus.OVERDUE), InvoiceLine(D(100), D(100), 1, AgingStatus.NORMAL)],
        on_account_credit=D(500),
    ))
    # raw 1600 - 500 credit; credit eats baseline_overdue(400) then invoice overdue(100).
    assert p.outstanding == D(1100)
    assert p.ageing.baseline_overdue == D(0) and p.ageing.overdue == D(400)
    assert p.ageing.baseline_current == D(600) and p.ageing.normal == D(100)
    assert p.overdue == D(400)


def test_pure_overpayment_is_advance_not_negative_outstanding():
    p = compute_brand_position(BrandInputs(
        invoices=[InvoiceLine(D(1000), D(1000), 5, AgingStatus.NORMAL)], posted_payments=D(5000), on_account_credit=D(5000),
    ))
    assert p.outstanding == D(0) and p.advance_credit == D(4000)
    assert p.opening_balance + p.invoiced - p.paid_in_tally == p.outstanding and p.reconciles
    assert p.collection_status == AgingStatus.PAID


# ---------------------------------------------------------------------------
# DB-backed: account summary vs collections overview on a mixed world
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def world():
    tag = uuid.uuid4().hex[:6].upper()
    today = date.today()
    async with AsyncSessionLocal() as s:
        admin = User(email=f"adm_pp_{tag}@fieldtrack.test", password_hash="h", role=Role.ADMIN, is_active=True)
        emp_user = User(email=f"emp_pp_{tag}@fieldtrack.test", password_hash="h", role=Role.EMPLOYEE, is_active=True)
        s.add_all([admin, emp_user])
        await s.flush()
        emp = Employee(user_id=emp_user.id, full_name=f"Prop Rep {tag}", employee_code=f"REP-PP{tag}")
        s.add(emp)
        outlets: dict[str, Customer] = {}
        for key in ("mixed", "baseline", "invoice", "over"):
            c = Customer(name=f"Prop {key} {tag}", outlet_code=f"PP{tag}{key[:3].upper()}", address="x", created_by=admin.id)
            s.add(c)
            outlets[key] = c
        await s.flush()

        def snap(c, brand, sales, coll, os_, gt90=0, b3045=0):
            s.add(OutletFinancialSnapshot(
                customer_id=c.id, brand=brand, snapshot_date=today, sales=D(sales), collection=D(coll),
                market_outstanding=D(os_), bucket_gt_90=D(gt90), bucket_30_45=D(b3045),
            ))

        def inv(c, brand, amount, age_days, no):
            i = Invoice(customer_id=c.id, invoice_number=f"PP-{tag}-{no}", invoice_date=today - timedelta(days=age_days),
                        amount=D(amount), brand=brand, created_by=admin.id)
            s.add(i)
            return i

        def pay(c, amount, status, invoice=None, brand=None):
            p = Payment(customer_id=c.id, employee_id=emp.id, amount=D(amount), payment_method=PaymentMethod.CASH,
                        payment_date=today, status=status, source=PaymentSource.MANUAL, created_by=admin.id,
                        invoice_id=invoice.id if invoice is not None else None)
            if brand:
                p.allocations.append(PaymentBrandAllocation(brand=brand, allocated_amount=D(amount)))
            s.add(p)
            return p

        m = outlets["mixed"]
        snap(m, "USHA", 80000, 30000, 50000, gt90=10000, b3045=5000)
        snap(m, "ZBR", 20000, 0, 20000)            # alias of Zebronics
        i_usha = inv(m, "usha", 10000, 40, "1")    # alias/case of USHA, overdue
        inv(m, "VU", 5000, 10, "2")
        inv(m, "VU", 2500, 22, "3")                 # warning
        await s.flush()
        paid_inv = pay(m, 4000, PaymentStatus.VERIFIED, invoice=i_usha, brand="USHA")
        onacct = pay(m, 6000, PaymentStatus.VERIFIED, brand="Zebronics")      # on-account credit
        pay(m, 3000, PaymentStatus.VERIFIED, brand="USHA")                    # verified, awaiting Tally
        pay(m, 2000, PaymentStatus.PENDING_VERIFICATION, brand="VU")
        pay(m, 1000, PaymentStatus.REJECTED, brand="VU")

        snap(outlets["baseline"], "Havells", 12000, 0, 12000, gt90=12000)       # baseline-only
        inv(outlets["invoice"], "VU", 7000, 30, "4")                            # invoice-only
        inv(outlets["invoice"], "VU", 3000, 3, "5")
        o = outlets["over"]
        inv(o, "USHA", 1000, 5, "6")
        await s.flush()
        over_pay = pay(o, 5000, PaymentStatus.VERIFIED, brand="USHA")            # over-payment / advance
        await s.commit()
        ids = {k: c.id for k, c in outlets.items()}
        pids = [paid_inv.id, onacct.id, over_pay.id]
        admin_id = admin.id
    for pid in pids:
        await ack_payment_in_tally(pid)
    async with AsyncSessionLocal() as s:
        admin_obj = await s.get(User, admin_id)
        s.expunge(admin_obj)
    return {"ids": ids, "tag": tag, "admin": admin_obj}


@requires_db
@pytest.mark.asyncio
async def test_account_summary_and_collections_row_share_one_calculation(world):
    async with AsyncSessionLocal() as s:
        overview = await collections_service.get_collections_overview(s, search=world["tag"], limit=100)
        rows = {r.customer_id: r for r in overview.outlets}
        assert set(rows) == set(world["ids"].values())
        summaries = {
            k: await account_service.get_account_summary(cid, world["admin"], s) for k, cid in world["ids"].items()
        }

    for key, cid in world["ids"].items():
        a, r = summaries[key], rows[cid]
        # (1) every outlet and brand; (3) ageing sums to outstanding
        for p in [a, *a.brand_summary]:
            assert p.opening_balance + p.total_invoiced - p.paid_in_tally == p.total_outstanding, (key, p)
            assert p.reconciles is True
            ag = p.ageing
            assert ag.normal + ag.warning + ag.overdue + ag.baseline_current + ag.baseline_overdue == p.total_outstanding
        # (2) brands == headline == collections row
        assert sum((b.total_outstanding for b in a.brand_summary), D(0)) == a.total_outstanding == r.total_outstanding
        # (5) identical on every shared quantity
        for f in (
            "total_invoiced", "total_paid", "verified_awaiting_tally_amount", "total_outstanding", "overdue_amount",
            "max_days_outstanding", "collection_status", "opening_balance", "baseline_invoiced", "baseline_collected",
            "paid_in_tally", "advance_credit", "ageing", "reconciles",
        ):
            assert getattr(a, f) == getattr(r, f), (key, f)

    # (2) totals row is the exact sum of the rows
    t = overview.totals
    assert t.total_outstanding == sum((r.total_outstanding for r in rows.values()), D(0))
    for f in ("total_invoiced", "verified_awaiting_tally_amount", "opening_balance", "paid_in_tally", "overdue_amount", "advance_credit"):
        assert getattr(t, f) == sum((getattr(r, f) for r in rows.values()), D(0)), f
    assert t.opening_balance + t.total_invoiced - t.paid_in_tally == t.total_outstanding
    assert (t.ageing.normal + t.ageing.warning + t.ageing.overdue + t.ageing.baseline_current + t.ageing.baseline_overdue
            == t.total_outstanding)
    assert t.reconciles is True

    # Hand-checked figures.
    mixed = summaries["mixed"]
    brands = {b.brand: b for b in mixed.brand_summary}
    assert set(brands) == {"USHA", "Zebronics", "VU"}                                    # aliases merged
    # USHA: baseline 50000 + invoice (10000-4000 posted) = 56000; awaiting 3000 NOT netted.
    assert brands["USHA"].total_outstanding == D("56000.00")
    assert brands["USHA"].verified_awaiting_tally_amount == D("3000.00")
    assert brands["USHA"].paid_in_tally == D("34000.00")
    assert brands["Zebronics"].total_outstanding == D("14000.00")                        # 20000 - 6000 on-account credit
    assert brands["VU"].total_outstanding == D("7500.00")                                 # pending/rejected ignored
    assert mixed.total_outstanding == D("77500.00") and mixed.verified_awaiting_tally_amount == D("3000.00")
    assert mixed.total_paid == D("10000.00") and mixed.paid_in_tally == D("40000.00")     # posted only vs +baseline
    # overdue: baseline aged 30+ (USHA 15000) + 40-day invoice remaining 6000
    assert mixed.overdue_amount == D("21000.00")

    assert summaries["baseline"].total_outstanding == D("12000.00")
    assert summaries["baseline"].ageing.baseline_overdue == D("12000.00")
    assert summaries["invoice"].total_outstanding == D("10000.00")
    assert summaries["invoice"].overdue_amount == D("7000.00")
    over = summaries["over"]
    assert over.total_outstanding == D("0.00") and over.advance_credit == D("4000.00") and over.reconciles


@requires_db
@pytest.mark.asyncio
async def test_awaiting_payment_changes_nothing_but_awaiting(world):
    """(4) The verified-awaiting 3000 is not netted into paid or outstanding."""
    async with AsyncSessionLocal() as s:
        a = await account_service.get_account_summary(world["ids"]["mixed"], world["admin"], s)
    assert a.verified_awaiting_tally_amount == D("3000.00")
    assert a.total_outstanding == a.opening_balance + a.total_invoiced - a.paid_in_tally == D("77500.00")
