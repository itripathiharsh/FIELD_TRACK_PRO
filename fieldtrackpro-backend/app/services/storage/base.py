"""
Abstract Base Storage Provider Interface.
Allows seamless switching between local disk storage and cloud/MinIO object stores.
"""
from __future__ import annotations

from abc import ABC, abstractmethod


class BaseStorageProvider(ABC):
    """Abstract contract for blob storage operations."""

    @abstractmethod
    async def upload(self, file_bytes: bytes, storage_key: str, content_type: str) -> str:
        """Upload file bytes to target storage key. Returns storage key location."""
        pass

    @abstractmethod
    async def download(self, storage_key: str) -> bytes:
        """Retrieve raw file bytes from target storage key."""
        pass

    @abstractmethod
    async def delete(self, storage_key: str) -> bool:
        """Remove object at storage key."""
        pass

    @abstractmethod
    async def exists(self, storage_key: str) -> bool:
        """Check if object exists at storage key."""
        pass

    @abstractmethod
    async def generate_presigned_url(self, storage_key: str, expiry_minutes: int = 15) -> str:
        """Generate a pre-signed URL for temporary access to the object."""
        pass
