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

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps.agent_auth import AuthenticatedAgent, authenticate_agent
from app.core.deps.auth import CurrentUser, _get_user_from_token, require_role
from app.database import get_async_session
from app.exceptions.custom import ForbiddenException, UnauthorizedException
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
from app.schemas.tally_sync_v2 import (
    BillsSyncBatch,
    LedgerSyncBatch,
    ManifestSyncBatch,
    V2SyncResult,
    VoucherSyncBatch,
)
from app.services import (
    tally_audit_service,
    tally_reconciliation,
    tally_sync_service,
    tally_v2_sync,
    tally_writeback_service,
)


router = APIRouter(prefix="/integrations/tally", tags=["tally-integration"])

DbSession = Annotated[AsyncSession, Depends(get_async_session)]
AdminOnly = Depends(require_role(Role.ADMIN))


_optional_bearer = HTTPBearer(auto_error=False)


async def require_admin_or_agent(
    request: Request,
    session: DbSession,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_optional_bearer)],
) -> None:
    """Allow either an authenticated ADMIN (JWT) or an authenticated Sync Agent (X-Agent-* headers)."""
    if request.headers.get("X-Agent-Id") or request.headers.get("X-Agent-Key"):
        await authenticate_agent(
            session, request, request.headers.get("X-Agent-Id"), request.headers.get("X-Agent-Key")
        )
        return
    if credentials is None:
        raise UnauthorizedException("Authentication required")
    user = await _get_user_from_token(credentials, session)
    if not user.is_admin:
        raise ForbiddenException("Access restricted to Administrators")


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


@router.get(
    "/status",
    response_model=TallyIntegrationStatusResponse,
    dependencies=[Depends(require_admin_or_agent)],
)
async def get_tally_status(session: DbSession):
    """
    Get live Tally integration connectivity, company, and sync statistics.
    Restricted to Administrators and the Sync Agent (employees have no access).
    """
    return await tally_sync_service.get_integration_status(session)


@router.get(
    "/audit-logs",
    response_model=TallyAuditLogListResponse,
    dependencies=[AdminOnly],
)
async def get_tally_audit_logs(
    session: DbSession,
    direction: Optional[str] = Query(None, description="Filter by direction: READ or WRITE"),
    status: Optional[str] = Query(None, description="Filter by status: SUCCESS, FAILED, PARTIAL, PENDING, PROCESSING"),
    entity_type: Optional[str] = Query(None, description="Filter by entity type: CUSTOMERS, INVOICES, PAYMENTS"),
    start_date: Optional[datetime] = Query(None, description="Start datetime ISO filter"),
    end_date: Optional[datetime] = Query(None, description="End datetime ISO filter"),
    sort_order: Optional[str] = Query("desc", description="Sort order: desc or asc"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
):
    """
    Retrieve unified chronological audit log of all Tally READ and WRITE operations.
    Combines persistent read audit logs with live writeback queue records.
    Restricted to Administrators.
    """
    return await tally_audit_service.get_audit_logs(
        session=session,
        direction=direction,
        status=status,
        entity_type=entity_type,
        start_date=start_date,
        end_date=end_date,
        sort_order=sort_order,
        skip=skip,
        limit=limit,
    )


# ---------------------------------------------------------------------------
# Agent Communication Endpoints (Authenticated by X-Agent-Id + X-Agent-Key)
# ---------------------------------------------------------------------------

@router.get("/capabilities")
async def agent_capabilities(agent: AuthenticatedAgent):
    """Release 2.2.0: what this backend guarantees to the agent. `history_safe` = Tally rows dated before the
    reporting floor (historical financial years) cannot create pending-close reporting periods (B1), are kept
    out of live screens / BI / ageing (B4), and bill due dates are matched on date when bill names repeat (B6).
    The 2.2.0 agent uploads a historical FY only when this is true (and the FY is listed in HISTORY_UPLOAD)."""
    from app.services.reporting_floor import reporting_floor
    return {"history_safe": True, "reporting_floor": reporting_floor().isoformat(), "backend_release": "2.2.0",
            "agent_id": str(agent.id)}


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
# Agent 2.0 sync (ledgers, every debtor voucher, Bills Receivable, GUID manifest)
# ---------------------------------------------------------------------------

@router.post("/sync/ledgers", response_model=V2SyncResult)
async def sync_ledgers_v2(batch: LedgerSyncBatch, agent: AuthenticatedAgent, session: DbSession):
    """Ledger masters (debtors in full, other ledgers by GUID/group) and balance snapshots."""
    return await tally_v2_sync.sync_ledgers(agent, batch, session)


@router.post("/sync/vouchers", response_model=V2SyncResult)
async def sync_vouchers_v2(batch: VoucherSyncBatch, agent: AuthenticatedAgent, session: DbSession):
    """Changed vouchers with their debtor lines; classified into invoices, receipts, adjustments."""
    return await tally_v2_sync.sync_vouchers(agent, batch, session)


@router.post("/sync/bills", response_model=V2SyncResult)
async def sync_bills_v2(batch: BillsSyncBatch, agent: AuthenticatedAgent, session: DbSession):
    """Tally's Bills Receivable report as on a date (chunked snapshot)."""
    return await tally_v2_sync.sync_bills(agent, batch, session)


@router.post("/sync/manifest", response_model=V2SyncResult)
async def sync_manifest_v2(batch: ManifestSyncBatch, agent: AuthenticatedAgent, session: DbSession):
    """Every voucher GUID in a date window; synced rows absent from it are retired."""
    return await tally_v2_sync.sync_manifest(agent, batch, session)


@router.get("/reconciliation", dependencies=[AdminOnly])
async def get_tally_reconciliation(
    session: DbSession,
    limit: int = Query(200, ge=1, le=5000),
):
    """FieldTrack vs Tally, per debtor: opening + synced movements - closing (must be 0)."""
    return await tally_reconciliation.build_report(session, limit=limit)


# ---------------------------------------------------------------------------
# Outbox Endpoints: BE -> Tally Write-Back
# ---------------------------------------------------------------------------

@router.get("/outbox/pending", response_model=list[TallyWritebackJobRead])
async def get_pending_outbox_jobs(
    agent: AuthenticatedAgent,
    session: DbSession,
    limit: int = Query(10, ge=1, le=100),
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
    job = await tally_writeback_service.ack_writeback_job(session, job_id, data, agent=agent)
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
    job = await tally_writeback_service.fail_writeback_job(session, job_id, data, agent=agent)
    return TallyWritebackActionResponse(
        status=job.status.value if hasattr(job.status, "value") else str(job.status),
        job_id=job.id,
        message=f"Job status updated to {job.status}: {data.error_message}",
    )


@router.post(
    "/outbox/{job_id}/retry",
    response_model=TallyWritebackActionResponse,
    dependencies=[AdminOnly],
)
async def retry_outbox_job(
    job_id: uuid.UUID,
    session: DbSession,
    user: CurrentUser,
):
    """
    Manually reset a failed or pending outbox write-back job to PENDING.
    Clears error and backoff timer so the local Sync Agent picks it up on next cycle.
    """
    job = await tally_writeback_service.retry_writeback_job(session, job_id, actor_user_id=user.id)
    return TallyWritebackActionResponse(
        status="PENDING",
        job_id=job.id,
        message="Write-back operation reset to PENDING and scheduled for immediate Tally execution.",
    )


