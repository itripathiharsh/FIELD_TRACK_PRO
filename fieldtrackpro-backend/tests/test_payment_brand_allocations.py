import uuid
from datetime import date
from decimal import Decimal
import pytest
import pytest_asyncio
from httpx import AsyncClient

from app.core.security import create_access_token, hash_password
from app.database import AsyncSessionLocal
from app.models.customer import Customer
from app.models.employee import Employee
from app.models.invoice import Invoice, InvoiceSource
from app.models.payment import PaymentMethod, PaymentStatus
from app.models.user import Role, User
from app.models.visit import Visit, VisitStatus
from tests.conftest import requires_db


@pytest_asyncio.fixture
async def brand_payment_setup():
    async with AsyncSessionLocal() as session:
        # Create Admin
        admin_user = User(
            email=f"admin_brand_{uuid.uuid4().hex[:6]}@fieldtrack.test",
            password_hash=hash_password("AdminPass123!"),
            role=Role.ADMIN,
            is_active=True,
        )
        # Create Employee User & Employee
        emp_user = User(
            email=f"emp_brand_{uuid.uuid4().hex[:6]}@fieldtrack.test",
            password_hash=hash_password("EmpPass123!"),
            role=Role.EMPLOYEE,
            is_active=True,
        )
        session.add_all([admin_user, emp_user])
        await session.flush()

        employee = Employee(
            user_id=emp_user.id,
            full_name="Brand Collector Rep",
            employee_code=f"EMP-{uuid.uuid4().hex[:6].upper()}",
        )
        session.add(employee)
        await session.flush()

        # Create Customer
        customer = Customer(
            name="ABC Electronics",
            outlet_code=f"OUT-{uuid.uuid4().hex[:6].upper()}",
            address="123 Market Road, City",
            created_by=admin_user.id,
        )
        session.add(customer)
        await session.flush()

        # Create Invoices for 3 brands: USHA, Zebronics, Havells
        usha_inv = Invoice(
            customer_id=customer.id,
            invoice_number=f"INV-USHA-{uuid.uuid4().hex[:4]}",
            invoice_date=date.today(),
            amount=Decimal("80000.00"),
            brand="USHA",
            source=InvoiceSource.MANUAL,
            created_by=admin_user.id,
        )
        zeb_inv = Invoice(
            customer_id=customer.id,
            invoice_number=f"INV-ZEB-{uuid.uuid4().hex[:4]}",
            invoice_date=date.today(),
            amount=Decimal("60000.00"),
            brand="Zebronics",
            source=InvoiceSource.MANUAL,
            created_by=admin_user.id,
        )
        hav_inv = Invoice(
            customer_id=customer.id,
            invoice_number=f"INV-HAV-{uuid.uuid4().hex[:4]}",
            invoice_date=date.today(),
            amount=Decimal("40000.00"),
            brand="Havells",
            source=InvoiceSource.MANUAL,
            created_by=admin_user.id,
        )
        session.add_all([usha_inv, zeb_inv, hav_inv])

        # Create Visit assigned to employee
        from datetime import datetime, timezone
        visit = Visit(
            customer_id=customer.id,
            employee_id=employee.id,
            scheduled_at=datetime.now(timezone.utc),
            status=VisitStatus.IN_PROGRESS,
            created_by=admin_user.id,
        )
        session.add(visit)
        await session.commit()

        admin_token = create_access_token(str(admin_user.id), Role.ADMIN.value)
        emp_token = create_access_token(str(emp_user.id), Role.EMPLOYEE.value)

        return {
            "admin_token": admin_token,
            "emp_token": emp_token,
            "admin_user_id": admin_user.id,
            "emp_user_id": emp_user.id,
            "customer_id": customer.id,
            "employee_id": employee.id,
            "visit_id": visit.id,
        }


@requires_db
@pytest.mark.asyncio
async def test_create_multi_brand_payment(client: AsyncClient, brand_payment_setup):
    data = brand_payment_setup
    payload = {
        "visit_id": str(data["visit_id"]),
        "amount": 80000.0,
        "payment_method": "ONLINE",
        "payment_date": str(date.today()),
        "utr_reference": "UTR12345678",
        "notes": "Collected for USHA & Zebronics",
        "allocations": [
            {"brand": "USHA", "amount": 50000.0},
            {"brand": "Zebronics", "amount": 30000.0},
        ],
    }

    resp = await client.post(
        "/api/v1/payments",
        json=payload,
        headers={"Authorization": f"Bearer {data['emp_token']}"},
    )
    assert resp.status_code == 201
    payment = resp.json()
    assert payment["amount"] == "80000.00"
    assert payment["status"] == "PENDING_VERIFICATION"
    assert len(payment["allocations"]) == 2

    alloc_map = {a["brand"]: Decimal(str(a["allocated_amount"])) for a in payment["allocations"]}
    assert alloc_map["USHA"] == Decimal("50000.00")
    assert alloc_map["Zebronics"] == Decimal("30000.00")


@requires_db
@pytest.mark.asyncio
async def test_reject_allocation_sum_mismatch(client: AsyncClient, brand_payment_setup):
    data = brand_payment_setup
    payload = {
        "visit_id": str(data["visit_id"]),
        "amount": 80000.0,
        "payment_method": "CASH",
        "payment_date": str(date.today()),
        "allocations": [
            {"brand": "USHA", "amount": 50000.0},
            {"brand": "Zebronics", "amount": 20000.0},  # Sum = 70K, Expected = 80K
        ],
    }

    resp = await client.post(
        "/api/v1/payments",
        json=payload,
        headers={"Authorization": f"Bearer {data['emp_token']}"},
    )
    assert resp.status_code == 422
    assert "must equal payment total" in resp.text


@requires_db
@pytest.mark.asyncio
async def test_reject_duplicate_brands_in_allocation(client: AsyncClient, brand_payment_setup):
    data = brand_payment_setup
    payload = {
        "visit_id": str(data["visit_id"]),
        "amount": 80000.0,
        "payment_method": "CASH",
        "payment_date": str(date.today()),
        "allocations": [
            {"brand": "USHA", "amount": 50000.0},
            {"brand": "usha", "amount": 30000.0},  # Duplicate case-insensitive brand
        ],
    }

    resp = await client.post(
        "/api/v1/payments",
        json=payload,
        headers={"Authorization": f"Bearer {data['emp_token']}"},
    )
    assert resp.status_code == 422
    assert "Duplicate brand allocation" in resp.text


@requires_db
@pytest.mark.asyncio
async def test_admin_can_update_allocations_when_pending(client: AsyncClient, brand_payment_setup):
    data = brand_payment_setup
    # 1. Create payment with USHA 50K, Zebronics 30K
    payload = {
        "visit_id": str(data["visit_id"]),
        "amount": 80000.0,
        "payment_method": "ONLINE",
        "payment_date": str(date.today()),
        "utr_reference": "UTR99999",
        "allocations": [
            {"brand": "USHA", "amount": 50000.0},
            {"brand": "Zebronics", "amount": 30000.0},
        ],
    }
    create_resp = await client.post(
        "/api/v1/payments",
        json=payload,
        headers={"Authorization": f"Bearer {data['emp_token']}"},
    )
    assert create_resp.status_code == 201
    payment_id = create_resp.json()["id"]

    # 2. Admin corrects allocation to USHA 40K, Zebronics 40K
    patch_resp = await client.patch(
        f"/api/v1/payments/{payment_id}/allocations",
        json={
            "allocations": [
                {"brand": "USHA", "amount": 40000.0},
                {"brand": "Zebronics", "amount": 40000.0},
            ]
        },
        headers={"Authorization": f"Bearer {data['admin_token']}"},
    )
    assert patch_resp.status_code == 200
    updated = patch_resp.json()
    alloc_map = {a["brand"]: Decimal(str(a["allocated_amount"])) for a in updated["allocations"]}
    assert alloc_map["USHA"] == Decimal("40000.00")
    assert alloc_map["Zebronics"] == Decimal("40000.00")
    assert "[Allocation adjusted by Admin" in updated["notes"]


@requires_db
@pytest.mark.asyncio
async def test_cannot_update_allocations_after_verification(client: AsyncClient, brand_payment_setup):
    data = brand_payment_setup
    create_resp = await client.post(
        "/api/v1/payments",
        json={
            "visit_id": str(data["visit_id"]),
            "amount": 50000.0,
            "payment_method": "CASH",
            "payment_date": str(date.today()),
            "allocations": [{"brand": "USHA", "amount": 50000.0}],
        },
        headers={"Authorization": f"Bearer {data['emp_token']}"},
    )
    payment_id = create_resp.json()["id"]

    # Admin verifies payment
    verify_resp = await client.post(
        f"/api/v1/payments/{payment_id}/verify",
        headers={"Authorization": f"Bearer {data['admin_token']}"},
    )
    assert verify_resp.status_code == 200

    # Try to modify allocations after verification
    patch_resp = await client.patch(
        f"/api/v1/payments/{payment_id}/allocations",
        json={"allocations": [{"brand": "USHA", "amount": 50000.0}]},
        headers={"Authorization": f"Bearer {data['admin_token']}"},
    )
    assert patch_resp.status_code == 409
    assert "Cannot adjust allocations" in patch_resp.text


@requires_db
@pytest.mark.asyncio
async def test_verified_payment_updates_only_allocated_brand_outstanding(client: AsyncClient, brand_payment_setup):
    data = brand_payment_setup
    customer_id = data["customer_id"]

    # Check Initial Account Summary
    init_summary_resp = await client.get(
        f"/api/v1/customers/{customer_id}/account",
        headers={"Authorization": f"Bearer {data['admin_token']}"},
    )
    assert init_summary_resp.status_code == 200
    init_summary = init_summary_resp.json()
    brand_map = {b["brand"]: b for b in init_summary["brand_summary"]}
    assert Decimal(brand_map["USHA"]["total_outstanding"]) == Decimal("80000.00")
    assert Decimal(brand_map["Zebronics"]["total_outstanding"]) == Decimal("60000.00")
    assert Decimal(brand_map["Havells"]["total_outstanding"]) == Decimal("40000.00")

    # Employee records payment: USHA 50K, Zebronics 30K (Total 80K)
    create_resp = await client.post(
        "/api/v1/payments",
        json={
            "visit_id": str(data["visit_id"]),
            "amount": 80000.0,
            "payment_method": "ONLINE",
            "payment_date": str(date.today()),
            "utr_reference": "UTR-BRAND-TEST",
            "allocations": [
                {"brand": "USHA", "amount": 50000.0},
                {"brand": "Zebronics", "amount": 30000.0},
            ],
        },
        headers={"Authorization": f"Bearer {data['emp_token']}"},
    )
    assert create_resp.status_code == 201
    payment_id = create_resp.json()["id"]

    # Before verification: balances must NOT change
    mid_summary_resp = await client.get(
        f"/api/v1/customers/{customer_id}/account",
        headers={"Authorization": f"Bearer {data['admin_token']}"},
    )
    mid_brand_map = {b["brand"]: b for b in mid_summary_resp.json()["brand_summary"]}
    assert Decimal(mid_brand_map["USHA"]["total_outstanding"]) == Decimal("80000.00")

    # Admin verifies payment
    verify_resp = await client.post(
        f"/api/v1/payments/{payment_id}/verify",
        headers={"Authorization": f"Bearer {data['admin_token']}"},
    )
    assert verify_resp.status_code == 200

    # After verification:
    # USHA: 80K invoiced - 50K paid = 30K outstanding
    # Zebronics: 60K invoiced - 30K paid = 30K outstanding
    # Havells: 40K invoiced - 0 paid = 40K outstanding (UNCHANGED!)
    final_summary_resp = await client.get(
        f"/api/v1/customers/{customer_id}/account",
        headers={"Authorization": f"Bearer {data['admin_token']}"},
    )
    assert final_summary_resp.status_code == 200
    final_brand_map = {b["brand"]: b for b in final_summary_resp.json()["brand_summary"]}

    assert Decimal(final_brand_map["USHA"]["total_paid"]) == Decimal("50000.00")
    assert Decimal(final_brand_map["USHA"]["total_outstanding"]) == Decimal("30000.00")

    assert Decimal(final_brand_map["Zebronics"]["total_paid"]) == Decimal("30000.00")
    assert Decimal(final_brand_map["Zebronics"]["total_outstanding"]) == Decimal("30000.00")

    assert Decimal(final_brand_map["Havells"]["total_paid"]) == Decimal("0.00")
    assert Decimal(final_brand_map["Havells"]["total_outstanding"]) == Decimal("40000.00")


@requires_db
@pytest.mark.asyncio
async def test_employee_cannot_update_allocations(client: AsyncClient, brand_payment_setup):
    data = brand_payment_setup
    create_resp = await client.post(
        "/api/v1/payments",
        json={
            "visit_id": str(data["visit_id"]),
            "amount": 50000.0,
            "payment_method": "CASH",
            "payment_date": str(date.today()),
            "allocations": [{"brand": "USHA", "amount": 50000.0}],
        },
        headers={"Authorization": f"Bearer {data['emp_token']}"},
    )
    payment_id = create_resp.json()["id"]

    patch_resp = await client.patch(
        f"/api/v1/payments/{payment_id}/allocations",
        json={"allocations": [{"brand": "USHA", "amount": 50000.0}]},
        headers={"Authorization": f"Bearer {data['emp_token']}"},
    )
    assert patch_resp.status_code == 403


@requires_db
@pytest.mark.asyncio
async def test_strict_brand_isolation_no_cross_brand_spillover(client: AsyncClient, brand_payment_setup):
    data = brand_payment_setup
    customer_id = data["customer_id"]

    # Overpay USHA by 90K (invoice is only 80K)
    create_resp = await client.post(
        "/api/v1/payments",
        json={
            "visit_id": str(data["visit_id"]),
            "amount": 90000.0,
            "payment_method": "CASH",
            "payment_date": str(date.today()),
            "allocations": [{"brand": "USHA", "amount": 90000.0}],
        },
        headers={"Authorization": f"Bearer {data['emp_token']}"},
    )
    assert create_resp.status_code == 201
    payment_id = create_resp.json()["id"]

    # Admin verifies payment
    await client.post(
        f"/api/v1/payments/{payment_id}/verify",
        headers={"Authorization": f"Bearer {data['admin_token']}"},
    )

    # Check account: Zebronics (60K) and Havells (40K) must remain 100% UNTOUCHED
    summary_resp = await client.get(
        f"/api/v1/customers/{customer_id}/account",
        headers={"Authorization": f"Bearer {data['admin_token']}"},
    )
    brand_map = {b["brand"]: b for b in summary_resp.json()["brand_summary"]}

    assert Decimal(brand_map["USHA"]["total_paid"]) == Decimal("90000.00")
    assert Decimal(brand_map["USHA"]["total_outstanding"]) == Decimal("0.00")

    assert Decimal(brand_map["Zebronics"]["total_paid"]) == Decimal("0.00")
    assert Decimal(brand_map["Zebronics"]["total_outstanding"]) == Decimal("60000.00")

    assert Decimal(brand_map["Havells"]["total_paid"]) == Decimal("0.00")
    assert Decimal(brand_map["Havells"]["total_outstanding"]) == Decimal("40000.00")
