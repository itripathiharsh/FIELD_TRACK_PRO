import logging
import re
import sys

from app.core.context import get_current_request_id

REDACTED = "[REDACTED]"

# --- Scrubbing -------------------------------------------------------------
# Production logs must never contain: customer coordinates, tokens/token
# fragments, OTPs, presigned URLs / signatures, or full query strings.

_BEARER = re.compile(r"(?i)\b(bearer|basic)\s+[A-Za-z0-9._~+/=\-]+")
_JWT = re.compile(r"\beyJ[A-Za-z0-9_\-]{5,}\.[A-Za-z0-9_\-]{5,}\.[A-Za-z0-9_\-]*")
# any URL query string (presigned URLs carry the signature there)
_URL_QUERY = re.compile(r"(https?://[^\s?#'\"<>]+|(?<=[\s'\"(])/[^\s?#'\"<>]*)\?[^\s'\"<>]+")
# key=value / "key": value for secret-bearing keys
_SECRET_KV = re.compile(
    r"(?i)(?P<key>[\w\-]*(?:token|otp|password|passwd|secret|signature|api[_\-]?key|authorization|credential|x-amz-[\w\-]+)[\w\-]*)"
    r"(?P<sep>[\"']?\s*[=:]\s*[\"']?)(?P<val>[^\s\"'&,;)}\]]+)"
)
# customer coordinates
_COORD_KV = re.compile(
    r"(?i)(?P<key>(?<![A-Za-z0-9])(?:[a-z]+_)*(?:lat|lng|lon|latitude|longitude)(?![A-Za-z0-9]))"
    r"(?P<sep>[\"']?\s*[=:]\s*[\"']?)(?P<val>-?\d+(?:\.\d+)?)"
)
# "(12.9716, 77.5946)" style coordinate pairs
_COORD_PAIR = re.compile(r"\(\s*-?\d{1,3}\.\d{3,}\s*,\s*-?\d{1,3}\.\d{3,}\s*\)")


def scrub_sensitive(text: str) -> str:
    """Return *text* with secrets, OTPs, signatures, query strings and coordinates removed."""
    if not text:
        return text
    text = _URL_QUERY.sub(lambda m: f"{m.group(1)}?{REDACTED}", text)
    text = _BEARER.sub(lambda m: f"{m.group(1)} {REDACTED}", text)
    text = _JWT.sub(REDACTED, text)
    text = _SECRET_KV.sub(lambda m: f"{m.group('key')}{m.group('sep')}{REDACTED}", text)
    text = _COORD_KV.sub(lambda m: f"{m.group('key')}{m.group('sep')}{REDACTED}", text)
    text = _COORD_PAIR.sub("(" + REDACTED + ")", text)
    return text


def strip_query(path: str) -> str:
    """Drop the query string (and fragment) from a request target."""
    return path.split("?", 1)[0].split("#", 1)[0]


class ScrubbingFormatter(logging.Formatter):
    """Formats a record then scrubs the whole result (message + traceback)."""

    def format(self, record: logging.LogRecord) -> str:
        return scrub_sensitive(super().format(record))


class RequestIdLogFilter(logging.Filter):
    """Injects the active correlation request_id into every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        req_id = get_current_request_id()
        record.request_id = req_id if req_id else "-"
        return True


class AccessLogQueryStripFilter(logging.Filter):
    """uvicorn.access logs the raw request target including the query string."""

    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args
        if isinstance(args, tuple) and len(args) >= 3 and isinstance(args[2], str):
            record.args = args[:2] + (strip_query(args[2]),) + args[3:]
        return True


def setup_logging(environment: str = "dev") -> logging.Logger:
    log_level = logging.DEBUG if environment == "dev" else logging.INFO

    formatter = ScrubbingFormatter(
        "[%(asctime)s] [%(levelname)s] [%(name)s] [req:%(request_id)s] - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    handler.addFilter(RequestIdLogFilter())
    handler._ft_scrub = True  # type: ignore[attr-defined]

    logger = logging.getLogger("fieldtrackpro")
    logger.setLevel(log_level)

    # Single scrubbing handler on the ROOT logger: both "fieldtrackpro" and
    # modules using logging.getLogger(__name__) propagate to it, so every
    # application record is scrubbed exactly once (and caplog keeps working).
    root = logging.getLogger()
    for h in list(root.handlers):
        if getattr(h, "_ft_scrub", False):
            root.removeHandler(h)
    root.addHandler(handler)
    root.setLevel(log_level)
    # httpx logs full request URLs (incl. query strings) at INFO.
    for noisy in ("httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    access = logging.getLogger("uvicorn.access")
    if not any(isinstance(f, AccessLogQueryStripFilter) for f in access.filters):
        access.addFilter(AccessLogQueryStripFilter())

    return logger
