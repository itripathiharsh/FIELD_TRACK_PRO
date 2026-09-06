import io
import uuid
import pytest
from httpx import AsyncClient
from tests.conftest import admin_headers, requires_db


@pytest.mark.asyncio
async def test_preview_import_disabled(client: AsyncClient):
    """Verify that creating Excel import preview is permanently disabled (HTTP 403)."""
    files = {"file": ("test.xlsx", b"dummy content", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    resp = await client.post("/api/v1/imports/preview", files=files, headers=admin_headers())
    assert resp.status_code == 403
    assert "Excel/MIS data import has been permanently disabled" in resp.text


@pytest.mark.asyncio
async def test_validate_import_disabled(client: AsyncClient):
    """Verify that creating Excel import validation is permanently disabled (HTTP 403)."""
    files = {"file": ("test.xlsx", b"dummy content", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    data = {"request": "{}"}
    resp = await client.post("/api/v1/imports/validate", files=files, data=data, headers=admin_headers())
    assert resp.status_code == 403
    assert "Excel/MIS data import has been permanently disabled" in resp.text


@pytest.mark.asyncio
async def test_commit_import_disabled(client: AsyncClient):
    """Verify that committing Excel import is permanently disabled (HTTP 403)."""
    fake_id = uuid.uuid4()
    resp = await client.post(f"/api/v1/imports/{fake_id}/commit", headers=admin_headers())
    assert resp.status_code == 403
    assert "Excel/MIS data import has been permanently disabled" in resp.text


@requires_db
@pytest.mark.asyncio
async def test_historical_import_audit_accessible(client: AsyncClient):
    """Verify that historical audit records remain read-only accessible."""
    resp = await client.get("/api/v1/imports", headers=admin_headers())
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@requires_db
@pytest.mark.asyncio
async def test_fos_mappings_accessible(client: AsyncClient):
    """Verify that FOS mapping reference endpoint remains accessible."""
    resp = await client.get("/api/v1/imports/fos-mappings", headers=admin_headers())
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
