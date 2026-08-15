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

P1-3: state is now backed by the shared Postgres database (the `login_attempts`
table) rather than in-process memory. The original design explicitly accepted
in-process state as an "MVP limitation" that "resets on restart and does not
span multiple workers" - the real-world consequence is that an attacker is
trivially routed to a different worker to reset their own budget. Postgres is
infrastructure every worker already depends on, so this closes the gap without
introducing a new dependency (e.g. Redis) the project doesn't otherwise use.
The policy itself (5 attempts / 15 minutes / cleared on success) is unchanged -
only the storage/coordination mechanism moved.

Security note (repair rule 7): the limiter fails **closed**. It only ever
*adds* a rejection; it can never cause a login to succeed. `check_allowed` is
invoked before credentials are examined, and raising is its only side effect on
the authentication path.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions.custom import BaseAPIException
from app.models.login_attempt import LoginAttempt

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
    """Sliding-window counter of failed login attempts, keyed by identifier - shared across all workers via the database."""

    def __init__(
        self, max_attempts: int = MAX_ATTEMPTS, window: timedelta = WINDOW
    ) -> None:
        self._max_attempts = max_attempts
        self._window = window

    @staticmethod
    def _normalise(identifier: str) -> str:
        """Case-insensitive key so 'User@x.com' and 'user@x.com' share a budget."""
        return identifier.strip().lower()

    async def check_allowed(self, identifier: str, session: AsyncSession) -> None:
        """Raise :class:`RateLimitExceededException` if the budget is exhausted."""
        key = self._normalise(identifier)
        now = datetime.now(tz=timezone.utc)
        cutoff = now - self._window
        result = await session.execute(
            select(LoginAttempt.attempted_at)
            .where(LoginAttempt.identifier == key, LoginAttempt.attempted_at > cutoff)
            .order_by(LoginAttempt.attempted_at.asc())
        )
        recent = [row[0] for row in result.all()]
        if len(recent) >= self._max_attempts:
            oldest = recent[0]
            retry_after = int((oldest + self._window - now).total_seconds())
            raise RateLimitExceededException(max(retry_after, 1))

    async def record_failure(self, identifier: str, session: AsyncSession) -> None:
        key = self._normalise(identifier)
        session.add(LoginAttempt(identifier=key))
        await session.commit()

    async def record_success(self, identifier: str, session: AsyncSession) -> None:
        """Clear the counter - a correct password proves this is the real user."""
        key = self._normalise(identifier)
        await session.execute(delete(LoginAttempt).where(LoginAttempt.identifier == key))
        await session.commit()

    async def reset(self, session: AsyncSession) -> None:
        """Clear all counters. Used by tests to guarantee isolation."""
        await session.execute(delete(LoginAttempt))
        await session.commit()

    async def failures_for(self, identifier: str, session: AsyncSession) -> int:
        """Current failure count inside the window (diagnostics and tests)."""
        key = self._normalise(identifier)
        now = datetime.now(tz=timezone.utc)
        cutoff = now - self._window
        count = await session.scalar(
            select(func.count())
            .select_from(LoginAttempt)
            .where(LoginAttempt.identifier == key, LoginAttempt.attempted_at > cutoff)
        )
        return count or 0


# Single shared instance. Holds no per-process state itself now - every method
# reads/writes through the database session passed in, so this is safe to
# share across any number of worker processes.
login_rate_limiter = LoginRateLimiter()
