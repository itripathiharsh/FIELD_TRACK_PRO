import pytest
from httpx import AsyncClient
from tests.conftest import admin_headers, employee_headers, requires_db


@requires_db
@pytest.mark.asyncio
async def test_field_exceptions_and_dashboard_flow(client: AsyncClient):
    # 1. Fetch customers and visits
    cust_res = await client.get("/api/v1/customers", headers=admin_headers())
    assert cust_res.status_code == 200
    customers = cust_res.json()
    assert len(customers) > 0
    customer_id = customers[0]["id"]

    # 2. File a field exception as employee
    exc_payload = {
        "customer_id": customer_id,
        "exception_type": "VEHICLE_BREAKDOWN",
        "description": "Bike breakdown near highway on way to outlet.",
    }
    create_res = await client.post("/api/v1/field-exceptions", json=exc_payload, headers=employee_headers())
    assert create_res.status_code == 201
    exc_data = create_res.json()
    assert exc_data["status"] == "PENDING_REVIEW"
    assert exc_data["exception_type"] == "VEHICLE_BREAKDOWN"
    exception_id = exc_data["id"]

    # 3. List exceptions as admin
    list_res = await client.get("/api/v1/field-exceptions", headers=admin_headers())
    assert list_res.status_code == 200
    items = list_res.json()
    assert any(i["id"] == exception_id for i in items)

    # 4. Review exception as Admin (Approve)
    review_payload = {
        "status": "APPROVED",
        "admin_notes": "Breakdown verified by ASM. Approved.",
    }
    review_res = await client.patch(
        f"/api/v1/field-exceptions/{exception_id}/review",
        json=review_payload,
        headers=admin_headers(),
    )
    assert review_res.status_code == 200
    reviewed_data = review_res.json()
    assert reviewed_data["status"] == "APPROVED"
    assert reviewed_data["admin_notes"] == "Breakdown verified by ASM. Approved."

    # 5. Get Dashboard Summary (Admin)
    dash_res = await client.get("/api/v1/dashboard/summary", headers=admin_headers())
    assert dash_res.status_code == 200
    dash_data = dash_res.json()
    assert "kpis" in dash_data
    assert "brand_breakdown" in dash_data
    assert dash_data["kpis"]["total_outlets"] > 0
    assert float(dash_data["kpis"]["total_sales"]) > 0

    # 6. Get Employee My-Day Dashboard
    my_day_res = await client.get("/api/v1/dashboard/my-day", headers=employee_headers())
    assert my_day_res.status_code == 200
    my_day_data = my_day_res.json()
    assert "employee_id" in my_day_data
    assert "assigned_outlets_count" in my_day_data
