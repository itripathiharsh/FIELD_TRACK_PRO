"""
Refresh token repository.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.refresh_token import RefreshToken
from app.repositories.base import BaseRepository


class TokenRepository(BaseRepository[RefreshToken]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(RefreshToken, session)

    async def get_active_by_hash(self, token_hash: str) -> RefreshToken | None:
        now = datetime.utcnow()
        result = await self.session.execute(
            select(RefreshToken)
            .where(RefreshToken.token_hash == token_hash)
            .where(RefreshToken.revoked.is_(False))
            .where(RefreshToken.expires_at > now)
        )
        return result.scalar_one_or_none()

    async def get_by_hash(self, token_hash: str) -> RefreshToken | None:
        result = await self.session.execute(
            select(RefreshToken).where(RefreshToken.token_hash == token_hash)
        )
        return result.scalar_one_or_none()

    async def revoke_all_for_user(self, user_id: uuid.UUID) -> int:
        """
        Revoke every outstanding refresh token for a user.

        Required by the locked auth design (`16_authentication.md` section 3):
        this is what makes a password change - and employee deactivation -
        take effect immediately rather than after the 7-day token lifetime.

        Returns the number of tokens revoked.
        """
        result = await self.session.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == user_id)
            .where(RefreshToken.revoked.is_(False))
            .values(revoked=True)
        )
        return int(result.rowcount or 0)
