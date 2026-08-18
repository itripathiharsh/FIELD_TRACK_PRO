import uuid
import pytest
from httpx import AsyncClient

from tests.conftest import admin_headers, requires_db

pytestmark = [pytest.mark.asyncio, requires_db]

async def test_employee_registration_success(client: AsyncClient):
    uid = uuid.uuid4().hex[:8]
    response = await client.post(
        "/api/v1/employees/register",
        json={
            "user": {
                "email": f"new.emp.{uid}@fieldtrackpro.com",
                "mobile_number": f"9990{uid[:6].replace('a','1').replace('b','2').replace('c','3').replace('d','4').replace('e','5').replace('f','6')}",
                "password": "Password123!",
                "role": "EMPLOYEE"
            },
            "full_name": "New Employee",
            "employee_code": f"EMP-{uid}"
        },
        headers=admin_headers()
    )
    assert response.status_code == 201
    data = response.json()
    assert data["full_name"] == "New Employee"
    assert data["employee_code"] == f"EMP-{uid}"
    assert data["user"]["email"] == f"new.emp.{uid}@fieldtrackpro.com"

async def test_employee_registration_duplicate_code(client: AsyncClient):
    uid = uuid.uuid4().hex[:8]
    code = f"EMP-{uid}"
    
    # First registration
    await client.post(
        "/api/v1/employees/register",
        json={
            "user": {
                "email": f"emp1.{uid}@fieldtrackpro.com",
                "mobile_number": f"1110{uid[:6].replace('a','1').replace('b','2').replace('c','3').replace('d','4').replace('e','5').replace('f','6')}",
                "password": "Password123!",
                "role": "EMPLOYEE"
            },
            "full_name": "Employee 1",
            "employee_code": code
        },
        headers=admin_headers()
    )
    
    # Second registration with same code
    response = await client.post(
        "/api/v1/employees/register",
        json={
            "user": {
                "email": f"emp2.{uid}@fieldtrackpro.com",
                "mobile_number": f"2220{uid[:6].replace('a','1').replace('b','2').replace('c','3').replace('d','4').replace('e','5').replace('f','6')}",
                "password": "Password123!",
                "role": "EMPLOYEE"
            },
            "full_name": "Employee 2",
            "employee_code": code
        },
        headers=admin_headers()
    )
    assert response.status_code == 409
    data = response.json()
    assert f"Employee code '{code}' is already in use" in data["error"]["message"]

async def test_employee_registration_duplicate_email(client: AsyncClient):
    uid = uuid.uuid4().hex[:8]
    email = f"dup.{uid}@fieldtrackpro.com"
    
    await client.post(
        "/api/v1/employees/register",
        json={
            "user": {
                "email": email,
                "mobile_number": f"5550{uid[:6].replace('a','1').replace('b','2').replace('c','3').replace('d','4').replace('e','5').replace('f','6')}",
                "password": "Password123!",
                "role": "EMPLOYEE"
            },
            "full_name": "Dup 1",
            "employee_code": f"DUP1-{uid}"
        },
        headers=admin_headers()
    )
    
    response = await client.post(
        "/api/v1/employees/register",
        json={
            "user": {
                "email": email,
                "mobile_number": f"6660{uid[:6].replace('a','1').replace('b','2').replace('c','3').replace('d','4').replace('e','5').replace('f','6')}",
                "password": "Password123!",
                "role": "EMPLOYEE"
            },
            "full_name": "Dup 2",
            "employee_code": f"DUP2-{uid}"
        },
        headers=admin_headers()
    )
    assert response.status_code == 409
    data = response.json()
    assert f"Email '{email}' is already in use" in data["error"]["message"]

async def test_employee_registration_duplicate_mobile(client: AsyncClient):
    uid = uuid.uuid4().hex[:8]
    mobile = f"4440{uid[:6].replace('a','1').replace('b','2').replace('c','3').replace('d','4').replace('e','5').replace('f','6')}"
    
    await client.post(
        "/api/v1/employees/register",
        json={
            "user": {
                "email": f"mob1.{uid}@fieldtrackpro.com",
                "mobile_number": mobile,
                "password": "Password123!",
                "role": "EMPLOYEE"
            },
            "full_name": "Mob 1",
            "employee_code": f"MOB1-{uid}"
        },
        headers=admin_headers()
    )
    
    response = await client.post(
        "/api/v1/employees/register",
        json={
            "user": {
                "email": f"mob2.{uid}@fieldtrackpro.com",
                "mobile_number": mobile,
                "password": "Password123!",
                "role": "EMPLOYEE"
            },
            "full_name": "Mob 2",
            "employee_code": f"MOB2-{uid}"
        },
        headers=admin_headers()
    )
    assert response.status_code == 409
    data = response.json()
    assert f"Mobile number '{mobile}' is already in use" in data["error"]["message"]
