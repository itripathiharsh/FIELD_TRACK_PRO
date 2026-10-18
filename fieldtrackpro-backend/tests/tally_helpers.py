"""
Test helper: simulate the Sync Agent confirming a payment's Tally write-back.

Business rule under test: outstanding only drops once the write-back job is
CONFIRMED (the agent ACKs the receipt voucher it created in Tally).
"""
from __future__ import annotations

import uuid

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.payment import Payment
from app.models.tally_writeback import TallyWritebackQueue
from app.schemas.tally_writeback import TallyWritebackAckRequest, TallyWritebackFailRequest
from app.services import tally_writeback_service


async def _job_for(session, payment_id):
    return (
        await session.execute(
            select(TallyWritebackQueue).where(
                TallyWritebackQueue.entity_type == "PAYMENT",
                TallyWritebackQueue.entity_id == uuid.UUID(str(payment_id)),
            )
        )
    ).scalar_one_or_none()


async def ack_payment_in_tally(payment_id, guid: str | None = None, voucher: str = "RCPT-1") -> str:
    """Enqueue (if verification did not already) and ACK the job. Returns the tally guid."""
    guid = guid or f"GUID-{uuid.uuid4()}"
    async with AsyncSessionLocal() as session:
        job = await _job_for(session, payment_id)
        if job is None:
            payment = (await session.execute(select(Payment).where(Payment.id == uuid.UUID(str(payment_id))))).scalar_one()
            job = await tally_writeback_service.enqueue_payment_writeback(session, payment)
            await session.commit()
        await tally_writeback_service.ack_writeback_job(
            session, job.id, TallyWritebackAckRequest(tally_guid=guid, tally_master_id="42", tally_voucher_number=voucher)
        )
    return guid


async def fail_payment_in_tally(payment_id, message: str = "Ledger not found", retryable: bool = False) -> None:
    async with AsyncSessionLocal() as session:
        job = await _job_for(session, payment_id)
        if job is None:
            payment = (await session.execute(select(Payment).where(Payment.id == uuid.UUID(str(payment_id))))).scalar_one()
            job = await tally_writeback_service.enqueue_payment_writeback(session, payment)
            await session.commit()
        await tally_writeback_service.fail_writeback_job(
            session, job.id, TallyWritebackFailRequest(error_message=message, is_retryable=retryable)
        )
