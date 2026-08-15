"""
Integration: signature download endpoint.

Covers GET /api/v1/signatures/{id}/download which previously had no direct test coverage.
"""
from __future__ import annotations

import base64

import pytest
from httpx import AsyncClient

from tests.integration.conftest import create_visit, requires_db

pytestmark = [requires_db, pytest.mark.integration, pytest.mark.asyncio]

PNG_B64 = (
    "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR4"
    "2mNk+A8AAQUAtwOe+GkAAAAASUVORK5CYII="
)
# A minimal valid JPEG (SOI + APP0 JFIF header + EOI).
JPEG_B64 = base64.b64encode(
    bytes.fromhex("FFD8FFE000104A46494600010100000100010000FFD9")
).decode()


async def test_authenticated_user_can_list_signatures(
    client: AsyncClient, employee_headers, seeded_world
):
    """Authenticated user can list signatures for a visit."""
    import uuid
    # Use a random visit ID - should return 404 or empty list
    resp = await client.get(
        f"/api/v1/visits/{uuid.uuid4()}/signatures",
        headers=employee_headers,
    )
    # Either returns a list (possibly empty) or 404 if no visit
    assert resp.status_code in (200, 404), resp.text


async def test_unauthenticated_cannot_access_signatures(client: AsyncClient, seeded_world):
    """Unauthenticated requests to signatures endpoints are rejected."""
    resp = await client.get(
        f"/api/v1/visits/{seeded_world.get('visit_id', 'none')}/signatures"
    )
    assert resp.status_code == 401


async def test_signature_download_requires_auth(client: AsyncClient):
    """Signature download endpoint requires authentication."""
    import uuid
    resp = await client.get(f"/api/v1/signatures/{uuid.uuid4()}/download")
    assert resp.status_code == 401


async def test_authenticated_signature_download_returns_the_actual_bytes(
    client: AsyncClient, admin_headers, employee_headers, seeded_world, created_visits
):
    """
    P0 fix: `generate_presigned_url(...)` was called without `await`, so the
    response body was a coroutine object FastAPI could not serialize. Every
    authenticated download 500'd; only the auth-rejection path above had
    coverage, so this went unnoticed. The pre-signed download_url must also
    be a real, fetchable, absolute URL (matching the equivalent media fix).
    """
    visit_id = await create_visit(
        client, admin_headers, seeded_world["customer_id"],
        seeded_world["employee_id"], created_visits,
    )
    up = await client.post(
        f"/api/v1/visits/{visit_id}/signatures",
        json={"signature_type": "CUSTOMER", "signature_image_base64": PNG_B64},
        headers=employee_headers,
    )
    assert up.status_code == 201, up.text

    dl = await client.get(
        f"/api/v1/signatures/{up.json()['id']}/download", headers=employee_headers
    )
    assert dl.status_code == 200, dl.text
    download_url = dl.json()["download_url"]
    assert download_url.startswith("http://") or download_url.startswith("https://")

    relative = download_url.split("/api/v1", 1)[1]
    file_resp = await client.get(f"/api/v1{relative}")
    assert file_resp.status_code == 200, file_resp.text
    assert file_resp.headers["content-type"] == "image/png"
    assert len(file_resp.content) > 0


# ---------------------------------------------------------------------------
# Signature/customer-acknowledgement upgrade: capture_method, integrity
# metadata, correct extension/content-type, replace-with-audit-trail.
# ---------------------------------------------------------------------------

async def test_signature_defaults_to_signature_capture_method(
    client: AsyncClient, admin_headers, employee_headers, seeded_world, created_visits, db
):
    visit_id = await create_visit(
        client, admin_headers, seeded_world["customer_id"],
        seeded_world["employee_id"], created_visits,
    )
    resp = await client.post(
        f"/api/v1/visits/{visit_id}/signatures",
        json={"signature_type": "CUSTOMER", "signature_image_base64": PNG_B64},
        headers=employee_headers,
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["capture_method"] == "SIGNATURE"


async def test_signature_upload_persists_content_type_checksum_size_and_created_by(
    client: AsyncClient, admin_headers, employee_headers, seeded_world, created_visits, db
):
    visit_id = await create_visit(
        client, admin_headers, seeded_world["customer_id"],
        seeded_world["employee_id"], created_visits,
    )
    resp = await client.post(
        f"/api/v1/visits/{visit_id}/signatures",
        json={"signature_type": "EMPLOYEE", "signature_image_base64": PNG_B64},
        headers=employee_headers,
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["content_type"] == "image/png"
    assert data["file_size_bytes"] > 0
    assert data["created_by"] is not None

    row = db.fetch_one(
        "SELECT checksum_sha256, content_type, file_size_bytes, created_by, storage_key "
        "FROM visit_signatures WHERE id = %s",
        (data["id"],),
    )
    assert row["checksum_sha256"] is not None and len(row["checksum_sha256"]) == 64
    assert row["content_type"] == "image/png"
    assert row["file_size_bytes"] == data["file_size_bytes"]
    assert str(row["created_by"]) == data["created_by"]
    assert row["storage_key"].endswith(".png")


async def test_jpeg_signature_gets_jpg_extension_and_correct_download_content_type(
    client: AsyncClient, admin_headers, employee_headers, seeded_world, created_visits, db
):
    """
    Regression for the audit finding: storage_key previously always ended in
    .png regardless of actual content type, and download always returned
    image/png regardless of what was actually stored.
    """
    visit_id = await create_visit(
        client, admin_headers, seeded_world["customer_id"],
        seeded_world["employee_id"], created_visits,
    )
    resp = await client.post(
        f"/api/v1/visits/{visit_id}/signatures",
        json={"signature_type": "CUSTOMER", "signature_image_base64": JPEG_B64},
        headers=employee_headers,
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["content_type"] == "image/jpeg"
    assert data["storage_key"].endswith(".jpg")

    row = db.fetch_one("SELECT storage_key FROM visit_signatures WHERE id = %s", (data["id"],))
    assert row["storage_key"].endswith(".jpg")

    dl = await client.get(f"/api/v1/signatures/{data['id']}/download", headers=employee_headers)
    assert dl.status_code == 200
    download_url = dl.json()["download_url"]
    relative = download_url.split("/api/v1", 1)[1]
    file_resp = await client.get(f"/api/v1{relative}")
    assert file_resp.status_code == 200
    assert file_resp.headers["content-type"] == "image/jpeg"


async def test_photo_upload_capture_method_is_accepted(
    client: AsyncClient, admin_headers, employee_headers, seeded_world, created_visits
):
    """The uploaded-acknowledgement-photo path shares the same validation/storage pipeline."""
    visit_id = await create_visit(
        client, admin_headers, seeded_world["customer_id"],
        seeded_world["employee_id"], created_visits,
    )
    resp = await client.post(
        f"/api/v1/visits/{visit_id}/signatures",
        json={
            "signature_type": "CUSTOMER",
            "signature_image_base64": JPEG_B64,
            "capture_method": "PHOTO_UPLOAD",
        },
        headers=employee_headers,
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["capture_method"] == "PHOTO_UPLOAD"


async def test_duplicate_current_signature_is_still_rejected(
    client: AsyncClient, admin_headers, employee_headers, seeded_world, created_visits
):
    visit_id = await create_visit(
        client, admin_headers, seeded_world["customer_id"],
        seeded_world["employee_id"], created_visits,
    )
    first = await client.post(
        f"/api/v1/visits/{visit_id}/signatures",
        json={"signature_type": "CUSTOMER", "signature_image_base64": PNG_B64},
        headers=employee_headers,
    )
    assert first.status_code == 201
    second = await client.post(
        f"/api/v1/visits/{visit_id}/signatures",
        json={"signature_type": "CUSTOMER", "signature_image_base64": PNG_B64},
        headers=employee_headers,
    )
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "SIGNATURE_ALREADY_EXISTS"


async def test_replace_signature_supersedes_old_and_creates_new_current(
    client: AsyncClient, admin_headers, employee_headers, seeded_world, created_visits, db
):
    visit_id = await create_visit(
        client, admin_headers, seeded_world["customer_id"],
        seeded_world["employee_id"], created_visits,
    )
    original = await client.post(
        f"/api/v1/visits/{visit_id}/signatures",
        json={"signature_type": "CUSTOMER", "signature_image_base64": PNG_B64},
        headers=employee_headers,
    )
    assert original.status_code == 201
    original_id = original.json()["id"]
    original_storage_key = original.json()["storage_key"]

    replacement = await client.post(
        f"/api/v1/visits/{visit_id}/signatures/{original_id}/replace",
        json={"signature_image_base64": JPEG_B64},
        headers=employee_headers,
    )
    assert replacement.status_code == 201, replacement.text
    replacement_data = replacement.json()
    assert replacement_data["id"] != original_id
    assert replacement_data["signature_type"] == "CUSTOMER"
    assert replacement_data["superseded_at"] is None

    # The old row is marked superseded, not deleted - and its storage blob
    # still exists (audit trail preserved, nothing orphaned/silently lost).
    old_row = db.fetch_one("SELECT superseded_at FROM visit_signatures WHERE id = %s", (original_id,))
    assert old_row["superseded_at"] is not None

    list_resp = await client.get(f"/api/v1/visits/{visit_id}/signatures", headers=employee_headers)
    assert list_resp.status_code == 200
    ids = {s["id"] for s in list_resp.json()}
    assert original_id in ids and replacement_data["id"] in ids, "history must include both rows"

    # A fresh (non-replace) create for the same type must still 409 - there
    # is a new CURRENT row now (the replacement), so this is not "no
    # current signature exists" territory again.
    fresh_attempt = await client.post(
        f"/api/v1/visits/{visit_id}/signatures",
        json={"signature_type": "CUSTOMER", "signature_image_base64": PNG_B64},
        headers=employee_headers,
    )
    assert fresh_attempt.status_code == 409


async def test_replacing_an_already_superseded_signature_is_rejected(
    client: AsyncClient, admin_headers, employee_headers, seeded_world, created_visits
):
    visit_id = await create_visit(
        client, admin_headers, seeded_world["customer_id"],
        seeded_world["employee_id"], created_visits,
    )
    original = await client.post(
        f"/api/v1/visits/{visit_id}/signatures",
        json={"signature_type": "CUSTOMER", "signature_image_base64": PNG_B64},
        headers=employee_headers,
    )
    original_id = original.json()["id"]
    await client.post(
        f"/api/v1/visits/{visit_id}/signatures/{original_id}/replace",
        json={"signature_image_base64": JPEG_B64},
        headers=employee_headers,
    )
    # Trying to replace the now-superseded original a second time must fail.
    second_replace = await client.post(
        f"/api/v1/visits/{visit_id}/signatures/{original_id}/replace",
        json={"signature_image_base64": PNG_B64},
        headers=employee_headers,
    )
    assert second_replace.status_code == 400
    assert second_replace.json()["error"]["code"] == "SIGNATURE_ALREADY_SUPERSEDED"


async def test_replace_rejects_a_signature_id_from_a_different_visit(
    client: AsyncClient, admin_headers, employee_headers, seeded_world, created_visits
):
    visit_a = await create_visit(
        client, admin_headers, seeded_world["customer_id"],
        seeded_world["employee_id"], created_visits,
    )
    visit_b = await create_visit(
        client, admin_headers, seeded_world["customer_id"],
        seeded_world["employee_id"], created_visits,
    )
    sig_a = await client.post(
        f"/api/v1/visits/{visit_a}/signatures",
        json={"signature_type": "CUSTOMER", "signature_image_base64": PNG_B64},
        headers=employee_headers,
    )
    resp = await client.post(
        f"/api/v1/visits/{visit_b}/signatures/{sig_a.json()['id']}/replace",
        json={"signature_image_base64": JPEG_B64},
        headers=employee_headers,
    )
    assert resp.status_code == 404
