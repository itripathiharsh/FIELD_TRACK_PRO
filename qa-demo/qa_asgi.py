"""
QA/DEMO entry point: ONE public address serves both the web app and the (unmodified) FieldTrack backend.

    /api/*  and  /health   -> the real backend application (app.main:app), exactly as in production
    everything else        -> the QA web build in ./web_dist (single-page app with history fallback)

Why a wrapper: the backend sends `Content-Security-Policy: default-src 'none'` on every response (correct for an API,
fatal for a web page), and serving both from one origin avoids CORS and third-party-cookie problems for the accountant.
The backend code itself is not modified.
"""
from __future__ import annotations

from pathlib import Path

from starlette.responses import FileResponse, Response
from starlette.staticfiles import StaticFiles

from app.main import app as backend

WEB_DIST = Path(__file__).resolve().parent / "web_dist"

# Same policy the production site ships (vercel.json), so QA behaves like production in the browser.
_SPA_CSP = (
    "default-src 'self'; script-src 'self'; worker-src 'self' blob:; child-src 'self' blob:; "
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' data: https://fonts.gstatic.com; "
    "img-src 'self' data: blob: https:; connect-src 'self' blob: https:; object-src 'none'; base-uri 'self'; "
    "form-action 'self'; frame-ancestors 'none'"
)
_HEADERS = {
    "Content-Security-Policy": _SPA_CSP,
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Strict-Transport-Security": "max-age=63072000; includeSubDomains",
}


class _Spa(StaticFiles):
    """Static files with single-page-app fallback to index.html, plus security headers."""

    async def get_response(self, path: str, scope) -> Response:
        try:
            resp = await super().get_response(path, scope)
            if resp.status_code == 404:
                raise FileNotFoundError
        except Exception:  # noqa: BLE001 - unknown client-side route: serve the app shell
            resp = FileResponse(WEB_DIST / "index.html")
            resp.headers["Cache-Control"] = "no-cache"
        for k, v in _HEADERS.items():
            resp.headers[k] = v
        if path.startswith("assets/"):
            resp.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return resp


_spa = _Spa(directory=str(WEB_DIST), html=True)


async def application(scope, receive, send):
    if scope["type"] == "http":
        path = scope.get("path", "")
        if path.startswith("/api/") or path == "/health":
            await backend(scope, receive, send)
        else:
            await _spa(scope, receive, send)
    else:  # lifespan (startup/shutdown) and anything else belong to the backend
        await backend(scope, receive, send)
