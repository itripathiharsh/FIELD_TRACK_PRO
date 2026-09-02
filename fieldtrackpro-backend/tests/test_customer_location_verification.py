import uuid
from datetime import datetime, timezone
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select

from app.core.security import create_access_token, hash_password
from app.database import AsyncSessionLocal
from app.main import app
from app.models.customer import Customer
from app.models.customer_brand import CustomerBrand
from app.models.customer_location_proposal import CustomerLocationProposal, LocationProposalStatus
from app.models.customer_requirement import CustomerRequirement
from app.models.employee import Employee
from app.models.user import Role, User


@pytest_asyncio.fixture
async def loc_setup():
    async with AsyncSessionLocal() as session:
        # Admin
        admin_user = User(
            email=f"admin_loc_{uuid.uuid4().hex[:6]}@fieldtrack.test",
            password_hash=hash_password("AdminPass123!"),
            role=Role.ADMIN,
            is_active=True,
        )
        # Employee
        emp_user = User(
            email=f"emp_loc_{uuid.uuid4().hex[:6]}@fieldtrack.test",
            password_hash=hash_password("EmpPass123!"),
            role=Role.EMPLOYEE,
            is_active=True,
        )
        session.add_all([admin_user, emp_user])
        await session.flush()

        employee = Employee(
            user_id=emp_user.id,
            employee_code=f"EMP-{uuid.uuid4().hex[:4].upper()}",
            full_name="Rahul Verma",
        )
        # Customer in Delhi
        customer = Customer(
            name="ABC Electronics",
            contact_number="+919876543210",
            contact_person="Alok Kumar",
            address="Chandni Chowk, Delhi",
            location="SRID=4326;POINT(77.2090 28.6139)",
            geofence_radius_m=75,
            location_status="VERIFIED",
            outlet_code=f"OUT-{uuid.uuid4().hex[:4].upper()}",
            created_by=admin_user.id,
        )
        session.add_all([employee, customer])
        await session.commit()
        await session.refresh(admin_user)
        await session.refresh(emp_user)
        await session.refresh(employee)
        await session.refresh(customer)

        admin_token = create_access_token(str(admin_user.id), Role.ADMIN.value)
        emp_token = create_access_token(str(emp_user.id), Role.EMPLOYEE.value)

        return {
            "admin_user": admin_user,
            "emp_user": emp_user,
            "employee": employee,
            "customer": customer,
            "admin_token": admin_token,
            "emp_token": emp_token,
        }


@pytest.mark.asyncio
async def test_suggest_location_creates_pending_proposal_without_modifying_official_coords(loc_setup):
    customer = loc_setup["customer"]
    emp_token = loc_setup["emp_token"]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Propose new location
        proposed_lat = 28.6200
        proposed_lng = 77.2150
        resp = await client.post(
            f"/api/v1/customers/{customer.id}/location-proposals",
            headers={"Authorization": f"Bearer {emp_token}"},
            json={
                "proposed_latitude": proposed_lat,
                "proposed_longitude": proposed_lng,
                "gps_accuracy_meters": 8.5,
                "notes": "Store shifted 200m north down the street.",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["status"] == "PENDING"
        assert data["proposed_latitude"] == proposed_lat
        assert data["proposed_longitude"] == proposed_lng
        assert data["gps_accuracy_meters"] == 8.5
        assert data["submitter_name"] == "Rahul Verma"

    # Check official customer coordinates remain UNCHANGED in DB
    async with AsyncSessionLocal() as session:
        cust_res = await session.execute(select(Customer).where(Customer.id == customer.id))
        reloaded_cust = cust_res.scalar_one()
        from app.services.customer_service import extract_coords
        official_lat, official_lng = extract_coords(reloaded_cust.location)
        assert round(official_lat, 4) == round(28.6139, 4)
        assert round(official_lng, 4) == round(77.2090, 4)
        assert reloaded_cust.location_status == "PENDING_APPROVAL"


@pytest.mark.asyncio
async def test_admin_approves_location_proposal_updates_official_coords(loc_setup):
    customer = loc_setup["customer"]
    emp_token = loc_setup["emp_token"]
    admin_token = loc_setup["admin_token"]
    admin_user = loc_setup["admin_user"]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Submit proposal
        prop_resp = await client.post(
            f"/api/v1/customers/{customer.id}/location-proposals",
            headers={"Authorization": f"Bearer {emp_token}"},
            json={
                "proposed_latitude": 28.7000,
                "proposed_longitude": 77.3000,
                "gps_accuracy_meters": 5.0,
                "notes": "Accurate GPS fix at front gate.",
            },
        )
        assert prop_resp.status_code == 201
        prop_id = prop_resp.json()["id"]

        # 2. Admin approves proposal
        appr_resp = await client.post(
            f"/api/v1/location-proposals/{prop_id}/approve",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert appr_resp.status_code == 200
        appr_data = appr_resp.json()
        assert appr_data["status"] == "APPROVED"
        assert appr_data["reviewed_by"] == str(admin_user.id)
        assert appr_data["reviewed_at"] is not None

    # 3. Verify official coordinates ARE now updated
    async with AsyncSessionLocal() as session:
        cust_res = await session.execute(select(Customer).where(Customer.id == customer.id))
        reloaded_cust = cust_res.scalar_one()
        from app.services.customer_service import extract_coords
        official_lat, official_lng = extract_coords(reloaded_cust.location)
        assert round(official_lat, 4) == round(28.7000, 4)
        assert round(official_lng, 4) == round(77.3000, 4)
        assert reloaded_cust.location_status == "VERIFIED"


@pytest.mark.asyncio
async def test_admin_rejects_location_proposal_with_reason_leaves_coords_untouched(loc_setup):
    customer = loc_setup["customer"]
    emp_token = loc_setup["emp_token"]
    admin_token = loc_setup["admin_token"]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Submit proposal
        prop_resp = await client.post(
            f"/api/v1/customers/{customer.id}/location-proposals",
            headers={"Authorization": f"Bearer {emp_token}"},
            json={
                "proposed_latitude": 12.9716,
                "proposed_longitude": 77.5946,
                "gps_accuracy_meters": 12.0,
            },
        )
        assert prop_resp.status_code == 201
        prop_id = prop_resp.json()["id"]

        # 2. Reject without reason -> validation failure (422)
        bad_rej = await client.post(
            f"/api/v1/location-proposals/{prop_id}/reject",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"rejection_reason": ""},
        )
        assert bad_rej.status_code == 422

        # 3. Reject with valid reason
        rej_resp = await client.post(
            f"/api/v1/location-proposals/{prop_id}/reject",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"rejection_reason": "Proposed location is in Bengaluru, but outlet is in Delhi."},
        )
        assert rej_resp.status_code == 200
        rej_data = rej_resp.json()
        assert rej_data["status"] == "REJECTED"
        assert rej_data["rejection_reason"] == "Proposed location is in Bengaluru, but outlet is in Delhi."

    # 4. Verify official coordinates remained unchanged
    async with AsyncSessionLocal() as session:
        cust_res = await session.execute(select(Customer).where(Customer.id == customer.id))
        reloaded_cust = cust_res.scalar_one()
        from app.services.customer_service import extract_coords
        official_lat, official_lng = extract_coords(reloaded_cust.location)
        assert round(official_lat, 4) == round(28.6139, 4)
        assert round(official_lng, 4) == round(77.2090, 4)
        assert reloaded_cust.location_status == "VERIFIED"


@pytest.mark.asyncio
async def test_employee_cannot_approve_location_proposal(loc_setup):
    customer = loc_setup["customer"]
    emp_token = loc_setup["emp_token"]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        prop_resp = await client.post(
            f"/api/v1/customers/{customer.id}/location-proposals",
            headers={"Authorization": f"Bearer {emp_token}"},
            json={"proposed_latitude": 28.6200, "proposed_longitude": 77.2150},
        )
        prop_id = prop_resp.json()["id"]

        # Employee tries to self-approve
        forbidden_resp = await client.post(
            f"/api/v1/location-proposals/{prop_id}/approve",
            headers={"Authorization": f"Bearer {emp_token}"},
        )
        assert forbidden_resp.status_code == 403


@pytest.mark.asyncio
async def test_single_pending_proposal_per_customer_guard(loc_setup):
    customer = loc_setup["customer"]
    emp_token = loc_setup["emp_token"]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. First proposal
        p1 = await client.post(
            f"/api/v1/customers/{customer.id}/location-proposals",
            headers={"Authorization": f"Bearer {emp_token}"},
            json={"proposed_latitude": 28.6200, "proposed_longitude": 77.2150},
        )
        assert p1.status_code == 201

        # 2. Second proposal while first is still pending -> 409 Conflict
        p2 = await client.post(
            f"/api/v1/customers/{customer.id}/location-proposals",
            headers={"Authorization": f"Bearer {emp_token}"},
            json={"proposed_latitude": 28.6250, "proposed_longitude": 77.2200},
        )
        assert p2.status_code == 409
        err_msg = p2.json().get("error", {}).get("message", "") or p2.json().get("detail", "")
        assert "pending location proposal already exists" in err_msg.lower()


@pytest.mark.asyncio
async def test_create_customer_prospect_with_brands_and_requirement(loc_setup):
    import random
    import string
    emp_token = loc_setup["emp_token"]
    unique_phone = f"+9198{random.randint(10000000, 99999999)}"
    unique_gst = f"07{''.join(random.choices(string.ascii_uppercase, k=5))}{random.randint(1000, 9999)}A1Z{random.randint(1, 9)}"

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/customers/prospect",
            headers={"Authorization": f"Bearer {emp_token}"},
            json={
                "name": "New Alpha Traders",
                "contact_person": "Vikram Singh",
                "contact_number": unique_phone,
                "gst_number": unique_gst,
                "address": "Shop 4, Chandni Chowk, Delhi",
                "brands": ["USHA", "Zebronics"],
                "location": {"latitude": 28.6505, "longitude": 77.2303},
                "gps_accuracy_meters": 6.0,
                "requirement": {
                    "brand": "USHA",
                    "requirement_type": "Dealership & Initial Stock",
                    "product_details": "50 Ceiling Fans, 20 Water Heaters",
                    "quantity": 70,
                    "expected_value": 150000.0,
                    "follow_up_date": "2026-09-05",
                    "notes": "Owner interested in festive bulk discount.",
                },
            },
        )
        assert resp.status_code == 201
        cust_data = resp.json()
        cust_id = uuid.UUID(cust_data["id"])
        assert cust_data["name"] == "New Alpha Traders"
        assert cust_data["gst_number"] == unique_gst
        assert "USHA" in cust_data["brands"]
        assert "Zebronics" in cust_data["brands"]
        assert cust_data["location_status"] == "PENDING_APPROVAL"

    async with AsyncSessionLocal() as session:
        # Verify brands in database
        b_res = await session.execute(select(CustomerBrand).where(CustomerBrand.customer_id == cust_id))
        brands = b_res.scalars().all()
        assert len(brands) == 2
        assert {b.brand for b in brands} == {"USHA", "Zebronics"}

        # Verify requirement in database
        r_res = await session.execute(select(CustomerRequirement).where(CustomerRequirement.customer_id == cust_id))
        reqs = r_res.scalars().all()
        assert len(reqs) == 1
        req = reqs[0]
        assert req.brand == "USHA"
        assert req.quantity == 70
        assert float(req.expected_value) == 150000.0
        assert str(req.follow_up_date) == "2026-09-05"

        # Verify pending location proposal created
        p_res = await session.execute(select(CustomerLocationProposal).where(CustomerLocationProposal.customer_id == cust_id))
        proposals = p_res.scalars().all()
        assert len(proposals) == 1
        prop = proposals[0]
        assert prop.status == LocationProposalStatus.PENDING
        assert prop.proposed_latitude == 28.6505
        assert prop.proposed_longitude == 77.2303


@pytest.mark.asyncio
async def test_duplicate_customer_detection(loc_setup):
    import random
    import string
    emp_token = loc_setup["emp_token"]
    unique_phone = f"+9199{random.randint(10000000, 99999999)}"
    unique_gst = f"07{''.join(random.choices(string.ascii_uppercase, k=5))}{random.randint(1000, 9999)}B2Z{random.randint(1, 9)}"

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Create initial customer
        init_resp = await client.post(
            "/api/v1/customers/prospect",
            headers={"Authorization": f"Bearer {emp_token}"},
            json={
                "name": "Original Store",
                "contact_person": "Ramesh",
                "contact_number": unique_phone,
                "gst_number": unique_gst,
                "address": "Delhi",
            },
        )
        assert init_resp.status_code == 201

        # Attempt to create duplicate with same mobile number
        dup_resp = await client.post(
            "/api/v1/customers/prospect",
            headers={"Authorization": f"Bearer {emp_token}"},
            json={
                "name": "Duplicate Store Attempt",
                "contact_number": unique_phone,
                "address": "Delhi",
            },
        )
        assert dup_resp.status_code == 409
        dup_json = dup_resp.json()
        err_code = dup_json.get("error", {}).get("code", "") or dup_json.get("error_code", "")
        err_msg = dup_json.get("error", {}).get("message", "") or dup_json.get("detail", "")
        assert err_code == "DUPLICATE_CUSTOMER"
        assert "Original Store" in err_msg


@pytest.mark.asyncio
async def test_global_requirements_and_brands_api(loc_setup):
    emp_token = loc_setup["emp_token"]
    customer = loc_setup["customer"]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Master brands API
        brands_resp = await client.get(
            "/api/v1/brands",
            headers={"Authorization": f"Bearer {emp_token}"},
        )
        brand_list = brands_resp.json()
        brand_names = [b["name"] for b in brand_list] if (brand_list and isinstance(brand_list[0], dict)) else brand_list
        assert "USHA" in brand_names
        assert "Zebronics" in brand_names

        # 2. Requirements API
        create_req = await client.post(
            f"/api/v1/customers/{customer.id}/requirements",
            headers={"Authorization": f"Bearer {emp_token}"},
            json={
                "brand": "Zebronics",
                "requirement_type": "Display / Branding",
                "product_details": "Storefront glow sign board",
                "expected_value": 25000.0,
                "follow_up_date": "2026-09-10",
            },
        )
        assert create_req.status_code == 201
        req_id = create_req.json()["id"]

        # 3. Global requirements list
        list_req = await client.get(
            "/api/v1/requirements?brand=Zebronics",
            headers={"Authorization": f"Bearer {emp_token}"},
        )
        assert list_req.status_code == 200
        req_items = list_req.json()
        assert any(r["id"] == req_id for r in req_items)
