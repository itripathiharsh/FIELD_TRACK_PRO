"""
Integration: media lifecycle (scenarios 26-30).

The backend media pipeline was found healthy in the audit; these tests lock
that behaviour in before repairs begin, and pin the contract the UI needs
(FT-015: the UI compares media_type against a MIME string, and fetches the
download URL without an Authorization header).
"""
from __future__ import annotations

import os
import uuid

import pytest
import pytest_asyncio
from httpx import AsyncClient

from app.config import settings
from tests.integration.conftest import VALID_JPEG, create_visit, requires_db

pytestmark = [requires_db, pytest.mark.integration, pytest.mark.asyncio]

VALID_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 128
VALID_PDF = b"%PDF-1.4\n" + b"\x00" * 128


@pytest_asyncio.fixture
async def visit_id(client, admin_headers, seeded_world, created_visits) -> str:
    return await create_visit(
        client, admin_headers, seeded_world["customer_id"],
        seeded_world["employee_id"], created_visits,
    )


# --- Scenario 26: upload ----------------------------------------------------

async def test_upload_photo_succeeds_and_persists(
    client: AsyncClient, employee_headers, visit_id, created_media, db
):
    resp = await client.post(
        f"/api/v1/visits/{visit_id}/media",
        files={"file": ("site_photo.jpg", VALID_JPEG, "image/jpeg")},
        headers=employee_headers,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    created_media.append(body["id"])

    assert body["media_type"] == "PHOTO"
    assert body["file_size_bytes"] == len(VALID_JPEG)

    row = db.fetch_one("SELECT storage_key, visit_id FROM visit_media WHERE id = %s", (body["id"],))
    assert row is not None, "media metadata must be committed"
    assert str(row["visit_id"]) == visit_id


async def test_uploaded_bytes_actually_reach_storage(
    client: AsyncClient, employee_headers, visit_id, created_media
):
    """
    FT-047 guard: a DB row must correspond to real bytes on disk. The existing
    seed row points at a file that does not exist.
    """
    resp = await client.post(
        f"/api/v1/visits/{visit_id}/media",
        files={"file": ("proof.jpg", VALID_JPEG, "image/jpeg")},
        headers=employee_headers,
    )
    assert resp.status_code == 201
    created_media.append(resp.json()["id"])

    key = resp.json()["storage_key"]
    path = os.path.join(os.path.abspath(settings.media_storage_path), key)
    assert os.path.isfile(path), f"stored object missing on disk for key {key}"
    with open(path, "rb") as fh:
        assert fh.read() == VALID_JPEG


async def test_pdf_upload_is_classified_as_document(
    client: AsyncClient, employee_headers, visit_id, created_media
):
    resp = await client.post(
        f"/api/v1/visits/{visit_id}/media",
        files={"file": ("contract.pdf", VALID_PDF, "application/pdf")},
        headers=employee_headers,
    )
    assert resp.status_code == 201, resp.text
    created_media.append(resp.json()["id"])
    assert resp.json()["media_type"] == "DOCUMENT"


# --- Scenario 27: retrieval -------------------------------------------------

async def test_uploaded_media_is_listed_for_the_visit(
    client: AsyncClient, employee_headers, visit_id, created_media
):
    up = await client.post(
        f"/api/v1/visits/{visit_id}/media",
        files={"file": ("a.jpg", VALID_JPEG, "image/jpeg")},
        headers=employee_headers,
    )
    assert up.status_code == 201
    created_media.append(up.json()["id"])

    listing = await client.get(f"/api/v1/visits/{visit_id}/media", headers=employee_headers)
    assert listing.status_code == 200, listing.text
    assert up.json()["id"] in [m["id"] for m in listing.json()]


# --- Scenario 28: authenticated download ------------------------------------

async def test_authenticated_download_returns_pre_signed_url(
    client: AsyncClient, employee_headers, visit_id, created_media
):
    """
    Security Design Section 4: access only via pre-signed URLs.
    The download endpoint returns a pre-signed URL, not raw bytes.
    """
    up = await client.post(
        f"/api/v1/visits/{visit_id}/media",
        files={"file": ("photo.jpg", VALID_JPEG, "image/jpeg")},
        headers=employee_headers,
    )
    created_media.append(up.json()["id"])

    dl = await client.get(
        f"/api/v1/media/{up.json()['id']}/download", headers=employee_headers
    )
    assert dl.status_code == 200, dl.text
    body = dl.json()
    assert "download_url" in body, "Response must contain pre-signed URL"
    assert "expires_in_minutes" in body, "Response must contain expiry"
    assert body["expires_in_minutes"] == 15


async def test_presigned_download_url_actually_serves_the_uploaded_bytes(
    client: AsyncClient, employee_headers, visit_id, created_media
):
    """
    P0 fix: the pre-signed download_url returned above must itself be a real,
    fetchable HTTP(S) URL that serves the actual file bytes with no separate
    Authorization header (that's the point of a pre-signed link - it carries
    its own short-lived credential). It previously was a bare `file://
    <server-disk-path>` string, unusable by any remote client (web or
    Android) and carrying no signature or expiry at all.
    """
    up = await client.post(
        f"/api/v1/visits/{visit_id}/media",
        files={"file": ("photo.jpg", VALID_JPEG, "image/jpeg")},
        headers=employee_headers,
    )
    created_media.append(up.json()["id"])

    dl = await client.get(
        f"/api/v1/media/{up.json()['id']}/download", headers=employee_headers
    )
    download_url = dl.json()["download_url"]
    assert download_url.startswith("http://") or download_url.startswith("https://"), (
        f"download_url must be a real fetchable URL, got: {download_url}"
    )

    # Fetch the file itself with NO Authorization header - the signature is
    # the credential, matching how a real pre-signed object-store URL works.
    relative = download_url.split("/api/v1", 1)[1]
    file_resp = await client.get(f"/api/v1{relative}")
    assert file_resp.status_code == 200, file_resp.text
    assert file_resp.content == VALID_JPEG
    assert file_resp.headers["content-type"] == "image/jpeg"


async def test_presigned_download_url_rejects_tampered_signature(
    client: AsyncClient, employee_headers, visit_id, created_media
):
    up = await client.post(
        f"/api/v1/visits/{visit_id}/media",
        files={"file": ("photo.jpg", VALID_JPEG, "image/jpeg")},
        headers=employee_headers,
    )
    created_media.append(up.json()["id"])

    dl = await client.get(
        f"/api/v1/media/{up.json()['id']}/download", headers=employee_headers
    )
    download_url = dl.json()["download_url"]
    relative = download_url.split("/api/v1", 1)[1]
    tampered = relative[:-1] + ("0" if relative[-1] != "0" else "1")

    resp = await client.get(f"/api/v1{tampered}")
    assert resp.status_code == 403


async def test_download_without_auth_is_rejected(
    client: AsyncClient, employee_headers, visit_id, created_media
):
    """
    FT-015: the UI renders <img src=".../download"> and <a href=...>, which the
    browser cannot decorate with a Bearer header. This test documents WHY that
    approach fails, so the fix does not weaken the endpoint.
    """
    up = await client.post(
        f"/api/v1/visits/{visit_id}/media",
        files={"file": ("photo.jpg", VALID_JPEG, "image/jpeg")},
        headers=employee_headers,
    )
    created_media.append(up.json()["id"])

    anon = await client.get(f"/api/v1/media/{up.json()['id']}/download")
    assert anon.status_code in (401, 403), "media must never be publicly downloadable"


# --- Scenario 29: UI preview contract ---------------------------------------

async def test_media_type_is_an_enum_not_a_mime_string(
    client: AsyncClient, employee_headers, visit_id, created_media
):
    """
    FT-015: the UI does `media_type.includes('image')`, which is always false
    because the API returns the enum 'PHOTO'. Pin the real contract.
    """
    up = await client.post(
        f"/api/v1/visits/{visit_id}/media",
        files={"file": ("photo.jpg", VALID_JPEG, "image/jpeg")},
        headers=employee_headers,
    )
    created_media.append(up.json()["id"])

    media_type = up.json()["media_type"]
    assert media_type in ("PHOTO", "DOCUMENT")
    assert "image" not in media_type.lower(), (
        "FT-015: media_type is an enum; the UI must not treat it as a MIME type"
    )


# --- Scenario 30: rejection of unsafe files ---------------------------------

@pytest.mark.parametrize(
    "name,payload,expected",
    [
        ("evil.exe", b"MZ\x90\x00\x03\x00\x00\x00", 415),
        ("empty.jpg", b"", 400),
        ("script.js", b"alert('xss')", 415),
        ("fake.jpg", b"<html><script>alert(1)</script></html>", 415),
    ],
)
async def test_unsafe_uploads_rejected(
    client: AsyncClient, employee_headers, visit_id, name, payload, expected
):
    resp = await client.post(
        f"/api/v1/visits/{visit_id}/media",
        files={"file": (name, payload, "application/octet-stream")},
        headers=employee_headers,
    )
    assert resp.status_code == expected, f"{name}: expected {expected}, got {resp.status_code}"


async def test_rejected_upload_leaves_no_database_row(
    client: AsyncClient, employee_headers, visit_id, db
):
    before = db.count("visit_media", "visit_id = %s", (visit_id,))
    await client.post(
        f"/api/v1/visits/{visit_id}/media",
        files={"file": ("evil.exe", b"MZ\x90\x00", "application/octet-stream")},
        headers=employee_headers,
    )
    assert db.count("visit_media", "visit_id = %s", (visit_id,)) == before


# --- Ownership --------------------------------------------------------------

async def test_employee_cannot_upload_to_another_employees_visit(
    client: AsyncClient, other_employee_headers, visit_id, db
):
    before = db.count("visit_media", "visit_id = %s", (visit_id,))
    resp = await client.post(
        f"/api/v1/visits/{visit_id}/media",
        files={"file": ("x.jpg", VALID_JPEG, "image/jpeg")},
        headers=other_employee_headers,
    )
    assert resp.status_code == 403
    assert db.count("visit_media", "visit_id = %s", (visit_id,)) == before


async def test_employee_cannot_download_another_employees_media(
    client: AsyncClient, employee_headers, other_employee_headers, visit_id, created_media
):
    up = await client.post(
        f"/api/v1/visits/{visit_id}/media",
        files={"file": ("private.jpg", VALID_JPEG, "image/jpeg")},
        headers=employee_headers,
    )
    created_media.append(up.json()["id"])

    resp = await client.get(
        f"/api/v1/media/{up.json()['id']}/download", headers=other_employee_headers
    )
    assert resp.status_code == 403


# --- Deletion ---------------------------------------------------------------

async def test_delete_removes_row_and_stored_object(
    client: AsyncClient, employee_headers, visit_id, db
):
    up = await client.post(
        f"/api/v1/visits/{visit_id}/media",
        files={"file": ("temp.jpg", VALID_JPEG, "image/jpeg")},
        headers=employee_headers,
    )
    media_id, key = up.json()["id"], up.json()["storage_key"]
    path = os.path.join(os.path.abspath(settings.media_storage_path), key)
    assert os.path.isfile(path)

    resp = await client.delete(f"/api/v1/media/{media_id}", headers=employee_headers)
    assert resp.status_code == 204
    assert db.fetch_one("SELECT id FROM visit_media WHERE id = %s", (media_id,)) is None
    assert not os.path.isfile(path), "storage object must be removed with its metadata"


async def test_missing_media_returns_404(client: AsyncClient, admin_headers):
    resp = await client.get(f"/api/v1/media/{uuid.uuid4()}", headers=admin_headers)
    assert resp.status_code == 404
