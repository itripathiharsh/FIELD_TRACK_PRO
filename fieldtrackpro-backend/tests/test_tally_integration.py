import uuid
from decimal import Decimal
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.core.security import create_access_token, hash_password
from app.database import AsyncSessionLocal
from app.models.user import Role, User
from app.models.employee import Employee
from app.models.brand import Brand
from tests.conftest import requires_db


@pytest_asyncio.fixture
async def tally_test_setup():
    async with AsyncSessionLocal() as session:
        # Create Admin user
        admin_user = User(
            email=f"admin_tally_{uuid.uuid4().hex[:6]}@fieldtrack.test",
            password_hash=hash_password("Admin123!"),
            role=Role.ADMIN,
            is_active=True,
        )
        session.add(admin_user)
        await session.flush()

        emp_user = User(
            email=f"emp_tally_{uuid.uuid4().hex[:6]}@fieldtrack.test",
            password_hash=hash_password("Emp123!"),
            role=Role.EMPLOYEE,
            is_active=True,
        )
        session.add(emp_user)
        await session.flush()

        employee = Employee(
            user_id=emp_user.id,
            full_name="Tally Sync Worker",
            employee_code=f"EMP-TALLY-{uuid.uuid4().hex[:4].upper()}",
        )
        session.add(employee)
        await session.flush()

        # Ensure brands
        for b_name in ["Oppo", "Philips", "USHA", "VU"]:
            norm = b_name.lower()
            from sqlalchemy import select
            existing = (await session.execute(select(Brand).where(Brand.normalized_name == norm))).scalar_one_or_none()
            if not existing:
                session.add(Brand(name=b_name, normalized_name=norm, is_active=True))

        await session.commit()
        return {"admin_user": admin_user, "employee": employee}


@pytest.mark.asyncio
@requires_db
async def test_tally_agent_lifecycle_and_sync(tally_test_setup):
    admin = tally_test_setup["admin_user"]
    admin_token = create_access_token(subject=str(admin.id), role=Role.ADMIN.value)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Register Agent (AdminOnly)
        reg_payload = {
            "name": "SGRG Main PC Agent",
            "organization_id": "sgrg_org_01",
            "tally_company_guid": "19a03e17-e1ab-44f2-8e7f-1bff56f20ebe",
            "tally_company_name": "SGRG SERVICES (OPC) PRIVATE LIMITED"
        }
        res_reg = await client.post(
            "/api/v1/integrations/tally/agents",
            json=reg_payload,
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert res_reg.status_code == 201, res_reg.text
        reg_data = res_reg.json()
        agent_id = reg_data["agent"]["id"]
        api_key = reg_data["api_key"]
        assert agent_id is not None
        assert api_key.startswith("ft_agent_")

        # 2. Test Unauthorized access without headers
        res_fail = await client.post("/api/v1/integrations/tally/heartbeat", json={
            "agent_version": "1.0.0",
            "tally_status": "CONNECTED"
        })
        assert res_fail.status_code == 401

        # 3. Test Heartbeat with valid headers
        agent_headers = {
            "X-Agent-Id": agent_id,
            "X-Agent-Key": api_key,
        }
        res_hb = await client.post(
            "/api/v1/integrations/tally/heartbeat",
            json={
                "agent_version": "1.0.0",
                "tally_status": "CONNECTED",
                "company_name": "SGRG SERVICES (OPC) PRIVATE LIMITED",
                "company_guid": "19a03e17-e1ab-44f2-8e7f-1bff56f20ebe",
                "checkpoints": {"customers": "2026-08-18"}
            },
            headers=agent_headers,
        )
        assert res_hb.status_code == 200, res_hb.text
        hb_data = res_hb.json()
        assert hb_data["status"] == "OK"
        assert hb_data["organization_id"] == "sgrg_org_01"

        # 4. Sync Customers Batch
        tag = uuid.uuid4().hex[:6]
        cust_batch = {
            "batch_id": str(uuid.uuid4()),
            "company_guid": "19a03e17-e1ab-44f2-8e7f-1bff56f20ebe",
            "customers": [
                {
                    "source_reference": f"TALLY_GUID_CUST_{tag}",
                    "outlet_code": f"DMS-{tag}",
                    "name": f"Aashi Mobile World {tag}",
                    "parent_group": "Sundry Debtors- PH.",
                    "brand": "Philips",
                    "address": "Station Road, Unnao",
                    "gst_number": "09AABCS1429B1Z",
                    "contact_number": "+919999900001",
                    "contact_person": "Mr. Aashi"
                }
            ]
        }
        res_cust = await client.post(
            "/api/v1/integrations/tally/sync/customers",
            json=cust_batch,
            headers=agent_headers,
        )
        assert res_cust.status_code == 200, res_cust.text
        cust_data = res_cust.json()
        assert cust_data["created_count"] == 1
        assert cust_data["failed_count"] == 0

        # Re-sync same customer (Idempotency test)
        res_cust_retry = await client.post(
            "/api/v1/integrations/tally/sync/customers",
            json=cust_batch,
            headers=agent_headers,
        )
        assert res_cust_retry.status_code == 200
        assert res_cust_retry.json()["updated_count"] == 1

        # 5. Sync Invoices Batch
        inv_batch = {
            "batch_id": str(uuid.uuid4()),
            "company_guid": "19a03e17-e1ab-44f2-8e7f-1bff56f20ebe",
            "invoices": [
                {
                    "source_reference": f"TALLY_VCH_GUID_INV_{tag}",
                    "invoice_number": f"SGRG/26-27/{tag}",
                    "outlet_code": f"DMS-{tag}",
                    "customer_name": f"Aashi Mobile World {tag}",
                    "invoice_date": "2026-08-18",
                    "due_date": "2026-09-07",
                    "amount": 1080.00,
                    "brand": "Philips",
                    "voucher_type": "Sales",
                    "imported_outstanding_amount": 1080.00
                }
            ]
        }
        res_inv = await client.post(
            "/api/v1/integrations/tally/sync/invoices",
            json=inv_batch,
            headers=agent_headers,
        )
        assert res_inv.status_code == 200, res_inv.text
        inv_data = res_inv.json()
        assert inv_data["created_count"] == 1
        assert inv_data["failed_count"] == 0

        # Re-sync same invoice (Idempotency test)
        res_inv_retry = await client.post(
            "/api/v1/integrations/tally/sync/invoices",
            json=inv_batch,
            headers=agent_headers,
        )
        assert res_inv_retry.status_code == 200
        assert res_inv_retry.json()["updated_count"] == 1

        # 6. Sync Payments Batch
        pmt_batch = {
            "batch_id": str(uuid.uuid4()),
            "company_guid": "19a03e17-e1ab-44f2-8e7f-1bff56f20ebe",
            "payments": [
                {
                    "source_reference": f"TALLY_RCPT_GUID_{tag}",
                    "receipt_number": f"RCPT-2026-{tag}",
                    "outlet_code": f"DMS-{tag}",
                    "customer_name": f"Aashi Mobile World {tag}",
                    "payment_date": "2026-08-18",
                    "amount": 1080.00,
                    "payment_method": "ONLINE",
                    "utr_reference": f"UTR{tag}",
                    "notes": f"Payment for SGRG/26-27/{tag}",
                    "brand_allocations": [
                        {"brand": "Philips", "allocated_amount": 1080.00}
                    ]
                }
            ]
        }
        res_pmt = await client.post(
            "/api/v1/integrations/tally/sync/payments",
            json=pmt_batch,
            headers=agent_headers,
        )
        assert res_pmt.status_code == 200, res_pmt.text
        pmt_data = res_pmt.json()
        assert pmt_data["created_count"] == 1
        assert pmt_data["failed_count"] == 0

        # Re-sync same payment (Idempotency test)
        res_pmt_retry = await client.post(
            "/api/v1/integrations/tally/sync/payments",
            json=pmt_batch,
            headers=agent_headers,
        )
        assert res_pmt_retry.status_code == 200
        assert res_pmt_retry.json()["updated_count"] == 1
