"""
Bounded upload reading + request body size cap.

`read_upload_limited` replaces every bare `await file.read()`: it refuses early when the
declared size is already over the cap and otherwise reads in chunks, raising
413 FILE_TOO_LARGE the moment the running total crosses the cap, so worst-case memory is
~max_bytes + one chunk no matter how large the request is.

`BodySizeLimitMiddleware` is the front line: it rejects a request whose Content-Length is
over the global cap (and aborts chunked bodies that stream past it) BEFORE the multipart /
JSON parser buffers it, covering every endpoint including base64 signature payloads.
"""
from __future__ import annotations

import json

from fastapi import UploadFile
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.config import settings
from app.exceptions.custom import BaseAPIException

_CHUNK = 1024 * 1024


def file_too_large(max_bytes: int) -> BaseAPIException:
    return BaseAPIException(
        status_code=413,
        detail=f"Upload exceeds maximum allowed size ({max_bytes} bytes)",
        error_code="FILE_TOO_LARGE",
    )


async def read_upload_limited(file: UploadFile, max_bytes: int, chunk_size: int = _CHUNK) -> bytes:
    """Read an UploadFile fully but never more than `max_bytes` (413 FILE_TOO_LARGE otherwise)."""
    declared = getattr(file, "size", None)
    if declared is not None and declared > max_bytes:
        raise file_too_large(max_bytes)
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(chunk_size)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise file_too_large(max_bytes)
        chunks.append(chunk)
    return b"".join(chunks)


class BodySizeLimitMiddleware:
    """Pure-ASGI cap on request body size (Content-Length check + streamed byte count)."""

    def __init__(self, app: ASGIApp, max_bytes: int | None = None) -> None:
        self.app = app
        self._max_bytes = max_bytes

    @property
    def max_bytes(self) -> int:
        return self._max_bytes if self._max_bytes is not None else settings.max_request_body_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        limit = self.max_bytes
        declared = None
        for name, value in scope.get("headers", []):
            if name == b"content-length":
                try:
                    declared = int(value)
                except ValueError:
                    declared = None
                break
        if declared is not None and declared > limit:
            await self._reject(send, limit)
            return

        received = 0
        responded = False

        async def limited_receive() -> Message:
            nonlocal received, responded
            if responded:
                return {"type": "http.disconnect"}
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    # Body streamed past the cap without a (truthful) Content-Length: answer 413
                    # ourselves and tell the app the client is gone so it stops reading.
                    responded = True
                    await self._reject(send, limit)
                    return {"type": "http.disconnect"}
            return message

        async def guarded_send(message: Message) -> None:
            if not responded:
                await send(message)

        await self.app(scope, limited_receive, guarded_send)

    @staticmethod
    async def _reject(send: Send, limit: int) -> None:
        body = json.dumps(
            {
                "error": {
                    "code": "REQUEST_TOO_LARGE",
                    "message": f"Request body exceeds maximum allowed size ({limit} bytes)",
                    "details": None,
                    "request_id": "-",
                }
            }
        ).encode()
        await send(
            {
                "type": "http.response.start",
                "status": 413,
                "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())],
            }
        )
        await send({"type": "http.response.body", "body": body})

