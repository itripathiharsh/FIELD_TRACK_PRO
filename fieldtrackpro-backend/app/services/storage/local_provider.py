"""
Local Disk Storage Provider.
Persists binary assets securely on the local filesystem.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import time
from pathlib import Path
from urllib.parse import quote

from app.config import settings
from app.exceptions.custom import BaseAPIException
from app.services.storage.base import BaseStorageProvider

LOCAL_MEDIA_URL_PATH = "/api/v1/media/local-file"


def _sign(storage_key: str, expires_at: int) -> str:
    """
    P1-2: signed with a dedicated media_signing_secret, not jwt_secret -
    rotating the JWT signing secret (a session/auth concern) must never
    invalidate every outstanding media download link, and vice versa.
    """
    message = f"{storage_key}:{expires_at}".encode()
    return hmac.new(settings.media_signing_secret.encode(), message, hashlib.sha256).hexdigest()


def verify_local_media_signature(storage_key: str, expires_at: int, signature: str) -> bool:
    """Constant-time check that `signature` matches storage_key+expires_at, and that it hasn't expired."""
    if time.time() > expires_at:
        return False
    expected = _sign(storage_key, expires_at)
    return hmac.compare_digest(expected, signature)


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

    async def generate_presigned_url(self, storage_key: str, expiry_minutes: int = 15) -> str:
        """
        Local storage has no object-store presigned-URL support, so this signs
        a short-lived HMAC token instead and points at the local file-serving
        endpoint that verifies it. A raw `file://<server-disk-path>` was
        previously returned here, which no remote client (browser or Android
        device) can ever fetch, and which carried no signature or expiry
        despite the "pre-signed URL" contract documented on this interface.
        """
        target_path = self._resolve_path(storage_key)
        if not target_path.exists():
            raise BaseAPIException(
                status_code=404,
                detail="Media file not found in storage",
                error_code="FILE_NOT_FOUND_IN_STORAGE",
            )
        expires_at = int(time.time()) + expiry_minutes * 60
        signature = _sign(storage_key, expires_at)
        return (
            f"{LOCAL_MEDIA_URL_PATH}?key={quote(storage_key)}"
            f"&expires={expires_at}&sig={signature}"
        )
