"""
Storage Service: high-level abstraction that insulates business services
from underlying storage implementations (Local Disk vs MinIO Object Storage).
"""
from __future__ import annotations

from app.config import settings
from app.services.storage.base import BaseStorageProvider
from app.services.storage.local_provider import LocalStorageProvider
from app.services.storage.minio_provider import MinIOStorageProvider


class StorageService:
    """Unified storage service manager."""

    def __init__(self, provider: BaseStorageProvider | None = None) -> None:
        if provider is not None:
            self._provider = provider
        elif settings.storage_provider.upper() == "MINIO":
            self._provider = MinIOStorageProvider(
                endpoint=settings.minio_endpoint,
                access_key=settings.minio_access_key,
                secret_key=settings.minio_secret_key,
                bucket_name=settings.minio_bucket,
                secure=settings.minio_secure,
            )
        else:
            self._provider = LocalStorageProvider(base_dir=settings.media_storage_path)

    async def upload(self, file_bytes: bytes, storage_key: str, content_type: str) -> str:
        """Upload file bytes to target storage key."""
        return await self._provider.upload(file_bytes, storage_key, content_type)

    async def download(self, storage_key: str) -> bytes:
        """Retrieve raw file bytes from target storage key."""
        return await self._provider.download(storage_key)

    async def delete(self, storage_key: str) -> bool:
        """Delete object at storage key."""
        return await self._provider.delete(storage_key)

    async def exists(self, storage_key: str) -> bool:
        """Check if object exists at storage key."""
        return await self._provider.exists(storage_key)

    async def generate_presigned_url(self, storage_key: str, expiry_minutes: int = 15) -> str:
        """
        Generate a pre-signed URL for temporary access to a stored object.

        Security Design Section 4: access only via pre-signed URLs with short expiry.
        Returns a URL that expires after the specified number of minutes.
        """
        return await self._provider.generate_presigned_url(storage_key, expiry_minutes)


storage_service = StorageService()
