"""MinIOStorageProvider behaviour with a fake minio client (no live MinIO needed)."""
from __future__ import annotations

import io
from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest

from app.exceptions.custom import BaseAPIException
from app.services.storage.minio_provider import MinIOStorageProvider


def _provider(fake_client):
    p = MinIOStorageProvider(
        endpoint="s3.example.com", access_key="AK", secret_key="SK", bucket_name="prod-bucket", secure=True
    )
    p._client = fake_client
    return p


@pytest.mark.asyncio
async def test_upload_passes_bytes_length_and_content_type():
    c = MagicMock()
    key = await _provider(c).upload(b"abc", "visits/1/a.jpg", "image/jpeg")
    assert key == "visits/1/a.jpg"
    kw = c.put_object.call_args.kwargs
    assert kw["bucket_name"] == "prod-bucket" and kw["object_name"] == "visits/1/a.jpg"
    assert kw["length"] == 3 and kw["content_type"] == "image/jpeg"
    assert isinstance(kw["data"], io.BytesIO) and kw["data"].getvalue() == b"abc"


@pytest.mark.asyncio
async def test_upload_error_does_not_leak_internal_details():
    c = MagicMock()
    c.put_object.side_effect = RuntimeError("secret-endpoint.internal refused AK/SK")
    with pytest.raises(BaseAPIException) as ei:
        await _provider(c).upload(b"x", "k", "image/png")
    assert ei.value.status_code == 500 and "secret-endpoint" not in ei.value.detail


@pytest.mark.asyncio
async def test_presigned_url_uses_expiry_and_bucket():
    c = MagicMock()
    c.presigned_get_object.return_value = "https://s3.example.com/prod-bucket/k?X-Amz-Signature=abc"
    url = await _provider(c).generate_presigned_url("k", expiry_minutes=7)
    assert url.startswith("https://")
    args, kwargs = c.presigned_get_object.call_args
    assert args == ("prod-bucket", "k") and kwargs["expires"] == timedelta(minutes=7)


@pytest.mark.asyncio
async def test_download_reads_and_releases_connection():
    c = MagicMock()
    resp = MagicMock()
    resp.read.return_value = b"data"
    c.get_object.return_value = resp
    assert await _provider(c).download("k") == b"data"
    resp.close.assert_called_once()
    resp.release_conn.assert_called_once()


@pytest.mark.asyncio
async def test_download_missing_is_404_and_exists_false():
    c = MagicMock()
    c.get_object.side_effect = RuntimeError("NoSuchKey")
    c.stat_object.side_effect = RuntimeError("NoSuchKey")
    p = _provider(c)
    with pytest.raises(BaseAPIException) as ei:
        await p.download("k")
    assert ei.value.status_code == 404
    assert await p.exists("k") is False


@pytest.mark.asyncio
async def test_delete_true_then_false_on_error():
    c = MagicMock()
    p = _provider(c)
    assert await p.delete("k") is True
    c.remove_object.side_effect = RuntimeError("x")
    assert await p.delete("k") is False


def test_client_init_creates_missing_bucket_and_failure_is_503():
    fake_minio_cls = MagicMock()
    inst = fake_minio_cls.return_value
    inst.bucket_exists.return_value = False
    p = MinIOStorageProvider("e:9000", "AK", "SK", "b", True)
    with patch.dict("sys.modules", {"minio": MagicMock(Minio=fake_minio_cls)}):
        p._get_client()
    inst.make_bucket.assert_called_once_with("b")

    bad = MagicMock(side_effect=RuntimeError("connection refused 10.0.0.5"))
    p2 = MinIOStorageProvider("e:9000", "AK", "SK", "b", True)
    with patch.dict("sys.modules", {"minio": MagicMock(Minio=bad)}):
        with pytest.raises(BaseAPIException) as ei:
            p2._get_client()
    assert ei.value.status_code == 503 and "10.0.0.5" not in ei.value.detail


class _S3Error(Exception):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


def test_client_init_tolerates_access_denied_on_bucket_check_and_passes_region():
    fake_minio_cls = MagicMock()
    inst = fake_minio_cls.return_value
    inst.bucket_exists.side_effect = _S3Error("AccessDenied")
    p = MinIOStorageProvider("acct.r2.cloudflarestorage.com", "AK", "SK", "b", True, region="auto")
    with patch.dict("sys.modules", {"minio": MagicMock(Minio=fake_minio_cls)}):
        assert p._get_client() is inst
    inst.make_bucket.assert_not_called()
    assert fake_minio_cls.call_args.kwargs["region"] == "auto"


def test_client_init_tolerates_access_denied_on_make_bucket_but_not_other_errors():
    fake_minio_cls = MagicMock()
    inst = fake_minio_cls.return_value
    inst.bucket_exists.return_value = False
    inst.make_bucket.side_effect = _S3Error("AccessDenied")
    with patch.dict("sys.modules", {"minio": MagicMock(Minio=fake_minio_cls)}):
        assert MinIOStorageProvider("e:9000", "AK", "SK", "b", True)._get_client() is inst

    inst2 = MagicMock()
    inst2.bucket_exists.side_effect = _S3Error("SignatureDoesNotMatch")
    with patch.dict("sys.modules", {"minio": MagicMock(Minio=MagicMock(return_value=inst2))}):
        with pytest.raises(BaseAPIException) as ei:
            MinIOStorageProvider("e:9000", "AK", "SK", "b", True)._get_client()
    assert ei.value.status_code == 503
