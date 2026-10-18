"""
Core security utilities: JWT token lifecycle and password hashing.
"""
from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt
import bcrypt

from app.config import settings
from app.exceptions.custom import BaseAPIException

# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------


#: bcrypt only uses the first 72 BYTES of a password and bcrypt 5 raises on longer
#: input. Pre-hashing would not be compatible with the hashes already stored, so
#: over-long passwords are rejected (422 PASSWORD_TOO_LONG) at every entry point
#: (all of which funnel through hash_password) and never verify.
MAX_PASSWORD_BYTES = 72


class PasswordTooLongException(BaseAPIException):
    def __init__(self) -> None:
        super().__init__(
            detail=f"Password is too long (maximum {MAX_PASSWORD_BYTES} bytes; some characters use several bytes).",
            status_code=422,
            error_code="PASSWORD_TOO_LONG",
        )


def password_too_long(plain: str) -> bool:
    return len(plain.encode("utf-8")) > MAX_PASSWORD_BYTES


def hash_password(plain: str) -> str:
    """Return bcrypt hash of *plain* password. Raises PasswordTooLongException above 72 bytes."""
    if password_too_long(plain):
        raise PasswordTooLongException()
    pw_bytes = plain.encode("utf-8")
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(pw_bytes, salt).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """Return True if *plain* matches the stored *hashed* password (False, never an error, if >72 bytes)."""
    if password_too_long(plain):
        return False
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


_DUMMY_HASH: str | None = None


def dummy_verify_password(plain: str) -> None:
    """
    Burn one bcrypt verification against a fixed hash. Called when the login
    identifier does not exist so the response time does not reveal whether the
    account exists. The hash is computed lazily once per process.
    """
    global _DUMMY_HASH
    if _DUMMY_HASH is None:
        _DUMMY_HASH = bcrypt.hashpw(b"fieldtrack-timing-equaliser", bcrypt.gensalt()).decode("utf-8")
    verify_password(plain, _DUMMY_HASH)


# ---------------------------------------------------------------------------
# JWT access tokens
# ---------------------------------------------------------------------------

ALGORITHM = "HS256"


def create_access_token(
    subject: str,
    role: str,
    expires_delta: timedelta | None = None,
    token_version: int = 0,
) -> str:
    """
    Create a signed JWT access token.

    `role` is informational only: authorization always uses the role currently stored in the
    database. `tv` (token version) lets the server kill every outstanding access token of an
    account at once (admin password reset, role change) by bumping `users.token_version`.
    """
    if expires_delta is None:
        expires_delta = timedelta(minutes=settings.jwt_access_token_expiry_minutes)

    now = datetime.now(tz=timezone.utc)
    expire = now + expires_delta
    payload = {
        "sub": subject,
        "role": role,
        "iat": now,
        "exp": expire,
        "jti": str(uuid.uuid4()),
        "tv": int(token_version or 0),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=ALGORITHM)


TEMP_PASSWORD_ALPHABET_UPPER = "ABCDEFGHJKLMNPQRSTUVWXYZ"
TEMP_PASSWORD_ALPHABET_LOWER = "abcdefghijkmnpqrstuvwxyz"
TEMP_PASSWORD_ALPHABET_DIGITS = "23456789"


def generate_temporary_password() -> str:
    """
    Cryptographically random temporary password (CSPRNG), e.g. ``Kq7m-Rv4t-Xw9z``.

    14 characters (12 random + 2 separators) drawn from an alphabet without look-alike characters
    (no 0/O, 1/l/I), always containing an upper-case letter, a lower-case letter and a digit.
    ~58 bits of entropy; it is single-use and short-lived (see TEMP_PASSWORD_EXPIRY_MINUTES).
    """
    alphabet = TEMP_PASSWORD_ALPHABET_UPPER + TEMP_PASSWORD_ALPHABET_LOWER + TEMP_PASSWORD_ALPHABET_DIGITS
    while True:
        chars = [secrets.choice(alphabet) for _ in range(12)]
        if (
            any(c in TEMP_PASSWORD_ALPHABET_UPPER for c in chars)
            and any(c in TEMP_PASSWORD_ALPHABET_LOWER for c in chars)
            and any(c in TEMP_PASSWORD_ALPHABET_DIGITS for c in chars)
        ):
            return "-".join("".join(chars[i : i + 4]) for i in range(0, 12, 4))


def decode_access_token(token: str) -> dict:
    """Decode and validate an access token. Raises JWTError on failure."""
    return jwt.decode(token, settings.jwt_secret, algorithms=[ALGORITHM])


# ---------------------------------------------------------------------------
# Refresh tokens  (opaque, stored as SHA-256 hash in DB)
# ---------------------------------------------------------------------------

def generate_refresh_token() -> tuple[str, str]:
    """
    Generate a cryptographically secure refresh token.

    Returns
    -------
    (raw_token, token_hash)
        *raw_token*  is sent to the client.
        *token_hash* is persisted in the database.
    """
    raw = secrets.token_urlsafe(64)
    token_hash = hashlib.sha256(raw.encode()).hexdigest()
    return raw, token_hash


def hash_refresh_token(raw: str) -> str:
    """Hash a raw refresh token for DB lookup."""
    return hashlib.sha256(raw.encode()).hexdigest()
