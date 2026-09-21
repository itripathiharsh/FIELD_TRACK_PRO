import uuid
from datetime import datetime, timezone
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
from app.models.customer import Customer
from app.models.payment import Payment, PaymentMethod, PaymentSource, PaymentStatus
from app.models.tally_writeback import TallyWritebackQueue, WritebackStatus
from app.services.tally_writeback_service import enqueue_payment_writeback
from tests.conftest import requires_db


@pytest_asyncio.fixture
async def audit_test_setup():
    async with AsyncSessionLocal() as session:
        tag = uuid.uuid4().hex[:6]

        # 1. Admin user
        admin_user = User(
            email=f"admin_audit_{tag}@fieldtrack.test",
            password_hash=hash_password("Admin123!"),
            role=Role.ADMIN,
            is_active=True,
        )
        session.add(admin_user)
        await session.flush()

        # 2. Accountant employee user
        acct_user = User(
            email=f"acct_audit_{tag}@fieldtrack.test",
            password_hash=hash_password("Acct123!"),
            role=Role.EMPLOYEE,
            is_active=True,
        )
        session.add(acct_user)
        await session.flush()

        acct_emp = Employee(
            user_id=acct_user.id,
            full_name="Chief Accountant",
            employee_code=f"ACCT-{tag.upper()}",
            working_profile="Head Accountant & Billing In-Charge",
        )
        session.add(acct_emp)
        await session.flush()

        # 3. Standard Field Rep user (Non-accountant employee)
        rep_user = User(
            email=f"rep_audit_{tag}@fieldtrack.test",
            password_hash=hash_password("Rep123!"),
            role=Role.EMPLOYEE,
            is_active=True,
        )
        session.add(rep_user)
        await session.flush()

        rep_emp = Employee(
            user_id=rep_user.id,
            full_name="Field Rep",
            employee_code=f"REP-{tag.upper()}",
            working_profile="Field Operations Specialist",
        )
        session.add(rep_emp)
        await session.flush()

        # 4. Brand
        b_norm = f"brand_{tag}"
        brand = Brand(name=f"Brand {tag}", normalized_name=b_norm, is_active=True)
        session.add(brand)
        await session.flush()

        # 5. Customer
        customer = Customer(
            name=f"Audit Test Store {tag}",
            outlet_code=f"AUDIT-{tag}",
            location_status="VERIFIED",
            created_by=admin_user.id,
        )
        session.add(customer)
        await session.flush()

        await session.commit()
        return {
            "admin_user": admin_user,
            "acct_user": acct_user,
            "rep_user": rep_user,
            "customer": customer,
            "brand": brand,
            "tag": tag,
        }


@pytest.mark.asyncio
@requires_db
async def test_tally_read_write_audit_logging_and_apis(audit_test_setup):
    admin = audit_test_setup["admin_user"]
    acct = audit_test_setup["acct_user"]
    rep = audit_test_setup["rep_user"]
    cust = audit_test_setup["customer"]
    tag = audit_test_setup["tag"]

    admin_token = create_access_token(subject=str(admin.id), role=Role.ADMIN.value)
    acct_token = create_access_token(subject=str(acct.id), role=Role.EMPLOYEE.value)
    rep_token = create_access_token(subject=str(rep.id), role=Role.EMPLOYEE.value)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Register a Sync Agent
        reg_res = await client.post(
            "/api/v1/integrations/tally/agents",
            json={
                "name": f"Audit Agent {tag}",
                "organization_id": f"org_{tag}",
                "tally_company_guid": f"guid_{tag}",
                "tally_company_name": f"SGRG Audit Co {tag}",
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert reg_res.status_code == 201
        agent_id = reg_res.json()["agent"]["id"]
        api_key = reg_res.json()["api_key"]
        agent_headers = {"X-Agent-Id": agent_id, "X-Agent-Key": api_key}

        # 2. Sync Customers -> Must create persistent READ audit entry
        cust_batch = {
            "batch_id": str(uuid.uuid4()),
            "company_guid": f"guid_{tag}",
            "customers": [
                {
                    "source_reference": f"GUID_CUST_{tag}",
                    "outlet_code": f"CUST-AUDIT-{tag}",
                    "name": f"Audit Customer {tag}",
                    "brand": f"Brand {tag}",
                }
            ],
        }
        res_c = await client.post("/api/v1/integrations/tally/sync/customers", json=cust_batch, headers=agent_headers)
        assert res_c.status_code == 200

        # 3. Sync Invoices -> Must create persistent READ audit entry
        inv_batch = {
            "batch_id": str(uuid.uuid4()),
            "company_guid": f"guid_{tag}",
            "invoices": [
                {
                    "source_reference": f"INV_GUID_{tag}",
                    "invoice_number": f"INV/{tag}",
                    "outlet_code": f"CUST-AUDIT-{tag}",
                    "customer_name": f"Audit Customer {tag}",
                    "invoice_date": "2026-09-20",
                    "amount": 5400.00,
                    "brand": f"Brand {tag}",
                }
            ],
        }
        res_i = await client.post("/api/v1/integrations/tally/sync/invoices", json=inv_batch, headers=agent_headers)
        assert res_i.status_code == 200

        # 4. Enqueue a WRITE operation (payment writeback)
        async with AsyncSessionLocal() as session:
            payment = Payment(
                customer_id=cust.id,
                amount=Decimal("3500.00"),
                payment_method=PaymentMethod.ONLINE,
                payment_date=datetime.now(timezone.utc).date(),
                status=PaymentStatus.VERIFIED,
                source=PaymentSource.MANUAL,
                created_by=admin.id,
            )
            session.add(payment)
            await session.flush()
            await enqueue_payment_writeback(session, payment, customer=cust)
            await session.commit()

        # 5. Access /audit-logs as Admin -> 200 OK with both READ and WRITE entries
        res_logs_admin = await client.get(
            "/api/v1/integrations/tally/audit-logs",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert res_logs_admin.status_code == 200
        logs_data = res_logs_admin.json()
        assert "items" in logs_data
        assert logs_data["total"] >= 3

        # Verify READ entries exist
        read_items = [x for x in logs_data["items"] if x["direction"] == "READ"]
        assert len(read_items) >= 2
        cust_log = next((x for x in read_items if x["entity_type"] == "CUSTOMERS"), None)
        assert cust_log is not None
        assert cust_log["status"] == "SUCCESS"
        assert cust_log["record_count"] == 1
        assert cust_log["duration_ms"] is not None

        # Verify WRITE entries exist (from tally_writeback_queue)
        write_items = [x for x in logs_data["items"] if x["direction"] == "WRITE"]
        assert len(write_items) >= 1
        wb_log = write_items[0]
        assert wb_log["operation"] == "CREATE_RECEIPT"
        assert wb_log["entity_type"] == "PAYMENT"
        assert wb_log["record_count"] == 1

        # 6. Test Role Security:
        # Accountant user -> 200 OK
        res_logs_acct = await client.get(
            "/api/v1/integrations/tally/audit-logs",
            headers={"Authorization": f"Bearer {acct_token}"},
        )
        assert res_logs_acct.status_code == 200

        # Non-accountant Field Rep -> 403 Forbidden
        res_logs_rep = await client.get(
            "/api/v1/integrations/tally/audit-logs",
            headers={"Authorization": f"Bearer {rep_token}"},
        )
        assert res_logs_rep.status_code == 403

        # 7. Test Filters:
        # Filter direction=READ
        res_filter_read = await client.get(
            "/api/v1/integrations/tally/audit-logs?direction=READ",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert res_filter_read.status_code == 200
        assert all(x["direction"] == "READ" for x in res_filter_read.json()["items"])

        # Filter direction=WRITE
        res_filter_write = await client.get(
            "/api/v1/integrations/tally/audit-logs?direction=WRITE",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert res_filter_write.status_code == 200
        assert all(x["direction"] == "WRITE" for x in res_filter_write.json()["items"])

        # Filter status=SUCCESS
        res_filter_succ = await client.get(
            "/api/v1/integrations/tally/audit-logs?status=SUCCESS",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert res_filter_succ.status_code == 200
        assert all(x["status"] in ["SUCCESS", "PARTIAL"] for x in res_filter_succ.json()["items"])

        # Filter entity_type=INVOICES
        res_filter_inv = await client.get(
            "/api/v1/integrations/tally/audit-logs?entity_type=INVOICES",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert res_filter_inv.status_code == 200
        assert all(x["entity_type"] == "INVOICES" for x in res_filter_inv.json()["items"])

        # 8. Test /status enriched fields
        res_status = await client.get(
            "/api/v1/integrations/tally/status",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert res_status.status_code == 200
        st_data = res_status.json()
        assert "today_read_count" in st_data
        assert "today_write_count" in st_data
        assert "failed_operation_count" in st_data
        assert st_data["today_read_count"] >= 2
        assert st_data["today_write_count"] >= 1
