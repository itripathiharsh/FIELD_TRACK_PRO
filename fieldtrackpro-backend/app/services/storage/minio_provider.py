"""
MinIO Object Storage Provider.
Integrates with S3-compatible MinIO object store buckets.
"""
from __future__ import annotations

import io
from datetime import timedelta

from app.exceptions.custom import BaseAPIException
from app.services.storage.base import BaseStorageProvider


class MinIOStorageProvider(BaseStorageProvider):
    """MinIO implementation of BaseStorageProvider."""

    def __init__(
        self,
        endpoint: str = "localhost:9000",
        access_key: str = "minioadmin",
        secret_key: str = "minioadmin",
        bucket_name: str = "fieldtrackpro-media",
        secure: bool = False,
    ) -> None:
        self.endpoint = endpoint
        self.access_key = access_key
        self.secret_key = secret_key
        self.bucket_name = bucket_name
        self.secure = secure
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
                )
                if not self._client.bucket_exists(self.bucket_name):
                    self._client.make_bucket(self.bucket_name)
            except Exception as err:
                raise BaseAPIException(
                    status_code=503,
                    detail=f"MinIO storage unavailable: {str(err)}",
                    error_code="STORAGE_UNAVAILABLE",
                )
        return self._client

    async def upload(self, file_bytes: bytes, storage_key: str, content_type: str) -> str:
        client = self._get_client()
        data_stream = io.BytesIO(file_bytes)
        try:
            client.put_object(
                bucket_name=self.bucket_name,
                object_name=storage_key,
                data=data_stream,
                length=len(file_bytes),
                content_type=content_type,
            )
            return storage_key
        except Exception as err:
            raise BaseAPIException(
                status_code=500,
                detail=f"MinIO upload error: {str(err)}",
                error_code="STORAGE_UPLOAD_ERROR",
            )

    async def download(self, storage_key: str) -> bytes:
        client = self._get_client()
        try:
            response = client.get_object(self.bucket_name, storage_key)
            return response.read()
        except Exception as err:
            raise BaseAPIException(
                status_code=404,
                detail=f"MinIO object download error: {str(err)}",
                error_code="FILE_NOT_FOUND_IN_STORAGE",
            )

    async def delete(self, storage_key: str) -> bool:
        client = self._get_client()
        try:
            client.remove_object(self.bucket_name, storage_key)
            return True
        except Exception:
            return False

    async def exists(self, storage_key: str) -> bool:
        client = self._get_client()
        try:
            client.stat_object(self.bucket_name, storage_key)
            return True
        except Exception:
            return False

    async def generate_presigned_url(self, storage_key: str, expiry_minutes: int = 15) -> str:
        """
        Generate a pre-signed URL for temporary access to a stored object.

        Security Design Section 4: access only via pre-signed URLs with short expiry.
        The URL expires after the specified number of minutes.
        """
        client = self._get_client()
        try:
            return client.presigned_get_object(
                self.bucket_name,
                storage_key,
                expires=timedelta(minutes=expiry_minutes),
            )
        except Exception as err:
            raise BaseAPIException(
                status_code=500,
                detail=f"Failed to generate access URL: {str(err)}",
                error_code="PRESIGNED_URL_ERROR",
            )
