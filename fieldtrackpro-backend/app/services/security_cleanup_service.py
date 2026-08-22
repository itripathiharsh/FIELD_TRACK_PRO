from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.login_attempt import LoginAttempt
from app.models.password_reset import PasswordResetToken
from app.models.refresh_token import RefreshToken

logger = logging.getLogger("fieldtrackpro")


class SecurityCleanupService:
    """Service to purge expired and stale authentication/security records."""

    async def cleanup_expired_records(self, session: AsyncSession) -> dict[str, int]:
        """
        Purge expired refresh tokens, expired/used password reset tokens,
        and old login attempt records.
        """
        now = datetime.now(timezone.utc)
        seven_days_ago = now - timedelta(days=7)
        thirty_days_ago = now - timedelta(days=30)

        counts = {
            "refresh_tokens": 0,
            "password_reset_tokens": 0,
            "login_attempts": 0,
        }

        try:
            # 1. Purge expired or long-revoked refresh tokens
            refresh_stmt = delete(RefreshToken).where(
                or_(
                    RefreshToken.expires_at < now,
                    (RefreshToken.revoked.is_(True) & (RefreshToken.created_at < seven_days_ago)),
                )
            )
            refresh_res = await session.execute(refresh_stmt)
            counts["refresh_tokens"] = refresh_res.rowcount or 0

            # 2. Purge expired or already-used password reset tokens
            reset_stmt = delete(PasswordResetToken).where(
                or_(
                    PasswordResetToken.expires_at < now,
                    PasswordResetToken.used.is_(True),
                )
            )
            reset_res = await session.execute(reset_stmt)
            counts["password_reset_tokens"] = reset_res.rowcount or 0

            # 3. Purge login attempt rate-limit records older than 30 days
            login_stmt = delete(LoginAttempt).where(LoginAttempt.attempted_at < thirty_days_ago)
            login_res = await session.execute(login_stmt)
            counts["login_attempts"] = login_res.rowcount or 0

            await session.commit()

            total = sum(counts.values())
            if total > 0:
                logger.info(
                    f"[cleanup] Purged {total} stale security records: "
                    f"{counts['refresh_tokens']} refresh tokens, "
                    f"{counts['password_reset_tokens']} reset tokens, "
                    f"{counts['login_attempts']} login attempts"
                )
            else:
                logger.debug("[cleanup] Security record sweep completed: 0 expired records found.")

            return counts

        except Exception as e:
            await session.rollback()
            logger.error(f"[cleanup] Error during security records cleanup: {e}", exc_info=True)
            raise


security_cleanup_service = SecurityCleanupService()
