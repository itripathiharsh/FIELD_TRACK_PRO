from __future__ import annotations

import logging
import uuid
from typing import Annotated

from fastapi import Depends, Header, Request
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.client_ip import get_client_ip
from app.core.rate_limiter import agent_key_id_limiter, agent_key_ip_limiter, throttle_key
from app.core.security import verify_password
from app.database import get_async_session
from app.exceptions.custom import UnauthorizedException
from app.models.login_attempt import LoginAttempt
from app.models.sync_agent import SyncAgent

DbSession = Annotated[AsyncSession, Depends(get_async_session)]

logger = logging.getLogger("fieldtrackpro")


async def authenticate_agent(
    session: AsyncSession,
    request: Request | None,
    x_agent_id: str | None,
    x_agent_key: str | None,
) -> SyncAgent:
    """
    Authenticate a Sync Agent from X-Agent-Id and X-Agent-Key.

    Brute-force protection: failed attempts are counted per client IP (10 /
    15 min) and per presented agent id (10 / 15 min). Once either budget is
    exhausted the request is refused with 429 BEFORE any key verification
    work, whether or not the agent id exists.
    """
    if not x_agent_id or not x_agent_key:
        raise UnauthorizedException("Missing X-Agent-Id or X-Agent-Key headers")

    client_ip = get_client_ip(request)
    ip_key = throttle_key("agentkey", "ip", client_ip) if client_ip else None
    id_key = throttle_key("agentkey", "id", x_agent_id)

    if ip_key:
        await agent_key_ip_limiter.check_allowed(ip_key, session)
    await agent_key_id_limiter.check_allowed(id_key, session)

    async def _fail(message: str) -> UnauthorizedException:
        if ip_key:
            await agent_key_ip_limiter.record_failure(ip_key, session)
        await agent_key_id_limiter.record_failure(id_key, session)
        logger.warning("event=tally_agent_auth result=failed reason=%s", message.replace(" ", "_").upper())
        return UnauthorizedException(message)

    try:
        agent_uuid = uuid.UUID(x_agent_id)
    except ValueError:
        raise await _fail("Invalid X-Agent-Id format")

    agent = (await session.execute(select(SyncAgent).where(SyncAgent.id == agent_uuid))).scalar_one_or_none()
    if not agent or not agent.is_active:
        raise await _fail("Invalid or inactive sync agent")

    if not verify_password(x_agent_key, agent.api_key_hash):
        raise await _fail("Invalid agent key")

    # A correct key clears only this agent's own failure counter (not the IP's).
    await session.execute(delete(LoginAttempt).where(LoginAttempt.identifier == id_key))
    await session.commit()
    return agent


async def get_authenticated_agent(
    request: Request,
    session: DbSession,
    x_agent_id: str | None = Header(default=None, alias="X-Agent-Id"),
    x_agent_key: str | None = Header(default=None, alias="X-Agent-Key"),
) -> SyncAgent:
    return await authenticate_agent(session, request, x_agent_id, x_agent_key)


AuthenticatedAgent = Annotated[SyncAgent, Depends(get_authenticated_agent)]
