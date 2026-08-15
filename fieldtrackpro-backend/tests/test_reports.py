"""
Reports endpoint regression tests.

Pins the true backend contract for report endpoints: they serve JSON report
data only. They do NOT stream PDF/CSV files, do NOT emit Content-Disposition,
and do NOT expose any file/temporary/UUID names. Downloads are assembled
entirely client-side, so a UUID filename can never originate from the backend.
"""
from __future__ import annotations

import pytest
from httpx import AsyncClient

from tests.conftest import admin_headers, requires_db

REPORT_ENDPOINTS = [
    "/api/v1/reports/employees",
    "/api/v1/reports/productivity",
    "/api/v1/reports/geo-verification",
]


@requires_db
@pytest.mark.asyncio
async def test_report_endpoints_return_json_with_no_file_headers(client: AsyncClient):
    for path in REPORT_ENDPOINTS:
        resp = await client.get(path, headers=admin_headers())
        assert resp.status_code == 200, f"{path} -> {resp.status_code}"
        # Reports are JSON payloads, never served as downloadable files.
        assert resp.headers.get("content-type", "").startswith("application/json"), (
            f"{path} must return application/json, got {resp.headers.get('content-type')}"
        )
        # No Content-Disposition means the backend never supplies a filename -
        # therefore it cannot leak a UUID/temporary filename for reports.
        assert "content-disposition" not in resp.headers, (
            f"{path} unexpectedly serves a file with Content-Disposition"
        )
        # Body must parse as JSON (array or object), not as bytes of a file.
        try:
            body = resp.json()
        except Exception:
            pytest.fail(f"{path} body is not JSON")
        assert isinstance(body, (list, dict))


@requires_db
@pytest.mark.asyncio
async def test_report_endpoints_require_admin(client: AsyncClient):
    for path in REPORT_ENDPOINTS:
        # No Authorization header at all -> 401 (never a file response).
        resp = await client.get(path)
        assert resp.status_code == 401, f"{path} without auth -> {resp.status_code}"
