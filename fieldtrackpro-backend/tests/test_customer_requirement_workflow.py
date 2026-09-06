import io
import uuid
import pytest
from httpx import AsyncClient
from sqlalchemy import select, delete

from app.models.customer import Customer
from app.models.customer_requirement import CustomerRequirement
from app.models.employee import Employee
from app.models.user import Role, User
from app.models.visit import Visit, VisitStatus
from app.models.visit_media import VisitMedia


from app.database import AsyncSessionLocal
from tests.conftest import requires_db, make_admin_token, make_employee_token


@pytest.mark.asyncio
@requires_db
async def test_customer_requirement_admin_workflow(client: AsyncClient):
    """
    End-to-end verification of Customer Requirement Admin Workflow:
    1. Employee creates requirement with product, quantity, value, visit
    2. Employee attaches requirement photo
    3. Employee cannot decide (403 Forbidden)
    4. Admin can review requirement details with photo URL
    5. Admin can partially approve: original values remain immutable
    6. Admin can reject another requirement
    7. Status filtering works
    8. Clean teardown
    """
    admin_token = make_admin_token()
    employee_token = make_employee_token()

    req_id_1 = None
    req_id_2 = None
    visit_id = None

    async with AsyncSessionLocal() as db_session:
        # 1. Setup real customer and employee
        cust_stmt = select(Customer).limit(1)
        customer = (await db_session.execute(cust_stmt)).scalar_one_or_none()
        assert customer is not None, "A real customer must exist in test database"

        emp_stmt = select(Employee).limit(1)
        employee = (await db_session.execute(emp_stmt)).scalar_one_or_none()
        assert employee is not None, "A real employee must exist in test database"

        from datetime import datetime, timezone
        visit = Visit(
            customer_id=customer.id,
            employee_id=employee.id,
            scheduled_at=datetime.now(timezone.utc),
            status=VisitStatus.COMPLETED,
            created_by=employee.user_id,
        )
        db_session.add(visit)
        await db_session.commit()
        await db_session.refresh(visit)
        visit_id = visit.id

    try:
        # 2. Employee submits Requirement 1 (e.g. 2 x Usha TV @ 1,00,000)
        req_payload = {
            "customer_id": str(customer.id),
            "visit_id": str(visit.id),
            "brand": "Usha",
            "requirement_type": "Bulk Order",
            "product_details": "2 x Usha TV 43-inch Smart",
            "quantity": 2,
            "expected_value": 100000.0,
            "notes": "Retailer requests immediate allocation for festive season",
        }
        res = await client.post(
            f"/api/v1/customers/{customer.id}/requirements",
            json=req_payload,
            headers={"Authorization": f"Bearer {employee_token}"},
        )
        assert res.status_code == 201, f"Create requirement failed: {res.text}"
        data1 = res.json()
        req_id_1 = uuid.UUID(data1["id"])
        assert data1["status"] == "PENDING"
        assert data1["quantity"] == 2
        assert data1["expected_value"] == 100000.0
        assert data1["visit_id"] == str(visit.id)

        # 3. Employee uploads client requirement photo
        fake_img_bytes = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00H\x00H\x00\x00\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t\x08\n\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a\x1f\x1e\x1d\x1a\x1c\x1c $.' \",#\x1c\x1c(7),01444\x1f'9=82<.342\xff\xc0\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00\xff\xc4\x00\x1f\x00\x00\x01\x05\x01\x01\x01\x01\x01\x01\x00\x00\x00\x00\x00\x00\x00\x00\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b\xff\xda\x00\x08\x01\x01\x00\x00?\x00\xbf\x00\xff\xd9"
        files = {"file": ("client_indent.jpg", fake_img_bytes, "image/jpeg")}
        photo_res = await client.post(
            f"/api/v1/requirements/{req_id_1}/photo",
            files=files,
            headers={"Authorization": f"Bearer {employee_token}"},
        )
        assert photo_res.status_code == 200, f"Upload photo failed: {photo_res.text}"
        photo_data = photo_res.json()
        assert photo_data["photo_url"] is not None
        assert "requirements/" in photo_data["photo_storage_key"]

        # 4. Authorization check: Employee CANNOT make an admin decision
        unauth_res = await client.post(
            f"/api/v1/requirements/{req_id_1}/decision",
            json={
                "action": "APPROVE",
                "approved_quantity": 2,
                "approved_value": 100000.0,
            },
            headers={"Authorization": f"Bearer {employee_token}"},
        )
        assert unauth_res.status_code == 403, "Employees must NOT be allowed to approve requirements"

        # 5. Admin retrieves requirement details with photo URL
        admin_get_res = await client.get(
            f"/api/v1/requirements/{req_id_1}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert admin_get_res.status_code == 200
        detail = admin_get_res.json()
        assert detail["customer_name"] == customer.name
        assert detail["photo_url"] is not None

        # 6. Admin PARTIALLY APPROVES requirement (Requested: 2 for 100,000 -> Approved: 1 for 40,000)
        partial_res = await client.post(
            f"/api/v1/requirements/{req_id_1}/decision",
            json={
                "action": "PARTIALLY_APPROVE",
                "approved_quantity": 1,
                "approved_value": 40000.0,
                "admin_notes": "Approved 1 unit subject to regional warehouse stock allocation",
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert partial_res.status_code == 200, f"Partial approval failed: {partial_res.text}"
        part_data = partial_res.json()
        assert part_data["status"] == "PARTIALLY_APPROVED"
        # Verify requested values remain untouched
        assert part_data["quantity"] == 2, "Original requested quantity must be preserved"
        assert part_data["expected_value"] == 100000.0, "Original expected value must be preserved"
        # Verify admin approved values
        assert part_data["approved_quantity"] == 1
        assert part_data["approved_value"] == 40000.0
        assert "Approved 1 unit" in part_data["admin_notes"]
        assert part_data["decider_name"] is not None
        assert part_data["decided_at"] is not None

        # 7. Create Requirement 2 and REJECT it
        req_payload_2 = {
            "customer_id": str(customer.id),
            "brand": "Usha",
            "product_details": "10 x Industrial Coolers",
            "quantity": 10,
            "expected_value": 250000.0,
            "notes": "Testing rejection flow",
        }
        res2 = await client.post(
            f"/api/v1/customers/{customer.id}/requirements",
            json=req_payload_2,
            headers={"Authorization": f"Bearer {employee_token}"},
        )
        assert res2.status_code == 201
        data2 = res2.json()
        req_id_2 = uuid.UUID(data2["id"])

        reject_res = await client.post(
            f"/api/v1/requirements/{req_id_2}/decision",
            json={
                "action": "REJECT",
                "admin_notes": "Discontinued model; please propose alternate catalog item",
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert reject_res.status_code == 200
        rej_data = reject_res.json()
        assert rej_data["status"] == "REJECTED"
        assert rej_data["approved_quantity"] is None
        assert rej_data["admin_notes"] == "Discontinued model; please propose alternate catalog item"

        # 8. Test Status Filtering
        list_pending = await client.get(
            "/api/v1/requirements?status=PENDING",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert list_pending.status_code == 200
        pending_ids = [r["id"] for r in list_pending.json()]
        assert str(req_id_1) not in pending_ids
        assert str(req_id_2) not in pending_ids

        list_partial = await client.get(
            "/api/v1/requirements?status=PARTIALLY_APPROVED",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert list_partial.status_code == 200
        partial_ids = [r["id"] for r in list_partial.json()]
        assert str(req_id_1) in partial_ids

        list_rejected = await client.get(
            "/api/v1/requirements?status=REJECTED",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert list_rejected.status_code == 200
        rejected_ids = [r["id"] for r in list_rejected.json()]
        assert str(req_id_2) in rejected_ids

    finally:
        # 9. Clean up test database records (Rule: ZERO test residue)
        async with AsyncSessionLocal() as clean_session:
            if req_id_1:
                await clean_session.execute(delete(VisitMedia).where(VisitMedia.note.like(f"%{req_id_1}%")))
                await clean_session.execute(delete(CustomerRequirement).where(CustomerRequirement.id == req_id_1))
            if req_id_2:
                await clean_session.execute(delete(CustomerRequirement).where(CustomerRequirement.id == req_id_2))
            if visit_id:
                await clean_session.execute(delete(Visit).where(Visit.id == visit_id))
            await clean_session.commit()
