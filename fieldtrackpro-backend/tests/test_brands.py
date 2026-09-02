import pytest
import uuid
from httpx import AsyncClient, ASGITransport

from app.main import app
from tests.conftest import make_admin_token, make_employee_token


@pytest.mark.asyncio
async def test_list_brands():
    token = make_employee_token()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/brands", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        names = [b["name"] for b in data]
        assert "USHA" in names
        assert "Zebronics" in names
        assert "Lund" not in names


@pytest.mark.asyncio
async def test_create_brand_and_duplicate_prevention():
    token = make_employee_token()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Create a unique new brand
        unique_name = f"Daikin AC {uuid.uuid4().hex[:4]}"
        create_resp = await client.post(
            "/api/v1/brands",
            json={"name": unique_name},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert create_resp.status_code == 201
        created = create_resp.json()
        assert created["name"] == unique_name
        assert created["normalized_name"] == unique_name.lower()
        assert created["is_active"] is True

        # 2. Case-insensitive duplicate rejection
        dup_resp = await client.post(
            "/api/v1/brands",
            json={"name": f"  {unique_name.upper()}  "},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert dup_resp.status_code == 409
        err_json = dup_resp.json()
        msg = err_json.get("error", {}).get("message", "") or err_json.get("detail", "")
        assert "already exists" in msg.lower()


@pytest.mark.asyncio
async def test_empty_and_forbidden_brand_validation():
    token = make_employee_token()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Empty brand
        empty_resp = await client.post(
            "/api/v1/brands",
            json={"name": "   "},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert empty_resp.status_code == 422

        # Forbidden brand
        lund_resp = await client.post(
            "/api/v1/brands",
            json={"name": "Lund"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert lund_resp.status_code == 422


@pytest.mark.asyncio
async def test_admin_patch_brand():
    admin_token = make_admin_token()
    emp_token = make_employee_token()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Create brand
        brand_name = f"Voltas {uuid.uuid4().hex[:4]}"
        create_resp = await client.post(
            "/api/v1/brands",
            json={"name": brand_name},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert create_resp.status_code == 201
        brand_id = create_resp.json()["id"]

        # Employee cannot patch (403)
        emp_patch = await client.patch(
            f"/api/v1/brands/{brand_id}",
            json={"is_active": False},
            headers={"Authorization": f"Bearer {emp_token}"},
        )
        assert emp_patch.status_code == 403

        # Admin can deactivate
        admin_patch = await client.patch(
            f"/api/v1/brands/{brand_id}",
            json={"is_active": False},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert admin_patch.status_code == 200
        assert admin_patch.json()["is_active"] is False

        # Verify active_only filter excludes inactive brand
        active_resp = await client.get("/api/v1/brands?active_only=true", headers={"Authorization": f"Bearer {admin_token}"})
        active_names = [b["name"] for b in active_resp.json()]
        assert brand_name not in active_names

        # Verify active_only=false includes it
        all_resp = await client.get("/api/v1/brands?active_only=false", headers={"Authorization": f"Bearer {admin_token}"})
        all_names = [b["name"] for b in all_resp.json()]
        assert brand_name in all_names
