"""
Login rate limiting.

FT-041. Implements the locked design in `16_authentication.md` section 6 and
`09_security_design.md` section 1: at most 5 failed attempts per identifier per
15-minute sliding window, then a temporary lockout.

Design notes carried over verbatim from the specification:

* The window is *sliding*, not fixed - attempts older than the window are
  discarded on every check, so a legitimate user is never locked out by
  failures that have already aged out.
* Counting is keyed on the **identifier** (email / mobile), not the IP address.
  The stated goal is to stop credential brute force against a specific account
  without letting one bad actor on a shared NAT lock out an entire office.
* A **successful** login clears the counter for that identifier.
* State is in-process. The specification calls this out explicitly as an
  accepted MVP limitation: it resets on restart and does not span multiple
  workers. Moving it to Redis is a scaling concern, not a Phase 3 concern.

Security note (repair rule 7): the limiter fails **closed**. It only ever
*adds* a rejection; it can never cause a login to succeed. `check_allowed` is
invoked before credentials are examined, and raising is its only side effect on
the authentication path.
"""
from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone

from app.exceptions.custom import BaseAPIException

MAX_ATTEMPTS = 5
WINDOW = timedelta(minutes=15)


class RateLimitExceededException(BaseAPIException):
    """Raised when an identifier exceeds the failed-login budget."""

    def __init__(self, retry_after_seconds: int) -> None:
        minutes = max(1, round(retry_after_seconds / 60))
        super().__init__(
            detail=f"Too many failed sign-in attempts. Try again in {minutes} minute(s).",
            status_code=429,
            error_code="AUTH_RATE_LIMITED",
        )
        self.retry_after_seconds = retry_after_seconds


class LoginRateLimiter:
    """Sliding-window counter of failed login attempts, keyed by identifier."""

    def __init__(
        self, max_attempts: int = MAX_ATTEMPTS, window: timedelta = WINDOW
    ) -> None:
        self._attempts: dict[str, list[datetime]] = {}
        self._max_attempts = max_attempts
        self._window = window
        # Uvicorn runs the event loop in one thread, but FastAPI may execute
        # sync dependencies in a threadpool. A lock keeps the counter honest.
        self._lock = threading.Lock()

    @staticmethod
    def _normalise(identifier: str) -> str:
        """Case-insensitive key so 'User@x.com' and 'user@x.com' share a budget."""
        return identifier.strip().lower()

    def check_allowed(self, identifier: str) -> None:
        """Raise :class:`RateLimitExceededException` if the budget is exhausted."""
        key = self._normalise(identifier)
        now = datetime.now(tz=timezone.utc)
        with self._lock:
            recent = [t for t in self._attempts.get(key, []) if now - t < self._window]
            if recent:
                self._attempts[key] = recent
            else:
                self._attempts.pop(key, None)

            if len(recent) >= self._max_attempts:
                oldest = min(recent)
                retry_after = int((oldest + self._window - now).total_seconds())
                raise RateLimitExceededException(max(retry_after, 1))

    def record_failure(self, identifier: str) -> None:
        key = self._normalise(identifier)
        now = datetime.now(tz=timezone.utc)
        with self._lock:
            self._attempts.setdefault(key, []).append(now)

    def record_success(self, identifier: str) -> None:
        """Clear the counter - a correct password proves this is the real user."""
        with self._lock:
            self._attempts.pop(self._normalise(identifier), None)

    def reset(self) -> None:
        """Clear all counters. Used by tests to guarantee isolation."""
        with self._lock:
            self._attempts.clear()

    def failures_for(self, identifier: str) -> int:
        """Current failure count inside the window (diagnostics and tests)."""
        key = self._normalise(identifier)
        now = datetime.now(tz=timezone.utc)
        with self._lock:
            return len([t for t in self._attempts.get(key, []) if now - t < self._window])


# Single process-wide instance, matching the locked design.
login_rate_limiter = LoginRateLimiter()
