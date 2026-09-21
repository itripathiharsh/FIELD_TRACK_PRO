from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.sync_agent import SyncAgent
from app.models.tally_audit import TallyAuditLog
from app.models.tally_writeback import TallyWritebackQueue, WritebackStatus
from app.schemas.tally_sync import TallyAuditLogItem, TallyAuditLogListResponse

logger = logging.getLogger("fieldtrackpro")


async def record_read_audit(
    session: AsyncSession,
    agent: SyncAgent,
    operation: str,
    entity_type: str,
    record_count: int,
    status: str,
    duration_ms: Optional[int] = None,
    error_message: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
) -> TallyAuditLog:
    """
    Creates and persists an audit entry for a Tally -> FieldTrack READ operation.
    """
    audit_entry = TallyAuditLog(
        direction="READ",
        operation=operation,
        entity_type=entity_type,
        record_count=record_count,
        status=status,
        duration_ms=duration_ms,
        error_message=error_message,
        agent_id=agent.id if agent else None,
        agent_name=agent.name if agent else None,
        company_name=agent.tally_company_name if agent else None,
        company_guid=agent.tally_company_guid if agent else None,
        details=details,
    )
    session.add(audit_entry)
    await session.commit()
    await session.refresh(audit_entry)
    return audit_entry


def _map_writeback_to_audit_item(job: TallyWritebackQueue, agent: Optional[SyncAgent] = None) -> TallyAuditLogItem:
    """Converts a TallyWritebackQueue entry into a unified TallyAuditLogItem."""
    status_map = {
        WritebackStatus.CONFIRMED: "SUCCESS",
        WritebackStatus.FAILED: "FAILED",
        WritebackStatus.PROCESSING: "PROCESSING",
        WritebackStatus.PENDING: "PENDING",
        WritebackStatus.SENT: "PROCESSING",
    }
    unified_status = status_map.get(job.status, str(job.status))

    duration_ms = None
    if job.confirmed_at and job.sent_at:
        duration_ms = max(0, int((job.confirmed_at - job.sent_at).total_seconds() * 1000))

    timestamp = job.confirmed_at or job.sent_at or job.created_at

    payload = job.payload or {}
    clean_details = {
        "payment_id": payload.get("payment_id"),
        "customer_name": payload.get("customer_name"),
        "amount": payload.get("amount"),
        "payment_method": payload.get("payment_method"),
        "invoice_number": payload.get("invoice_number"),
        "outlet_code": payload.get("outlet_code"),
        "retry_count": job.retry_count,
        "idempotency_key": job.idempotency_key,
    }

    return TallyAuditLogItem(
        id=job.id,
        timestamp=timestamp,
        direction="WRITE",
        operation=job.operation or "CREATE_RECEIPT",
        entity_type=job.entity_type or "PAYMENT",
        record_count=1,
        status=unified_status,
        duration_ms=duration_ms,
        error_message=job.last_error,
        agent_id=agent.id if agent else None,
        agent_name=agent.name if agent else None,
        company_name=agent.tally_company_name if agent else None,
        company_guid=agent.tally_company_guid if agent else None,
        tally_guid=job.tally_guid,
        tally_voucher_number=job.tally_voucher_number,
        writeback_job_id=job.id,
        details=clean_details,
    )


def _map_audit_log_to_audit_item(log: TallyAuditLog) -> TallyAuditLogItem:
    """Converts a TallyAuditLog row into a TallyAuditLogItem."""
    return TallyAuditLogItem(
        id=log.id,
        timestamp=log.timestamp,
        direction=log.direction,
        operation=log.operation,
        entity_type=log.entity_type,
        record_count=log.record_count,
        status=log.status,
        duration_ms=log.duration_ms,
        error_message=log.error_message,
        agent_id=log.agent_id,
        agent_name=log.agent_name,
        company_name=log.company_name,
        company_guid=log.company_guid,
        tally_guid=log.tally_guid,
        tally_voucher_number=log.tally_voucher_number,
        writeback_job_id=log.writeback_job_id,
        details=log.details,
    )


async def get_audit_logs(
    session: AsyncSession,
    direction: Optional[str] = None,
    status: Optional[str] = None,
    entity_type: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    skip: int = 0,
    limit: int = 50,
) -> TallyAuditLogListResponse:
    """
    Retrieves a unified chronological list of Tally audit entries.
    Merges persistent READ audit logs with live WRITE writeback queue entries.
    """
    items: List[TallyAuditLogItem] = []

    # Lookup active agent for writeback contextual display
    agent_stmt = select(SyncAgent).order_by(SyncAgent.updated_at.desc()).limit(1)
    active_agent = (await session.execute(agent_stmt)).scalar_one_or_none()

    clean_dir = direction.strip().upper() if direction else None
    clean_status = status.strip().upper() if status else None
    clean_entity = entity_type.strip().upper() if entity_type else None

    # 1. Fetch READ items from tally_audit_logs
    if clean_dir is None or clean_dir == "READ":
        stmt = select(TallyAuditLog)
        if clean_status:
            if clean_status == "SUCCESS":
                stmt = stmt.where(TallyAuditLog.status.in_(["SUCCESS", "PARTIAL"]))
            elif clean_status == "FAILED":
                stmt = stmt.where(TallyAuditLog.status.in_(["FAILED", "PARTIAL"]))
            else:
                stmt = stmt.where(func.upper(TallyAuditLog.status) == clean_status)

        if clean_entity:
            stmt = stmt.where(func.upper(TallyAuditLog.entity_type) == clean_entity)

        if start_date:
            stmt = stmt.where(TallyAuditLog.timestamp >= start_date)
        if end_date:
            stmt = stmt.where(TallyAuditLog.timestamp <= end_date)

        # Order and limit (fetch adequate pool to merge)
        stmt = stmt.order_by(TallyAuditLog.timestamp.desc()).limit(skip + limit + 100)
        read_logs = (await session.execute(stmt)).scalars().all()
        for log in read_logs:
            items.append(_map_audit_log_to_audit_item(log))

    # 2. Fetch WRITE items from tally_writeback_queue
    if clean_dir is None or clean_dir == "WRITE":
        wb_stmt = select(TallyWritebackQueue)

        if clean_status:
            if clean_status == "SUCCESS":
                wb_stmt = wb_stmt.where(TallyWritebackQueue.status == WritebackStatus.CONFIRMED)
            elif clean_status == "FAILED":
                wb_stmt = wb_stmt.where(TallyWritebackQueue.status == WritebackStatus.FAILED)
            elif clean_status == "PENDING":
                wb_stmt = wb_stmt.where(TallyWritebackQueue.status == WritebackStatus.PENDING)
            elif clean_status == "PROCESSING":
                wb_stmt = wb_stmt.where(
                    TallyWritebackQueue.status.in_([WritebackStatus.PROCESSING, WritebackStatus.SENT])
                )

        if clean_entity:
            wb_stmt = wb_stmt.where(func.upper(TallyWritebackQueue.entity_type) == clean_entity)

        if start_date:
            wb_stmt = wb_stmt.where(
                func.coalesce(
                    TallyWritebackQueue.confirmed_at,
                    TallyWritebackQueue.sent_at,
                    TallyWritebackQueue.created_at,
                ) >= start_date
            )
        if end_date:
            wb_stmt = wb_stmt.where(
                func.coalesce(
                    TallyWritebackQueue.confirmed_at,
                    TallyWritebackQueue.sent_at,
                    TallyWritebackQueue.created_at,
                ) <= end_date
            )

        wb_stmt = wb_stmt.order_by(TallyWritebackQueue.created_at.desc()).limit(skip + limit + 100)
        wb_jobs = (await session.execute(wb_stmt)).scalars().all()
        for job in wb_jobs:
            items.append(_map_writeback_to_audit_item(job, active_agent))

    # 3. Sort merged list chronologically descending
    items.sort(key=lambda x: x.timestamp, reverse=True)

    total_count = len(items)
    paginated_items = items[skip : skip + limit]

    return TallyAuditLogListResponse(
        items=paginated_items,
        total=total_count,
        skip=skip,
        limit=limit,
    )


async def get_today_summary(session: AsyncSession) -> Dict[str, Any]:
    """
    Computes today's operational read/write stats and last successful sync.
    """
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    # Today's READ batches / records
    read_stmt = select(
        func.coalesce(func.sum(TallyAuditLog.record_count), 0),
        func.count(TallyAuditLog.id),
    ).where(
        TallyAuditLog.direction == "READ",
        TallyAuditLog.timestamp >= today_start,
    )
    read_res = (await session.execute(read_stmt)).first()
    today_read_records = int(read_res[0]) if read_res else 0
    today_read_batches = int(read_res[1]) if read_res else 0
    # Use records count if available, otherwise batches count
    today_reads = today_read_records if today_read_records > 0 else today_read_batches

    # Today's WRITE jobs
    write_stmt = select(func.count(TallyWritebackQueue.id)).where(
        TallyWritebackQueue.created_at >= today_start
    )
    today_writes = (await session.execute(write_stmt)).scalar() or 0

    # Failed operations today (READ failures + WRITE failures)
    read_fail_stmt = select(func.count(TallyAuditLog.id)).where(
        TallyAuditLog.status.in_(["FAILED", "PARTIAL"]),
        TallyAuditLog.timestamp >= today_start,
    )
    read_fails = (await session.execute(read_fail_stmt)).scalar() or 0

    write_fail_stmt = select(func.count(TallyWritebackQueue.id)).where(
        TallyWritebackQueue.status == WritebackStatus.FAILED,
        TallyWritebackQueue.created_at >= today_start,
    )
    write_fails = (await session.execute(write_fail_stmt)).scalar() or 0
    failed_ops = read_fails + write_fails

    # Last successful sync
    last_succ_stmt = (
        select(TallyAuditLog.timestamp)
        .where(
            TallyAuditLog.direction == "READ",
            TallyAuditLog.status == "SUCCESS",
        )
        .order_by(TallyAuditLog.timestamp.desc())
        .limit(1)
    )
    last_succ_time = (await session.execute(last_succ_stmt)).scalar_one_or_none()

    return {
        "today_read_count": today_reads,
        "today_write_count": today_writes,
        "failed_operation_count": failed_ops,
        "last_successful_sync_at": last_succ_time,
    }
