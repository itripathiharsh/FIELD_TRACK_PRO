"""
Safe client-IP resolution for per-IP rate limiting.

Why this exists
---------------
`X-Forwarded-For` is a list that every proxy APPENDS to; everything the client
itself sent sits at the LEFT and is attacker-controlled. uvicorn's
`--proxy-headers --forwarded-allow-ips='*'` trusts the leftmost entry, so an
attacker could rotate fake addresses and get a fresh per-IP budget on every
request. The only trustworthy entries are the ones appended by OUR proxies,
counted from the RIGHT.

Rule: with TRUSTED_PROXY_HOPS = N, the client address is the Nth entry from the
right of X-Forwarded-For (Render's edge appends the real peer address, so N = 1
in production). If the header is absent, shorter than N, or N = 0, fall back to
the socket peer (`request.client.host`). When uvicorn is started WITHOUT
--proxy-headers (render.yaml), `request.client.host` is the proxy's address and
this helper is the single place that reads the header.
"""
from __future__ import annotations

import ipaddress

from starlette.requests import Request

from app.config import settings


def _valid_ip(value: str) -> str | None:
    value = value.strip()
    if not value:
        return None
    try:
        return str(ipaddress.ip_address(value))
    except ValueError:
        return None


def resolve_client_ip(
    forwarded_for: str | None, peer: str | None, trusted_hops: int | None = None
) -> str | None:
    hops = settings.trusted_proxy_hops if trusted_hops is None else trusted_hops
    if hops > 0 and forwarded_for:
        entries = [e.strip() for e in forwarded_for.split(",") if e.strip()]
        if len(entries) >= hops:
            candidate = _valid_ip(entries[-hops])
            if candidate:
                return candidate
    return peer


def get_client_ip(request: Request | None) -> str | None:
    """Client IP for rate limiting (never the client-controlled leftmost XFF entry)."""
    if request is None:
        return None
    peer = request.client.host if request.client else None
    return resolve_client_ip(request.headers.get("x-forwarded-for"), peer)
