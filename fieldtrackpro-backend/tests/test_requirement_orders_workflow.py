import uuid
from decimal import Decimal
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.core.security import create_access_token, hash_password
from app.database import AsyncSessionLocal
from app.models.user import Role, User
from app.models.customer import Customer
from app.models.customer_requirement import CustomerRequirement
from app.models.requirement_item import RequirementItem
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.tally_writeback import TallyWritebackQueue
from sqlalchemy import select


@pytest_asyncio.fixture
async def setup_test_data():
    async with AsyncSessionLocal() as session:
        tag = uuid.uuid4().hex[:6]

        # 1. Admin user
        admin = User(
            email=f"admin_order_{tag}@fieldtrack.test",
            password_hash=hash_password("Admin123!"),
            role=Role.ADMIN,
            is_active=True,
        )
        session.add(admin)

        # 2. Sales Rep employee user
        rep = User(
            email=f"rep_order_{tag}@fieldtrack.test",
            password_hash=hash_password("Rep123!"),
            role=Role.EMPLOYEE,
            is_active=True,
        )
        session.add(rep)
        await session.flush()

        # 3. Customer
        customer = Customer(
            name=f"Test Retailer {tag}",
            outlet_code=f"TR-{tag.upper()}",
            address="123 Civil Lines, Kanpur",
            contact_number="9876543210",
            created_by=admin.id,
        )
        session.add(customer)
        await session.commit()
        await session.refresh(customer)
        await session.refresh(admin)
        await session.refresh(rep)

        admin_token = create_access_token(str(admin.id), Role.ADMIN.value)
        rep_token = create_access_token(str(rep.id), Role.EMPLOYEE.value)

        yield {
            "admin": admin,
            "rep": rep,
            "customer": customer,
            "admin_token": admin_token,
            "rep_token": rep_token,
        }

        # Cleanup
        async with AsyncSessionLocal() as clean_session:
            await clean_session.execute(
                select(TallyWritebackQueue).where(TallyWritebackQueue.entity_type == "SALES_ORDER")
            )
            # cascade will clean up items


@pytest.mark.asyncio
async def test_multi_item_requirement_and_order_flow(setup_test_data):
    data = setup_test_data
    admin_token = data["admin_token"]
    rep_token = data["rep_token"]
    customer = data["customer"]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Sales rep creates multi-item requirement
        create_payload = {
            "customer_id": str(customer.id),
            "requirement_type": "Weekly Booking",
            "items": [
                {
                    "brand_name": "Samsung",
                    "product_model": "S25",
                    "requested_quantity": 3,
                    "expected_rate": 30000.0,
                    "notes": "Urgent customer requirement",
                },
                {
                    "brand_name": "Samsung",
                    "product_model": "A16",
                    "requested_quantity": 5,
                    "expected_rate": 12000.0,
                    "notes": "Display stock",
                },
            ],
            "notes": "Customer agreed to 14 days credit terms.",
        }

        res = await client.post(
            "/api/v1/requirements",
            json=create_payload,
            headers={"Authorization": f"Bearer {rep_token}"},
        )
        assert res.status_code == 201, res.text
        req_data = res.json()
        assert req_data["total_requested_value"] == 150000.0  # (3*30000) + (5*12000)
        assert len(req_data["items"]) == 2
        assert req_data["status"] == "NEW"
        req_id = req_data["id"]

        # 2. Admin reviews requirement line-by-line (partial approval)
        # S25: 3 requested -> 2 approved
        # A16: 5 requested -> 4 approved
        s25_item_id = req_data["items"][0]["id"]
        a16_item_id = req_data["items"][1]["id"]

        decision_payload = {
            "action": "PARTIALLY_APPROVE",
            "admin_notes": "Stock allocated from Kanpur Warehouse",
            "items": [
                {
                    "id": s25_item_id,
                    "approved_quantity": 2,
                    "approved_rate": 30000.0,
                    "tally_stock_item_name": "Samsung S25 5G (8GB/256GB)",
                },
                {
                    "id": a16_item_id,
                    "approved_quantity": 4,
                    "approved_rate": 12000.0,
                    "tally_stock_item_name": "Samsung Galaxy A16",
                },
            ],
        }

        res = await client.post(
            f"/api/v1/requirements/{req_id}/decision",
            json=decision_payload,
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert res.status_code == 200, res.text
        dec_data = res.json()
        assert dec_data["status"] == "PARTIALLY_APPROVED"
        assert dec_data["total_approved_value"] == 108000.0  # (2*30000) + (4*12000)

        # 3. Admin clicks "Confirm & Send to Tally"
        res = await client.post(
            f"/api/v1/requirements/{req_id}/confirm-order",
            json={"admin_notes": "Confirmed for dispatch tomorrow"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert res.status_code == 201, res.text
        order_data = res.json()
        assert order_data["total_amount"] == 108000.0
        assert order_data["status"] == "PENDING_TALLY"
        assert len(order_data["items"]) == 2
        order_id = order_data["id"]

        # 4. Verify requirement status is now CONVERTED_TO_ORDER
        res = await client.get(
            f"/api/v1/requirements/{req_id}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert res.status_code == 200
        assert res.json()["status"] == "CONVERTED_TO_ORDER"

        # 5. Verify Tally writeback queue has CREATE_SALES_ORDER job
        async with AsyncSessionLocal() as session:
            wb_res = await session.execute(
                select(TallyWritebackQueue).where(
                    TallyWritebackQueue.entity_id == uuid.UUID(order_id)
                )
            )
            wb_job = wb_res.scalar_one_or_none()
            assert wb_job is not None
            assert wb_job.entity_type == "SALES_ORDER"
            assert wb_job.operation == "CREATE"
            assert str(wb_job.status) == "PENDING"
            assert wb_job.payload["order_number"] == order_data["order_number"]
            assert len(wb_job.payload["items"]) == 2

        # 6. Verify list orders API
        res = await client.get(
            "/api/v1/orders",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert res.status_code == 200
        orders_list = res.json()
        assert any(o["id"] == order_id for o in orders_list)
