"""
Reports endpoint regression tests for Phase 3 and Phase 4.
"""
from __future__ import annotations

import pytest
from httpx import AsyncClient

from tests.conftest import admin_headers, requires_db

JSON_REPORT_ENDPOINTS = [
    "/api/v1/reports/employees",
    "/api/v1/reports/productivity",
    "/api/v1/reports/geo-verification",
    "/api/v1/reports/overview",
    "/api/v1/reports/employees-master",
    "/api/v1/reports/outlets",
    "/api/v1/reports/outstanding",
    "/api/v1/reports/collections",
    "/api/v1/reports/visits-detailed",
    "/api/v1/reports/business-summary",
    "/api/v1/reports/monthly-periods",
]

EXCEL_EXPORT_ENDPOINTS = [
    "/api/v1/reports/overview/export",
    "/api/v1/reports/employees-master/export",
    "/api/v1/reports/outlets/export",
    "/api/v1/reports/outstanding/export",
    "/api/v1/reports/collections/export",
    "/api/v1/reports/visits-detailed/export",
    "/api/v1/reports/business-summary/export",
]


@requires_db
@pytest.mark.asyncio
async def test_report_endpoints_return_json_with_no_file_headers(client: AsyncClient):
    for path in JSON_REPORT_ENDPOINTS:
        resp = await client.get(path, headers=admin_headers())
        assert resp.status_code == 200, f"{path} -> {resp.status_code}"
        assert resp.headers.get("content-type", "").startswith("application/json"), (
            f"{path} must return application/json, got {resp.headers.get('content-type')}"
        )
        assert "content-disposition" not in resp.headers, (
            f"{path} unexpectedly serves a file with Content-Disposition"
        )
        body = resp.json()
        assert isinstance(body, (list, dict))


@requires_db
@pytest.mark.asyncio
async def test_report_endpoints_require_admin(client: AsyncClient):
    for path in JSON_REPORT_ENDPOINTS:
        resp = await client.get(path)
        assert resp.status_code == 401, f"{path} without auth -> {resp.status_code}"


@requires_db
@pytest.mark.asyncio
async def test_excel_export_endpoints(client: AsyncClient):
    for path in EXCEL_EXPORT_ENDPOINTS:
        resp = await client.get(path, headers=admin_headers())
        assert resp.status_code == 200, f"{path} -> {resp.status_code}"
        assert "spreadsheetml.sheet" in resp.headers.get("content-type", ""), (
            f"{path} must return excel mime type, got {resp.headers.get('content-type')}"
        )
        assert "attachment" in resp.headers.get("content-disposition", "")
        assert len(resp.content) > 0


@requires_db
@pytest.mark.asyncio
async def test_monthly_period_finalize_and_reopen_workflow(client: AsyncClient):
    # 1. Fetch monthly periods
    resp = await client.get("/api/v1/reports/monthly-periods", headers=admin_headers())
    assert resp.status_code == 200
    periods = resp.json()
    assert isinstance(periods, list)

    if periods:
        period_id = periods[0]["id"]
        # 2. Finalize
        fin_resp = await client.post(f"/api/v1/reports/monthly-periods/{period_id}/finalize", headers=admin_headers())
        assert fin_resp.status_code == 200
        fin_data = fin_resp.json()
        assert fin_data["status"] == "FINALIZED"
        assert fin_data["finalized_at"] is not None

        # 3. Reopen
        reopen_resp = await client.post(f"/api/v1/reports/monthly-periods/{period_id}/reopen", headers=admin_headers())
        assert reopen_resp.status_code == 200
        reopen_data = reopen_resp.json()
        assert reopen_data["status"] == "OPEN"
        assert reopen_data["finalized_at"] is None
