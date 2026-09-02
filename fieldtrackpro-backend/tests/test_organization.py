import pytest
from httpx import AsyncClient
from app.core.security import create_access_token
from app.models.user import Role, User
from app.database import AsyncSessionLocal
from app.core.security import hash_password
from tests.conftest import requires_db
import uuid


@requires_db
@pytest.mark.asyncio
async def test_get_organization_profile_dynamic_data(client: AsyncClient):
    async with AsyncSessionLocal() as session:
        admin_user = User(
            email=f"admin_org_{uuid.uuid4().hex[:6]}@fieldtrack.test",
            password_hash=hash_password("AdminPass123!"),
            role=Role.ADMIN,
            is_active=True,
        )
        session.add(admin_user)
        await session.commit()
        token = create_access_token(str(admin_user.id), Role.ADMIN.value)

    resp = await client.get(
        "/api/v1/organization",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "organization_name" in data
    assert "operational_hub" in data
    assert "divisions" in data
    assert "total_employees" in data
    assert "total_customers" in data
    assert "total_territories" in data
    assert "total_areas" in data
    assert "master_brands" in data
    assert isinstance(data["master_brands"], list)
    assert "Lund" not in data["master_brands"]
