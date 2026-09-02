import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
import pytest
import pytest_asyncio
from httpx import AsyncClient
from app.core.security import create_access_token, hash_password
from app.database import AsyncSessionLocal
from app.models.customer import Customer
from app.models.customer_brand import CustomerBrand
from app.models.employee import Employee
from app.models.invoice import Invoice, InvoiceSource
from app.models.payment import PaymentMethod, PaymentStatus
from app.models.user import Role, User
from app.models.visit import Visit, VisitStatus
from tests.conftest import requires_db


@pytest_asyncio.fixture
async def brand_summary_fixture():
    async with AsyncSessionLocal() as session:
        admin_user = User(
            email=f"admin_bs_{uuid.uuid4().hex[:6]}@fieldtrack.test",
            password_hash=hash_password("AdminPass123!"),
            role=Role.ADMIN,
            is_active=True,
        )
        emp_user = User(
            email=f"emp_bs_{uuid.uuid4().hex[:6]}@fieldtrack.test",
            password_hash=hash_password("EmpPass123!"),
            role=Role.EMPLOYEE,
            is_active=True,
        )
        session.add_all([admin_user, emp_user])
        await session.flush()

        employee = Employee(
            user_id=emp_user.id,
            full_name="Account Summary Rep",
            employee_code=f"EMP-{uuid.uuid4().hex[:6].upper()}",
        )
        session.add(employee)
        await session.flush()

        # 1. Customer with customer_brands (USHA, Zebronics, Finolex) but ZERO invoices
        cust_assigned_no_inv = Customer(
            name="Alpha Multi-Brand Store",
            outlet_code=f"OUT-ALPHA-{uuid.uuid4().hex[:4].upper()}",
            address="Commercial Road",
            created_by=admin_user.id,
        )
        session.add(cust_assigned_no_inv)
        await session.flush()

        session.add_all([
            CustomerBrand(customer_id=cust_assigned_no_inv.id, brand="USHA", is_active=True),
            CustomerBrand(customer_id=cust_assigned_no_inv.id, brand="Zebronics", is_active=True),
            CustomerBrand(customer_id=cust_assigned_no_inv.id, brand="Finolex", is_active=True),
        ])

        # 2. Customer with brand only in invoices (Havells)
        cust_inv_only = Customer(
            name="Beta Electricals",
            outlet_code=f"OUT-BETA-{uuid.uuid4().hex[:4].upper()}",
            address="Industrial Area",
            created_by=admin_user.id,
        )
        session.add(cust_inv_only)
        await session.flush()

        session.add(
            Invoice(
                customer_id=cust_inv_only.id,
                invoice_number=f"INV-HAV-{uuid.uuid4().hex[:4]}",
                invoice_date=date.today(),
                amount=Decimal("45000.00"),
                brand="Havells",
                source=InvoiceSource.MANUAL,
                created_by=admin_user.id,
            )
        )

        # 3. Customer with duplicate brand in both customer_brands and invoices (case variation: "usha" vs "USHA")
        cust_overlap = Customer(
            name="Gamma Appliances",
            outlet_code=f"OUT-GAMMA-{uuid.uuid4().hex[:4].upper()}",
            address="Main Bazaar",
            created_by=admin_user.id,
        )
        session.add(cust_overlap)
        await session.flush()

        session.add(CustomerBrand(customer_id=cust_overlap.id, brand="USHA", is_active=True))
        session.add(
            Invoice(
                customer_id=cust_overlap.id,
                invoice_number=f"INV-USH-{uuid.uuid4().hex[:4]}",
                invoice_date=date.today(),
                amount=Decimal("25000.00"),
                brand="usha",
                source=InvoiceSource.MANUAL,
                created_by=admin_user.id,
            )
        )

        # 4. Customer with ZERO brands anywhere
        cust_no_brands = Customer(
            name="Delta General Store",
            outlet_code=f"OUT-DELTA-{uuid.uuid4().hex[:4].upper()}",
            address="Village Junction",
            created_by=admin_user.id,
        )
        session.add(cust_no_brands)
        await session.flush()

        from datetime import timedelta
        now = datetime.now(timezone.utc)
        visit_alpha = Visit(
            customer_id=cust_assigned_no_inv.id,
            employee_id=employee.id,
            scheduled_at=now,
            status=VisitStatus.IN_PROGRESS,
            created_by=admin_user.id,
        )
        visit_delta = Visit(
            customer_id=cust_no_brands.id,
            employee_id=employee.id,
            scheduled_at=now + timedelta(hours=2),
            status=VisitStatus.IN_PROGRESS,
            created_by=admin_user.id,
        )
        session.add_all([visit_alpha, visit_delta])
        await session.commit()

        admin_token = create_access_token(str(admin_user.id), Role.ADMIN.value)
        emp_token = create_access_token(str(emp_user.id), Role.EMPLOYEE.value)

        return {
            "admin_token": admin_token,
            "emp_token": emp_token,
            "cust_alpha_id": cust_assigned_no_inv.id,
            "cust_beta_id": cust_inv_only.id,
            "cust_gamma_id": cust_overlap.id,
            "cust_delta_id": cust_no_brands.id,
            "visit_alpha_id": visit_alpha.id,
            "visit_delta_id": visit_delta.id,
        }


@requires_db
@pytest.mark.asyncio
async def test_customer_with_brands_and_zero_invoices_returns_all_brands(client: AsyncClient, brand_summary_fixture):
    data = brand_summary_fixture
    resp = await client.get(
        f"/api/v1/customers/{data['cust_alpha_id']}/account",
        headers={"Authorization": f"Bearer {data['admin_token']}"},
    )
    assert resp.status_code == 200
    account = resp.json()
    assert Decimal(str(account["total_invoiced"])) == Decimal("0")
    assert Decimal(str(account["total_outstanding"])) == Decimal("0")
    
    brand_names = [b["brand"] for b in account["brand_summary"]]
    assert len(brand_names) == 3
    assert set(brand_names) == {"USHA", "Zebronics", "Finolex"}
    for b in account["brand_summary"]:
        assert Decimal(str(b["total_outstanding"])) == Decimal("0")
        assert Decimal(str(b["total_invoiced"])) == Decimal("0")


@requires_db
@pytest.mark.asyncio
async def test_customer_with_brand_in_invoice_only_returns_brand(client: AsyncClient, brand_summary_fixture):
    data = brand_summary_fixture
    resp = await client.get(
        f"/api/v1/customers/{data['cust_beta_id']}/account",
        headers={"Authorization": f"Bearer {data['admin_token']}"},
    )
    assert resp.status_code == 200
    account = resp.json()
    assert Decimal(str(account["total_invoiced"])) == Decimal("45000.00")
    assert Decimal(str(account["total_outstanding"])) == Decimal("45000.00")
    
    brand_names = [b["brand"] for b in account["brand_summary"]]
    assert brand_names == ["Havells"]
    assert Decimal(str(account["brand_summary"][0]["total_outstanding"])) == Decimal("45000.00")


@requires_db
@pytest.mark.asyncio
async def test_duplicate_brand_from_association_and_invoice_appears_once(client: AsyncClient, brand_summary_fixture):
    data = brand_summary_fixture
    resp = await client.get(
        f"/api/v1/customers/{data['cust_gamma_id']}/account",
        headers={"Authorization": f"Bearer {data['admin_token']}"},
    )
    assert resp.status_code == 200
    account = resp.json()
    brand_names = [b["brand"] for b in account["brand_summary"]]
    assert len(brand_names) == 1
    assert brand_names[0].upper() == "USHA"
    assert Decimal(str(account["brand_summary"][0]["total_invoiced"])) == Decimal("25000.00")
    assert Decimal(str(account["brand_summary"][0]["total_outstanding"])) == Decimal("25000.00")


@requires_db
@pytest.mark.asyncio
async def test_payment_for_zero_invoice_customer_with_brands_submits_allocations(client: AsyncClient, brand_summary_fixture):
    data = brand_summary_fixture
    payload = {
        "visit_id": str(data["visit_alpha_id"]),
        "amount": 75000.0,
        "payment_method": "ONLINE",
        "payment_date": str(date.today()),
        "utr_reference": "UTR_ZERO_INV_123",
        "allocations": [
            {"brand": "USHA", "amount": 50000.0},
            {"brand": "Zebronics", "amount": 25000.0},
        ],
    }

    resp = await client.post(
        "/api/v1/payments",
        json=payload,
        headers={"Authorization": f"Bearer {data['emp_token']}"},
    )
    assert resp.status_code == 201
    payment = resp.json()
    assert Decimal(str(payment["amount"])) == Decimal("75000.00")
    assert len(payment["allocations"]) == 2
    allocated_brands = {a["brand"]: Decimal(str(a["allocated_amount"])) for a in payment["allocations"]}
    assert allocated_brands["USHA"] == Decimal("50000.00")
    assert allocated_brands["Zebronics"] == Decimal("25000.00")


@requires_db
@pytest.mark.asyncio
async def test_customer_with_no_brands_anywhere_returns_empty_brand_summary(client: AsyncClient, brand_summary_fixture):
    data = brand_summary_fixture
    resp = await client.get(
        f"/api/v1/customers/{data['cust_delta_id']}/account",
        headers={"Authorization": f"Bearer {data['admin_token']}"},
    )
    assert resp.status_code == 200
    account = resp.json()
    assert account["brand_summary"] == []
    assert Decimal(str(account["total_outstanding"])) == Decimal("0")

    # Payment without allocations for brandless customer succeeds
    payload = {
        "visit_id": str(data["visit_delta_id"]),
        "amount": 10000.0,
        "payment_method": "CASH",
        "payment_date": str(date.today()),
        "allocations": None,
    }
    pay_resp = await client.post(
        "/api/v1/payments",
        json=payload,
        headers={"Authorization": f"Bearer {data['emp_token']}"},
    )
    assert pay_resp.status_code == 201
    assert pay_resp.json()["allocations"] == []
