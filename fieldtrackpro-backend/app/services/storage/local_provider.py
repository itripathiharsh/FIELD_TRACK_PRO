"""
Local Disk Storage Provider.
Persists binary assets securely on the local filesystem.
"""
from __future__ import annotations

import os
from pathlib import Path

from app.exceptions.custom import BaseAPIException
from app.services.storage.base import BaseStorageProvider


class LocalStorageProvider(BaseStorageProvider):
    """Local disk implementation of BaseStorageProvider."""

    def __init__(self, base_dir: str = "media_storage") -> None:
        self.base_dir = Path(base_dir).resolve()
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _resolve_path(self, storage_key: str) -> Path:
        """Resolve and prevent path traversal attacks."""
        clean_key = storage_key.lstrip("/\\")
        target_path = (self.base_dir / clean_key).resolve()
        if not str(target_path).startswith(str(self.base_dir)):
            raise BaseAPIException(
                status_code=400,
                detail="Path traversal attempt detected",
                error_code="PATH_TRAVERSAL_DETECTED",
            )
        return target_path

    async def upload(self, file_bytes: bytes, storage_key: str, content_type: str) -> str:
        target_path = self._resolve_path(storage_key)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_bytes(file_bytes)
        return storage_key

    async def download(self, storage_key: str) -> bytes:
        target_path = self._resolve_path(storage_key)
        if not target_path.exists():
            raise BaseAPIException(
                status_code=404,
                detail="Media file not found in storage",
                error_code="FILE_NOT_FOUND_IN_STORAGE",
            )
        return target_path.read_bytes()

    async def delete(self, storage_key: str) -> bool:
        target_path = self._resolve_path(storage_key)
        if target_path.exists():
            target_path.unlink()
            return True
        return False

    async def exists(self, storage_key: str) -> bool:
        target_path = self._resolve_path(storage_key)
        return target_path.exists()
