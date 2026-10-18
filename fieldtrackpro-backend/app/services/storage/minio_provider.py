"""
MinIO Object Storage Provider.
Integrates with S3-compatible MinIO object store buckets.
"""
from __future__ import annotations

import asyncio
import io
import logging
from datetime import timedelta

from app.exceptions.custom import BaseAPIException
from app.services.storage.base import BaseStorageProvider

logger = logging.getLogger("fieldtrackpro")


class MinIOStorageProvider(BaseStorageProvider):
    """MinIO implementation of BaseStorageProvider."""

    def __init__(
        self,
        endpoint: str = "localhost:9000",
        access_key: str = "minioadmin",
        secret_key: str = "minioadmin",
        bucket_name: str = "fieldtrackpro-media",
        secure: bool = False,
        region: str | None = None,
    ) -> None:
        self.endpoint = endpoint
        self.access_key = access_key
        self.secret_key = secret_key
        self.bucket_name = bucket_name
        self.secure = secure
        # Explicit region (e.g. "auto" for Cloudflare R2, "ap-south-1" for AWS S3) lets minio-py
        # sign requests/presigned URLs offline instead of calling GetBucketLocation first.
        self.region = region or None
        self._client = None

    def _get_client(self):
        """Lazy-load minio client connection."""
        if self._client is None:
            try:
                from minio import Minio
                self._client = Minio(
                    self.endpoint,
                    access_key=self.access_key,
                    secret_key=self.secret_key,
                    secure=self.secure,
                    region=self.region,
                )
                self._ensure_bucket()
            except Exception as err:
                logger.error("MinIO client initialisation failed: %s", type(err).__name__)
                raise BaseAPIException(
                    status_code=503,
                    detail="Object storage is unavailable",
                    error_code="STORAGE_UNAVAILABLE",
                )
        return self._client

    @staticmethod
    def _is_access_denied(err: Exception) -> bool:
        return getattr(err, "code", None) in ("AccessDenied", "AllAccessDisabled")

    def _ensure_bucket(self) -> None:
        """
        Create the bucket if it is missing. Least-privilege production credentials (Get/Put/
        Delete on one bucket) usually lack ListBucket/CreateBucket: an AccessDenied from the
        existence check (or from make_bucket) is treated as "the bucket was provisioned for us".
        A genuinely missing bucket then surfaces as an upload/download error instead.
        """
        try:
            exists = self._client.bucket_exists(self.bucket_name)
        except Exception as err:
            if self._is_access_denied(err):
                logger.info("MinIO bucket existence check denied; assuming bucket is provisioned")
                return
            raise
        if not exists:
            try:
                self._client.make_bucket(self.bucket_name)
            except Exception as err:
                if self._is_access_denied(err):
                    logger.warning("MinIO bucket creation denied; assuming bucket is provisioned")
                    return
                raise

    async def upload(self, file_bytes: bytes, storage_key: str, content_type: str) -> str:
        client = await asyncio.to_thread(self._get_client)
        data_stream = io.BytesIO(file_bytes)
        try:
            # minio is a blocking client: keep it off the event loop.
            await asyncio.to_thread(
                client.put_object,
                bucket_name=self.bucket_name,
                object_name=storage_key,
                data=data_stream,
                length=len(file_bytes),
                content_type=content_type,
            )
            return storage_key
        except Exception as err:
            logger.error("MinIO upload failed: %s", type(err).__name__)
            raise BaseAPIException(
                status_code=500,
                detail="Object storage upload failed",
                error_code="STORAGE_UPLOAD_ERROR",
            )

    async def download(self, storage_key: str) -> bytes:
        client = await asyncio.to_thread(self._get_client)

        def _read() -> bytes:
            response = client.get_object(self.bucket_name, storage_key)
            try:
                return response.read()
            finally:
                response.close()
                response.release_conn()

        try:
            return await asyncio.to_thread(_read)
        except Exception as err:
            logger.warning("MinIO download failed: %s", type(err).__name__)
            raise BaseAPIException(
                status_code=404,
                detail="Stored file not found",
                error_code="FILE_NOT_FOUND_IN_STORAGE",
            )

    async def delete(self, storage_key: str) -> bool:
        client = await asyncio.to_thread(self._get_client)
        try:
            await asyncio.to_thread(client.remove_object, self.bucket_name, storage_key)
            return True
        except Exception:
            return False

    async def exists(self, storage_key: str) -> bool:
        client = await asyncio.to_thread(self._get_client)
        try:
            await asyncio.to_thread(client.stat_object, self.bucket_name, storage_key)
            return True
        except Exception:
            return False

    async def generate_presigned_url(self, storage_key: str, expiry_minutes: int = 15) -> str:
        """
        Generate a pre-signed URL for temporary access to a stored object.

        Security Design Section 4: access only via pre-signed URLs with short expiry.
        The URL expires after the specified number of minutes.
        """
        client = await asyncio.to_thread(self._get_client)
        try:
            return await asyncio.to_thread(
                client.presigned_get_object,
                self.bucket_name,
                storage_key,
                expires=timedelta(minutes=expiry_minutes),
            )
        except Exception as err:
            logger.error("MinIO presign failed: %s", type(err).__name__)
            raise BaseAPIException(
                status_code=500,
                detail="Failed to generate access URL",
                error_code="PRESIGNED_URL_ERROR",
            )
