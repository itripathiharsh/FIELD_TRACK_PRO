"""
Tally Integration API Router — /api/v1/integrations/tally

Provides secure endpoints for local Tally Sync Agent bridge service:
- Admin management & agent provisioning
- Agent heartbeat and liveness
- Idempotent batch synchronization of Customers, Invoices, and Payments
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps.agent_auth import AuthenticatedAgent
from app.core.deps.auth import CurrentUser, require_role
from app.database import get_async_session
from app.exceptions.custom import ForbiddenException
from app.models.employee import Employee
from app.models.sync_agent import SyncAgent
from app.models.user import Role, User
from app.schemas.tally_sync import (
    CustomerSyncBatch,
    HeartbeatRequest,
    HeartbeatResponse,
    InvoiceSyncBatch,
    PaymentSyncBatch,
    SyncAgentCreate,
    SyncAgentRead,
    SyncAgentRegistrationResponse,
    SyncResultResponse,
    TallyAuditLogListResponse,
    TallyIntegrationStatusResponse,
)
from app.schemas.tally_writeback import (
    TallyWritebackAckRequest,
    TallyWritebackActionResponse,
    TallyWritebackFailRequest,
    TallyWritebackJobRead,
)
from app.services import tally_audit_service, tally_sync_service, tally_writeback_service


router = APIRouter(prefix="/integrations/tally", tags=["tally-integration"])

DbSession = Annotated[AsyncSession, Depends(get_async_session)]
AdminOnly = Depends(require_role(Role.ADMIN))


async def require_admin_or_accountant(user: CurrentUser, session: DbSession) -> User:
    """Enforces caller is an ADMIN or an EMPLOYEE with accountant/billing profile."""
    if user.role == Role.ADMIN:
        return user
    if user.role == Role.EMPLOYEE:
        stmt = select(Employee).where(Employee.user_id == user.id)
        emp = (await session.execute(stmt)).scalar_one_or_none()
        if emp and emp.working_profile:
            wp = emp.working_profile.lower()
            if any(term in wp for term in ["accountant", "billing", "finance", "accounts"]):
                return user
    raise ForbiddenException("Access restricted to Administrators and Accountants")


# ---------------------------------------------------------------------------
# Admin Agent Management
# ---------------------------------------------------------------------------

@router.post(
    "/agents",
    response_model=SyncAgentRegistrationResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[AdminOnly],
)
async def register_sync_agent(data: SyncAgentCreate, session: DbSession):
    """
    Register a new local Tally Sync Agent.
    Generates and returns the one-time raw secret API key for agent configuration.
    """
    agent, raw_key = await tally_sync_service.register_agent(data, session)
    return SyncAgentRegistrationResponse(
        agent=SyncAgentRead.model_validate(agent),
        api_key=raw_key,
    )


@router.get("/agents", response_model=list[SyncAgentRead], dependencies=[AdminOnly])
async def list_sync_agents(session: DbSession):
    """List all registered Tally Sync Agents."""
    stmt = select(SyncAgent).order_by(SyncAgent.created_at.desc())
    agents = (await session.execute(stmt)).scalars().all()
    return [SyncAgentRead.model_validate(a) for a in agents]


@router.get("/status", response_model=TallyIntegrationStatusResponse)
async def get_tally_status(session: DbSession, user: CurrentUser):
    """
    Get live Tally integration connectivity, company, and sync statistics.
    Accessible to all authenticated users for UI freshness indicators.
    """
    return await tally_sync_service.get_integration_status(session)


@router.get(
    "/audit-logs",
    response_model=TallyAuditLogListResponse,
    dependencies=[Depends(require_admin_or_accountant)],
)
async def get_tally_audit_logs(
    session: DbSession,
    direction: Optional[str] = Query(None, description="Filter by direction: READ or WRITE"),
    status: Optional[str] = Query(None, description="Filter by status: SUCCESS, FAILED, PARTIAL, PENDING, PROCESSING"),
    entity_type: Optional[str] = Query(None, description="Filter by entity type: CUSTOMERS, INVOICES, PAYMENTS"),
    start_date: Optional[datetime] = Query(None, description="Start datetime ISO filter"),
    end_date: Optional[datetime] = Query(None, description="End datetime ISO filter"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
):
    """
    Retrieve unified chronological audit log of all Tally READ and WRITE operations.
    Combines persistent read audit logs with live writeback queue records.
    Restricted to Admins and Accountants.
    """
    return await tally_audit_service.get_audit_logs(
        session=session,
        direction=direction,
        status=status,
        entity_type=entity_type,
        start_date=start_date,
        end_date=end_date,
        skip=skip,
        limit=limit,
    )


# ---------------------------------------------------------------------------
# Agent Communication Endpoints (Authenticated by X-Agent-Id + X-Agent-Key)
# ---------------------------------------------------------------------------

@router.post("/heartbeat", response_model=HeartbeatResponse)
async def agent_heartbeat(
    data: HeartbeatRequest,
    agent: AuthenticatedAgent,
    session: DbSession,
):
    """Record heartbeat, version, and status from the local Sync Agent."""
    return await tally_sync_service.record_heartbeat(agent, data, session)


@router.post("/sync/customers", response_model=SyncResultResponse)
async def sync_customers(
    batch: CustomerSyncBatch,
    agent: AuthenticatedAgent,
    session: DbSession,
):
    """Idempotently sync customer / outlet records from Tally."""
    return await tally_sync_service.sync_customers(agent, batch, session)


@router.post("/sync/invoices", response_model=SyncResultResponse)
async def sync_invoices(
    batch: InvoiceSyncBatch,
    agent: AuthenticatedAgent,
    session: DbSession,
):
    """Idempotently sync sales invoices from Tally."""
    return await tally_sync_service.sync_invoices(agent, batch, session)


@router.post("/sync/payments", response_model=SyncResultResponse)
async def sync_payments(
    batch: PaymentSyncBatch,
    agent: AuthenticatedAgent,
    session: DbSession,
):
    """Idempotently sync payment / receipt records from Tally."""
    return await tally_sync_service.sync_payments(agent, batch, session)


# ---------------------------------------------------------------------------
# Outbox Endpoints: BE -> Tally Write-Back
# ---------------------------------------------------------------------------

@router.get("/outbox/pending", response_model=list[TallyWritebackJobRead])
async def get_pending_outbox_jobs(
    agent: AuthenticatedAgent,
    session: DbSession,
    limit: int = 10,
):
    """
    Fetch and atomically claim pending Tally write-back jobs.
    Uses database row-level locking to ensure safe concurrency across agent pollers.
    """
    jobs = await tally_writeback_service.claim_pending_jobs(session, limit=limit)
    return [TallyWritebackJobRead.model_validate(j) for j in jobs]


@router.post("/outbox/{job_id}/ack", response_model=TallyWritebackActionResponse)
async def ack_outbox_job(
    job_id: uuid.UUID,
    data: TallyWritebackAckRequest,
    agent: AuthenticatedAgent,
    session: DbSession,
):
    """
    Acknowledge successful creation of receipt voucher in Tally.
    Persists Tally GUID and identifiers, prevents duplicate write-backs.
    """
    job = await tally_writeback_service.ack_writeback_job(session, job_id, data)
    return TallyWritebackActionResponse(
        status="CONFIRMED",
        job_id=job.id,
        message="Job successfully acknowledged and confirmed with Tally identifiers.",
    )


@router.post("/outbox/{job_id}/fail", response_model=TallyWritebackActionResponse)
async def fail_outbox_job(
    job_id: uuid.UUID,
    data: TallyWritebackFailRequest,
    agent: AuthenticatedAgent,
    session: DbSession,
):
    """
    Record error attempting to write to Tally.
    Applies exponential backoff for retryable errors or marks terminal failure.
    """
    job = await tally_writeback_service.fail_writeback_job(session, job_id, data)
    return TallyWritebackActionResponse(
        status=job.status.value if hasattr(job.status, "value") else str(job.status),
        job_id=job.id,
        message=f"Job status updated to {job.status}: {data.error_message}",
    )

