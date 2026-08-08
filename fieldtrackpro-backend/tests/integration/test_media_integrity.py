"""
Integration: media content integrity (FT-036) and storage consistency (FT-047).
"""
from __future__ import annotations

import hashlib
import os

import pytest
import pytest_asyncio
from httpx import AsyncClient

from app.config import settings
from tests.integration.conftest import VALID_JPEG, create_visit, requires_db

pytestmark = [requires_db, pytest.mark.integration, pytest.mark.asyncio]

SECOND_JPEG = b"\xFF\xD8\xFF\xE0\x00\x10JFIF\x00\x01\x01\x01\x00\x60\x00\x60\x00\x00" + b"\x11" * 300
VALID_PDF = b"%PDF-1.4\n" + b"\x00" * 128


@pytest_asyncio.fixture
async def visit_id(client, admin_headers, seeded_world, created_visits) -> str:
    return await create_visit(
        client, admin_headers, seeded_world["customer_id"],
        seeded_world["employee_id"], created_visits,
    )


# ---------------------------------------------------------------------------
# FT-036 - checksum recorded and correct
# ---------------------------------------------------------------------------

async def test_upload_records_correct_sha256(
    client: AsyncClient, employee_headers, visit_id, created_media, db
):
    resp = await client.post(
        f"/api/v1/visits/{visit_id}/media",
        files={"file": ("evidence.jpg", VALID_JPEG, "image/jpeg")},
        headers=employee_headers,
    )
    assert resp.status_code == 201, resp.text
    created_media.append(resp.json()["id"])

    expected = hashlib.sha256(VALID_JPEG).hexdigest()
    assert resp.json()["checksum_sha256"] == expected

    row = db.fetch_one(
        "SELECT checksum_sha256, original_filename, uploaded_by FROM visit_media WHERE id = %s",
        (resp.json()["id"],),
    )
    assert row["checksum_sha256"] == expected
    assert row["original_filename"] == "evidence.jpg"
    assert row["uploaded_by"] is not None, "provenance must be recorded"


# ---------------------------------------------------------------------------
# FT-036 - duplicate rejection
# ---------------------------------------------------------------------------

async def test_identical_file_rejected_on_same_visit(
    client: AsyncClient, employee_headers, visit_id, created_media, db
):
    """
    Adversarial audit VULN-03: one generic photograph reused as evidence.
    The same bytes must not attach to the same visit twice.
    """
    first = await client.post(
        f"/api/v1/visits/{visit_id}/media",
        files={"file": ("site.jpg", VALID_JPEG, "image/jpeg")},
        headers=employee_headers,
    )
    assert first.status_code == 201
    created_media.append(first.json()["id"])

    duplicate = await client.post(
        f"/api/v1/visits/{visit_id}/media",
        files={"file": ("renamed_but_identical.jpg", VALID_JPEG, "image/jpeg")},
        headers=employee_headers,
    )
    assert duplicate.status_code == 409, "FT-036: identical content was accepted twice"
    assert "already attached" in duplicate.text.lower()

    assert db.count("visit_media", "visit_id = %s", (visit_id,)) == 1


async def test_rejected_duplicate_leaves_no_stored_object(
    client: AsyncClient, employee_headers, visit_id, created_media
):
    """A refused upload must not litter storage."""
    first = await client.post(
        f"/api/v1/visits/{visit_id}/media",
        files={"file": ("a.jpg", VALID_JPEG, "image/jpeg")},
        headers=employee_headers,
    )
    created_media.append(first.json()["id"])

    base = os.path.abspath(settings.media_storage_path)
    before = sum(len(files) for _, _, files in os.walk(base))

    dup = await client.post(
        f"/api/v1/visits/{visit_id}/media",
        files={"file": ("a.jpg", VALID_JPEG, "image/jpeg")},
        headers=employee_headers,
    )
    assert dup.status_code == 409

    after = sum(len(files) for _, _, files in os.walk(base))
    assert after == before, "a rejected duplicate must not write to storage"


async def test_different_content_is_accepted(
    client: AsyncClient, employee_headers, visit_id, created_media, db
):
    """Deduplication must not block genuinely different photographs."""
    for payload, name in ((VALID_JPEG, "one.jpg"), (SECOND_JPEG, "two.jpg")):
        resp = await client.post(
            f"/api/v1/visits/{visit_id}/media",
            files={"file": (name, payload, "image/jpeg")},
            headers=employee_headers,
        )
        assert resp.status_code == 201, f"{name}: {resp.text}"
        created_media.append(resp.json()["id"])

    assert db.count("visit_media", "visit_id = %s", (visit_id,)) == 2


async def test_same_file_allowed_on_a_different_visit(
    client: AsyncClient, admin_headers, employee_headers, seeded_world, created_visits, created_media
):
    """
    The constraint is per visit. Two different sites may legitimately produce
    an identical file (e.g. the same signed form template).
    """
    visit_a = await create_visit(
        client, admin_headers, seeded_world["customer_id"],
        seeded_world["employee_id"], created_visits,
    )
    visit_b = await create_visit(
        client, admin_headers, seeded_world["customer_id"],
        seeded_world["employee_id"], created_visits,
    )

    for vid in (visit_a, visit_b):
        resp = await client.post(
            f"/api/v1/visits/{vid}/media",
            files={"file": ("shared.pdf", VALID_PDF, "application/pdf")},
            headers=employee_headers,
        )
        assert resp.status_code == 201, resp.text
        created_media.append(resp.json()["id"])


# ---------------------------------------------------------------------------
# FT-036 - integrity verified on download
# ---------------------------------------------------------------------------

async def test_download_returns_byte_identical_content(
    client: AsyncClient, employee_headers, visit_id, created_media
):
    up = await client.post(
        f"/api/v1/visits/{visit_id}/media",
        files={"file": ("verify.jpg", VALID_JPEG, "image/jpeg")},
        headers=employee_headers,
    )
    created_media.append(up.json()["id"])

    dl = await client.get(f"/api/v1/media/{up.json()['id']}/download", headers=employee_headers)
    assert dl.status_code == 200
    assert hashlib.sha256(dl.content).hexdigest() == up.json()["checksum_sha256"]


async def test_tampered_storage_object_is_not_served(
    client: AsyncClient, employee_headers, visit_id, created_media
):
    """
    If the stored bytes are altered outside the application, the download must
    fail rather than serve unverified evidence.
    """
    up = await client.post(
        f"/api/v1/visits/{visit_id}/media",
        files={"file": ("tamper.jpg", VALID_JPEG, "image/jpeg")},
        headers=employee_headers,
    )
    created_media.append(up.json()["id"])

    path = os.path.join(os.path.abspath(settings.media_storage_path), up.json()["storage_key"])
    assert os.path.isfile(path)
    with open(path, "wb") as fh:
        fh.write(VALID_JPEG + b"tampered-with")

    resp = await client.get(f"/api/v1/media/{up.json()['id']}/download", headers=employee_headers)
    assert resp.status_code == 500
    assert "integrity" in resp.text.lower()


async def test_download_filename_uses_original_name(
    client: AsyncClient, employee_headers, visit_id, created_media
):
    up = await client.post(
        f"/api/v1/visits/{visit_id}/media",
        files={"file": ("inspection_report.pdf", VALID_PDF, "application/pdf")},
        headers=employee_headers,
    )
    created_media.append(up.json()["id"])

    dl = await client.get(f"/api/v1/media/{up.json()['id']}/download", headers=employee_headers)
    assert dl.status_code == 200
    assert "inspection_report.pdf" in dl.headers.get("content-disposition", "")


# ---------------------------------------------------------------------------
# FT-047 - no orphaned media
# ---------------------------------------------------------------------------

async def test_no_orphaned_media_rows_exist():
    """
    FT-047: every visit_media row must resolve to a real stored object.
    The seed row `uploads/visits/.../site_photo_01.jpg` had no file behind it.
    """
    from app.database import AsyncSessionLocal
    from app.services.media_service import find_orphaned_media

    async with AsyncSessionLocal() as session:
        orphans = await find_orphaned_media(session)

    assert orphans == [], (
        "FT-047: media rows without stored objects: "
        + ", ".join(f"{m.id} -> {m.storage_key}" for m in orphans)
    )


async def test_legacy_uploads_prefix_is_gone(db):
    """The obsolete key format must not reappear."""
    assert db.count("visit_media", "storage_key LIKE 'uploads/%%'") == 0


async def test_deleting_media_leaves_no_orphan(
    client: AsyncClient, employee_headers, visit_id
):
    up = await client.post(
        f"/api/v1/visits/{visit_id}/media",
        files={"file": ("temp.jpg", VALID_JPEG, "image/jpeg")},
        headers=employee_headers,
    )
    media_id = up.json()["id"]
    path = os.path.join(os.path.abspath(settings.media_storage_path), up.json()["storage_key"])
    assert os.path.isfile(path)

    assert (
        await client.delete(f"/api/v1/media/{media_id}", headers=employee_headers)
    ).status_code == 204

    assert not os.path.isfile(path), "storage object must be removed with the row"

    from app.database import AsyncSessionLocal
    from app.services.media_service import find_orphaned_media

    async with AsyncSessionLocal() as session:
        assert await find_orphaned_media(session) == []
