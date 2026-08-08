"""
Application middleware.

FT-046: an unhandled exception produced a 500 with **no** ``Access-Control-Allow-Origin``
header, so browsers reported the failure as a CORS error. The real server error
was invisible in the browser console, and during the audit this masked the
FT-005 crash entirely - the UI looked like a CORS misconfiguration when the
backend was actually raising ``AttributeError``.

Why it happened
---------------
Starlette assembles the stack as::

    ServerErrorMiddleware   <- handles Exception, always OUTERMOST
      user middleware       <- CORSMiddleware lives here
        ExceptionMiddleware <- handles HTTPException and registered handlers
          router

An exception escaping the router unwinds past ``CORSMiddleware`` and is turned
into a response by ``ServerErrorMiddleware``, which knows nothing about CORS.
Registering an ``Exception`` handler on the app does not help: FastAPI installs
that handler *into* ``ServerErrorMiddleware``, i.e. still outside CORS.

The fix
-------
Catch the exception *inside* the CORS layer. ``CatchUnhandledExceptionsMiddleware``
is registered **before** ``CORSMiddleware`` so that CORS ends up outermost and
therefore decorates the error response it produces.

The exception is still logged with a full traceback - this middleware changes
where the response is produced, never whether the failure is recorded.
"""
from __future__ import annotations

import logging

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

logger = logging.getLogger("fieldtrackpro")


class CatchUnhandledExceptionsMiddleware(BaseHTTPMiddleware):
    """Convert an escaped exception into a 500 *inside* the CORS layer."""

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next):
        try:
            return await call_next(request)
        except Exception as exc:  # noqa: BLE001 - deliberate boundary handler
            # Log the real cause with a traceback. Nothing is swallowed: the
            # operator sees exactly what failed, while the client receives a
            # generic message that leaks no internals.
            logger.error(
                "Unhandled exception on %s %s: %s",
                request.method,
                request.url.path,
                exc,
                exc_info=True,
            )
            return JSONResponse(
                status_code=500,
                content={
                    "error": {
                        "code": "INTERNAL_SERVER_ERROR",
                        "message": "An internal server error occurred.",
                        "details": {},
                    }
                },
            )
