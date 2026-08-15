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

from app.config import settings

logger = logging.getLogger("fieldtrackpro")

# Swagger UI / ReDoc (dev/test only - unavailable in production, see main.py)
# load their JS/CSS from a CDN, so a strict CSP on those two responses would
# break the interactive docs. Every other response never serves HTML/CSS/JS
# at all (this is a JSON API), so a default-deny CSP there is safe and pure
# defense-in-depth, not something the app actually relies on to be secure.
_DOC_PATHS = {"/docs", "/redoc", "/openapi.json"}


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


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    P1-4: baseline security response headers.

    Applied to every response (added on the way out, after call_next - never
    changes what a handler returns, only decorates it):

    * X-Content-Type-Options: nosniff - stops a browser from ignoring the
      declared Content-Type and sniffing a JSON/file response as HTML/JS.
    * X-Frame-Options: DENY - this API is never meant to be framed.
    * Referrer-Policy: strict-origin-when-cross-origin - a conservative,
      widely-compatible default that doesn't affect this app's own behaviour.
    * Content-Security-Policy - default-deny, skipped on /docs, /redoc and
      /openapi.json (see _DOC_PATHS) so the interactive API docs keep working
      wherever they're still enabled (dev/test only - see main.py).
    * Strict-Transport-Security - only added when ENVIRONMENT=production,
      where the deployment is assumed to be served over HTTPS. Never added
      otherwise: HSTS on a plain-HTTP deployment would make browsers refuse
      to connect over HTTP again, which would break local/dev access rather
      than protect anything.
    """

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        if request.url.path not in _DOC_PATHS:
            response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
        if settings.environment == "production":
            response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
        return response
