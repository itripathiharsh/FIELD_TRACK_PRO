"""
Customer prospect approval workflow: an EMPLOYEE-submitted new outlet is held
(PENDING) instead of becoming a live Customer immediately; an ADMIN reviews
(and can edit) it, then approves (creates the real Customer, brands,
assignment, requirement, and flags needs_tally_entry=True since there is no
Tally writeback for customers) or rejects it (nothing created).
"""
import uuid

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select

from app.core.security import create_access_token, hash_password
from app.database import AsyncSessionLocal
from app.main import app
from app.models.customer import Customer
from app.models.customer_prospect import CustomerProspect, ProspectStatus
from app.models.employee import Employee
from app.models.notification import Notification
from app.models.user import Role, User
from tests.conftest import requires_db

pytestmark = [requires_db, pytest.mark.asyncio]


async def _purge_prospect_test_rows(tag: str) -> None:
    """Best-effort teardown so repeat runs never collide on the tag-derived name/phone."""
    async with AsyncSessionLocal() as session:
        from sqlalchemy import delete as sa_delete

        from app.models.customer_brand import CustomerBrand
        from app.models.customer_requirement import CustomerRequirement
        from app.models.employee_customer_assignment import EmployeeCustomerAssignment

        cust_ids = (
            await session.execute(select(Customer.id).where(Customer.name.like(f"%{tag}%")))
        ).scalars().all()
        if cust_ids:
            await session.execute(sa_delete(EmployeeCustomerAssignment).where(EmployeeCustomerAssignment.customer_id.in_(cust_ids)))
            await session.execute(sa_delete(CustomerBrand).where(CustomerBrand.customer_id.in_(cust_ids)))
            await session.execute(sa_delete(CustomerRequirement).where(CustomerRequirement.customer_id.in_(cust_ids)))
        await session.execute(sa_delete(Notification).where(Notification.title.in_(["Outlet approved", "Outlet submission rejected"])))
        await session.execute(sa_delete(Customer).where(Customer.name.like(f"%{tag}%")))
        await session.execute(sa_delete(CustomerProspect).where(CustomerProspect.name.like(f"%{tag}%")))
        await session.execute(sa_delete(Employee).where(Employee.employee_code.like(f"%{tag.upper()}%")))
        await session.execute(sa_delete(User).where(User.email.like(f"%{tag}%@fieldtrack.test")))
        await session.commit()


@pytest_asyncio.fixture
async def prospect_env():
    # Numeric tag: also used in contact_number (digits-only per PHONE_PATTERN), so every
    # test run's phone numbers are unique and can never collide with a leftover row from a
    # previous (e.g. interrupted) run - that was a real source of flakiness here.
    tag = str(uuid.uuid4().int % 10**6).zfill(6)
    async with AsyncSessionLocal() as session:
        admin = User(
            email=f"admin_prospect_{tag}@fieldtrack.test",
            password_hash=hash_password("Admin123!"),
            role=Role.ADMIN,
            is_active=True,
        )
        session.add(admin)

        emp_user = User(
            email=f"emp_prospect_{tag}@fieldtrack.test",
            password_hash=hash_password("Emp123!"),
            role=Role.EMPLOYEE,
            is_active=True,
        )
        session.add(emp_user)
        await session.flush()

        employee = Employee(
            user_id=emp_user.id,
            full_name=f"Prospect Rep {tag}",
            employee_code=f"PROS-{tag}",
        )
        session.add(employee)
        await session.flush()
        await session.commit()

        yield {"admin": admin, "employee_user": emp_user, "employee": employee, "tag": tag}

    await _purge_prospect_test_rows(tag)


def _emp_headers(user_id):
    return {"Authorization": f"Bearer {create_access_token(str(user_id), Role.EMPLOYEE.value)}"}


def _admin_headers(user_id):
    return {"Authorization": f"Bearer {create_access_token(str(user_id), Role.ADMIN.value)}"}


async def test_employee_submission_creates_no_live_customer(prospect_env):
    """The outlet must NOT exist (directory, assignment, visits) until approved."""
    env = prospect_env
    emp_headers = _emp_headers(env["employee_user"].id)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        name = f"__itest__ProspectOutlet_{env['tag']}"
        resp = await client.post(
            "/api/v1/customers/prospect",
            json={
                "name": name,
                "contact_number": f"+9198123{env['tag']}",
                "address": "123 Test Lane",
                "brands": ["Havells", "Finolex"],
                "location": {"latitude": 12.97, "longitude": 77.59},
                "gps_accuracy_meters": 8.0,
                "requirement": {"product_details": "25 ceiling fans", "quantity": 25, "expected_value": 50000.0},
            },
            headers=emp_headers,
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["status"] == "PENDING_APPROVAL"
        assert body["customer"] is None
        prospect_id = body["prospect_id"]
        assert prospect_id

        # Not visible anywhere as a customer.
        directory = await client.get(f"/api/v1/customers?search={name}", headers=emp_headers)
        assert directory.status_code == 200
        assert all(c["name"] != name for c in directory.json())

    async with AsyncSessionLocal() as session:
        prospect = (
            await session.execute(select(CustomerProspect).where(CustomerProspect.id == uuid.UUID(prospect_id)))
        ).scalar_one()
        assert prospect.status == ProspectStatus.PENDING
        assert prospect.name == name
        assert prospect.brand_names == ["Havells", "Finolex"]
        assert prospect.requirement_payload["quantity"] == 25
        assert prospect.submitted_by == env["employee_user"].id
        assert prospect.submitted_by_employee_id == env["employee"].id

        no_customer = (
            await session.execute(select(Customer).where(Customer.name == name))
        ).scalar_one_or_none()
        assert no_customer is None


async def test_admin_can_edit_then_approve_creates_customer_with_tally_flag(prospect_env):
    env = prospect_env
    emp_headers = _emp_headers(env["employee_user"].id)
    adm_headers = _admin_headers(env["admin"].id)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        name = f"__itest__ProspectEdit_{env['tag']}"
        submit = await client.post(
            "/api/v1/customers/prospect",
            json={
                "name": name,
                "contact_number": f"+9198124{env['tag']}",
                "address": "456 Test Lane",
                "brands": ["Zebronics"],
                "outlet_code": "typo-code",
            },
            headers=emp_headers,
        )
        assert submit.status_code == 201, submit.text
        prospect_id = submit.json()["prospect_id"]

        # Admin review queue shows it.
        queue = await client.get("/api/v1/customers/prospects?status=PENDING", headers=adm_headers)
        assert queue.status_code == 200
        assert prospect_id in {p["id"] for p in queue.json()}

        # Admin fixes the outlet code before approving.
        edited = await client.patch(
            f"/api/v1/customers/prospects/{prospect_id}",
            json={"outlet_code": "UPDD-FIXED-01"},
            headers=adm_headers,
        )
        assert edited.status_code == 200, edited.text
        assert edited.json()["outlet_code"] == "UPDD-FIXED-01"

        approved = await client.post(f"/api/v1/customers/prospects/{prospect_id}/approve", headers=adm_headers)
        assert approved.status_code == 200, approved.text
        customer_body = approved.json()
        assert customer_body["outlet_code"] == "UPDD-FIXED-01"
        assert customer_body["brands"] == ["Zebronics"]
        assert customer_body["needs_tally_entry"] is True
        customer_id = customer_body["id"]

        # Now visible live.
        fetched = await client.get(f"/api/v1/customers/{customer_id}", headers=adm_headers)
        assert fetched.status_code == 200
        assert fetched.json()["name"] == name

        # The employee can see their assignment / the prospect's resolved status.
        mine = await client.get("/api/v1/customers/prospects", headers=emp_headers)
        mine_row = next(p for p in mine.json() if p["id"] == prospect_id)
        assert mine_row["status"] == "APPROVED"
        assert mine_row["resulting_customer_id"] == customer_id

        # Mark as added to Tally - flag clears.
        marked = await client.post(f"/api/v1/customers/{customer_id}/mark-tally-entry-done", headers=adm_headers)
        assert marked.status_code == 200
        assert marked.json()["needs_tally_entry"] is False

    async with AsyncSessionLocal() as session:
        assignment_check = (
            await session.execute(
                select(Customer).where(Customer.id == uuid.UUID(customer_id))
            )
        ).scalar_one()
        assert assignment_check.created_by == env["employee_user"].id

        notif = (
            await session.execute(
                select(Notification).where(
                    Notification.user_id == env["employee_user"].id,
                    Notification.title == "Outlet approved",
                )
            )
        ).scalar_one_or_none()
        assert notif is not None


async def test_duplicate_submission_blocked_while_first_is_still_pending(prospect_env):
    """
    Two submissions for the same outlet (same phone) must be caught even though NEITHER
    is a live Customer yet - a Customer-only duplicate check would miss this entirely,
    since at submission time no Customer row exists for either one.
    """
    env = prospect_env
    emp_headers = _emp_headers(env["employee_user"].id)
    phone = f"+9198127{env['tag']}"

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        first = await client.post(
            "/api/v1/customers/prospect",
            json={"name": f"__itest__ProspectDup_{env['tag']}", "contact_number": phone, "address": "A"},
            headers=emp_headers,
        )
        assert first.status_code == 201, first.text

        second = await client.post(
            "/api/v1/customers/prospect",
            json={"name": f"__itest__ProspectDup2_{env['tag']}", "contact_number": phone, "address": "B"},
            headers=emp_headers,
        )
        assert second.status_code == 409, second.text
        assert second.json()["error"]["code"] == "DUPLICATE_CUSTOMER"


async def test_reject_requires_reason_and_creates_no_customer(prospect_env):
    env = prospect_env
    emp_headers = _emp_headers(env["employee_user"].id)
    adm_headers = _admin_headers(env["admin"].id)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        name = f"__itest__ProspectReject_{env['tag']}"
        submit = await client.post(
            "/api/v1/customers/prospect",
            json={"name": name, "contact_number": f"+9198125{env['tag']}", "address": "789 Test Lane"},
            headers=emp_headers,
        )
        prospect_id = submit.json()["prospect_id"]

        too_short = await client.post(
            f"/api/v1/customers/prospects/{prospect_id}/reject", json={"reason": "no"}, headers=adm_headers
        )
        assert too_short.status_code == 422

        rejected = await client.post(
            f"/api/v1/customers/prospects/{prospect_id}/reject",
            json={"reason": "Duplicate of an existing outlet nearby."},
            headers=adm_headers,
        )
        assert rejected.status_code == 200, rejected.text
        assert rejected.json()["status"] == "REJECTED"
        assert rejected.json()["rejection_reason"] == "Duplicate of an existing outlet nearby."

        # Can't approve/reject again.
        again = await client.post(f"/api/v1/customers/prospects/{prospect_id}/approve", headers=adm_headers)
        assert again.status_code == 409

    async with AsyncSessionLocal() as session:
        no_customer = (
            await session.execute(select(Customer).where(Customer.name == name))
        ).scalar_one_or_none()
        assert no_customer is None


async def test_employee_cannot_see_or_act_on_another_employees_prospect(prospect_env):
    env = prospect_env
    emp_headers = _emp_headers(env["employee_user"].id)
    tag2 = env["tag"] + "9"  # distinct from env['tag'] but still purged by the same teardown (substring match)

    async with AsyncSessionLocal() as session:
        other_user = User(
            email=f"other_prospect_{tag2}@fieldtrack.test",
            password_hash=hash_password("Other123!"),
            role=Role.EMPLOYEE,
            is_active=True,
        )
        session.add(other_user)
        await session.flush()
        other_employee = Employee(user_id=other_user.id, full_name=f"Other Rep {tag2}", employee_code=f"OTH-{tag2}")
        session.add(other_employee)
        await session.commit()
        other_user_id = other_user.id

    other_headers = _emp_headers(other_user_id)

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            submit = await client.post(
                "/api/v1/customers/prospect",
                json={"name": f"__itest__ScopedProspect_{env['tag']}", "contact_number": f"+9198126{env['tag']}", "address": "1 Lane"},
                headers=emp_headers,
            )
            prospect_id = submit.json()["prospect_id"]

            other_get = await client.get(f"/api/v1/customers/prospects/{prospect_id}", headers=other_headers)
            assert other_get.status_code == 403

            other_list = await client.get("/api/v1/customers/prospects", headers=other_headers)
            assert prospect_id not in {p["id"] for p in other_list.json()}

            other_approve = await client.post(f"/api/v1/customers/prospects/{prospect_id}/approve", headers=other_headers)
            assert other_approve.status_code == 403
    finally:
        await _purge_prospect_test_rows(tag2)


@pytest.fixture(autouse=True)
def _outlet_proof_not_required(monkeypatch):
    """These tests predate live outlet proof: submit prospects without a proof (flag off)."""
    from app.config import settings

    monkeypatch.setattr(settings, "outlet_proof_required_for_new_outlet", False)
