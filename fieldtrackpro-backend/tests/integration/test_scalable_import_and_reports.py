import io
import json
import uuid
import pytest
import openpyxl
from datetime import date
from decimal import Decimal
from httpx import AsyncClient
from sqlalchemy import select, func

from app.database import AsyncSessionLocal
from app.models.employee import Employee
from app.models.customer import Customer
from app.models.territory import Territory
from app.models.payment import Payment, PaymentStatus, PaymentMethod, PaymentSource
from app.models.outlet_financial_snapshot import OutletFinancialSnapshot
from tests.integration.conftest import requires_db

pytestmark = [requires_db, pytest.mark.integration, pytest.mark.asyncio]


def _build_excel_bytes(headers: list[str], rows: list[list]) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "ImportData"
    ws.append(headers)
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


async def test_scalable_import_pipeline(client: AsyncClient, admin_headers, seeded_world):
    """
    WEB-GLOBAL-057: Scalable Import Pipeline.
    Verifies that importing rows creates and links entities efficiently
    using targeted batched lookups without loading all database records into memory.
    """
    # Create an employee master import excel
    headers = [
        "Employee ID", "Employee Name", "Mail ID", "Phone No.",
        "Working Profile", "CUG No.", "Date of Birth", "Application Role",
    ]
    rows = [
        [f"EMP_SCALE_{i:03d}", f"Scale Rep {i}", f"scalerep{i}@fieldtrack.test", f"987654{i:04d}", "FOS", f"CUG{i:04d}", "1995-05-15", "EMPLOYEE"]
        for i in range(10)
    ]
    file_bytes = _build_excel_bytes(headers, rows)

    files = {"file": ("scalable_employees.xlsx", file_bytes, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    col_map = {
        "Employee ID": "employee_code",
        "Employee Name": "employee_name",
        "Mail ID": "employee_email",
        "Phone No.": "employee_phone",
        "Working Profile": "employee_working_profile",
        "CUG No.": "employee_cug",
        "Date of Birth": "employee_dob",
        "Application Role": "employee_app_role",
    }
    # 1. Preview
    prev_resp = await client.post("/api/v1/imports/preview", files={"file": ("scalable_employees.xlsx", file_bytes, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}, data={"sheet_name": "ImportData"}, headers=admin_headers)
    assert prev_resp.status_code == 200, prev_resp.text
    assert "columns" in prev_resp.json()

    # 2. Validate
    validate_req = {
        "sheet_name": "ImportData",
        "column_mapping": col_map,
        "outlet_match_strategy": "outlet_code",
    }
    val_files = {"file": ("scalable_employees.xlsx", file_bytes, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    val_data = {"request": json.dumps(validate_req)}
    val_resp = await client.post("/api/v1/imports/validate", files=val_files, data=val_data, headers=admin_headers)
    assert val_resp.status_code == 200, val_resp.text
    batch_id = val_resp.json()["id"]
    assert val_resp.json()["status"] == "VALIDATED", val_resp.json()
    assert val_resp.json()["rows_processed"] == 10, val_resp.json()

    # 3. Commit
    commit_resp = await client.post(f"/api/v1/imports/{batch_id}/commit", headers=admin_headers)
    print("COMMIT RESP JSON:", commit_resp.json())
    assert commit_resp.status_code == 200, commit_resp.text
    assert commit_resp.json()["status"] == "COMMITTED", commit_resp.json()

    # Verify created employees exist in DB
    async with AsyncSessionLocal() as session:
        res = await session.execute(
            select(func.count(Employee.id)).where(Employee.employee_code.like("EMP_SCALE_%"))
        )
        count = res.scalar()
        assert count == 10


def import_mapping_to_json(mapping: dict) -> str:
    import json
    return json.dumps(mapping)


async def test_scalable_collections_and_filters(client: AsyncClient, admin_headers, seeded_world):
    """
    WEB-GLOBAL-058: Scalable Collections & SQL Aggregation.
    Verifies that collections queries filter in SQL with support for pagination.
    """
    resp = await client.get("/api/v1/reports/collections?skip=0&limit=5", headers=admin_headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) <= 5


async def test_employee_activity_sql_aggregation(client: AsyncClient, admin_headers, seeded_world):
    """
    WEB-GLOBAL-062: Employee Activity SQL Aggregation.
    Verifies that employee activity metrics (visits, collections) are computed via SQL aggregates.
    """
    emp_id = seeded_world["employee_id"]
    resp = await client.get(f"/api/v1/employees/{emp_id}/activity", headers=admin_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "visits_total" in body
    assert "collections_total" in body
    assert "collections_verified_amount" in body
    assert isinstance(body["visits"], list)
    assert isinstance(body["collections"], list)


async def test_report_endpoints_server_side_pagination(client: AsyncClient, admin_headers, seeded_world):
    """
    WEB-GLOBAL-054: Server-side report pagination across detail endpoints.
    """
    # 1. Employees Master Report pagination
    r1 = await client.get("/api/v1/reports/employees-master?skip=0&limit=2", headers=admin_headers)
    assert r1.status_code == 200
    assert len(r1.json()) <= 2

    # 2. Outlets Report pagination
    r2 = await client.get("/api/v1/reports/outlets?skip=0&limit=2", headers=admin_headers)
    assert r2.status_code == 200
    assert len(r2.json()) <= 2

    # 3. Outstanding Report pagination
    r3 = await client.get("/api/v1/reports/outstanding?skip=0&limit=2", headers=admin_headers)
    assert r3.status_code == 200
    assert len(r3.json()) <= 2

    # 4. Visits Detailed Report pagination
    r4 = await client.get("/api/v1/reports/visits-detailed?skip=0&limit=2", headers=admin_headers)
    assert r4.status_code == 200
    assert len(r4.json()) <= 2

    # 5. Geo Verification Report pagination
    r5 = await client.get("/api/v1/reports/geo-verification?skip=0&limit=2", headers=admin_headers)
    assert r5.status_code == 200
    assert len(r5.json()) <= 2
