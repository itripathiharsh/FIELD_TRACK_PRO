from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import Depends, Header
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import verify_password
from app.database import get_async_session
from app.exceptions.custom import UnauthorizedException, ForbiddenException
from app.models.sync_agent import SyncAgent

DbSession = Annotated[AsyncSession, Depends(get_async_session)]


async def get_authenticated_agent(
    session: DbSession,
    x_agent_id: str | None = Header(default=None, alias="X-Agent-Id"),
    x_agent_key: str | None = Header(default=None, alias="X-Agent-Key"),
) -> SyncAgent:
    """
    Authenticate a Sync Agent from X-Agent-Id and X-Agent-Key headers.
    Derives the tenant/organization boundary securely from the agent record.
    """
    if not x_agent_id or not x_agent_key:
        raise UnauthorizedException("Missing X-Agent-Id or X-Agent-Key headers")

    try:
        agent_uuid = uuid.UUID(x_agent_id)
    except ValueError:
        raise UnauthorizedException("Invalid X-Agent-Id format")

    stmt = select(SyncAgent).where(SyncAgent.id == agent_uuid)
    result = await session.execute(stmt)
    agent = result.scalar_one_or_none()

    if not agent or not agent.is_active:
        raise UnauthorizedException("Invalid or inactive sync agent")

    if not verify_password(x_agent_key, agent.api_key_hash):
        raise UnauthorizedException("Invalid agent key")

    return agent


AuthenticatedAgent = Annotated[SyncAgent, Depends(get_authenticated_agent)]
