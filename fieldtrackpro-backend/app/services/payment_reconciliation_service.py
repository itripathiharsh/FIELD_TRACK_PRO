"""
Field collection <-> Tally receipt reconciliation.

With Tally write-back disabled the accountant keys each receipt into Tally by
hand and the sync agent imports it as a separate TALLY payment. The employee's
MANUAL collection and that receipt are the same money; an admin confirms this by
linking them (never automatic). Once linked, payment_tally counts the money
once, through the TALLY receipt, and the collection shows as POSTED.

Several collections may be linked to one receipt (the accountant can batch a
day's cash into one voucher); their total may not exceed the receipt amount.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions.custom import BaseAPIException
from app.models.payment import Payment, PaymentSource, PaymentStatus
from app.repositories.payment_repo import PaymentRepository
from app.schemas.payment import TallyReceiptCandidate
from app.services import payment_tally, tally_audit_service

DEFAULT_WINDOW_DAYS = 7
MAX_WINDOW_DAYS = 60
_MONEY_TOLERANCE = Decimal("0.005")


def _err(status_code: int, code: str, detail: str) -> BaseAPIException:
    return BaseAPIException(status_code=status_code, detail=detail, error_code=code)


def _norm(v: str | None) -> str:
    return (v or "").strip().upper()


async def _linked_amounts(session: AsyncSession, receipt_ids: list[uuid.UUID]) -> dict[uuid.UUID, Decimal]:
    if not receipt_ids:
        return {}
    rows = (
        await session.execute(
            select(Payment.tally_receipt_payment_id, func.coalesce(func.sum(Payment.amount), Decimal("0.00")))
            .where(Payment.tally_receipt_payment_id.in_(receipt_ids))
            .group_by(Payment.tally_receipt_payment_id)
        )
    ).all()
    return {rid: amt for rid, amt in rows}


async def _get_field_collection(session: AsyncSession, payment_id: uuid.UUID, lock: bool = False) -> Payment:
    stmt = select(Payment).where(Payment.id == payment_id).execution_options(populate_existing=True)
    if lock:
        stmt = stmt.with_for_update()
    payment = (await session.execute(stmt)).scalar_one_or_none()
    if payment is None:
        raise _err(404, "PAYMENT_NOT_FOUND", "Payment not found")
    if payment.source != PaymentSource.MANUAL:
        raise _err(422, "PAYMENT_NOT_FIELD_COLLECTION", "Only an employee-recorded field collection can be linked to a Tally receipt.")
    return payment


async def suggest_tally_receipts(
    session: AsyncSession, payment_id: uuid.UUID, window_days: int = DEFAULT_WINDOW_DAYS
) -> list[TallyReceiptCandidate]:
    """Imported Tally receipts of the same outlet, dated within +/- window_days of
    the collection, that still have room for it. Ranked by UTR, cheque number,
    exact amount, then date proximity. Suggestions only - nothing is linked here."""
    payment = await _get_field_collection(session, payment_id)
    window = max(0, min(window_days, MAX_WINDOW_DAYS))
    receipts = (
        await session.execute(
            select(Payment).where(
                Payment.source == PaymentSource.TALLY,
                Payment.status == PaymentStatus.VERIFIED,
                Payment.customer_id == payment.customer_id,
                Payment.payment_date >= payment.payment_date - timedelta(days=window),
                Payment.payment_date <= payment.payment_date + timedelta(days=window),
            )
        )
    ).scalars().all()
    linked = await _linked_amounts(session, [r.id for r in receipts])

    out: list[TallyReceiptCandidate] = []
    for r in receipts:
        already = linked.get(r.id, Decimal("0.00"))
        if r.id == payment.tally_receipt_payment_id:
            already -= payment.amount
        available = r.amount - already
        if payment.amount - available > _MONEY_TOLERANCE:
            continue
        reasons = []
        if _norm(payment.utr_reference) and _norm(payment.utr_reference) == _norm(r.utr_reference):
            reasons.append("UTR")
        if _norm(payment.cheque_number) and _norm(payment.cheque_number) == _norm(r.cheque_number):
            reasons.append("CHEQUE_NUMBER")
        if abs(r.amount - payment.amount) <= _MONEY_TOLERANCE:
            reasons.append("AMOUNT")
        out.append(
            TallyReceiptCandidate(
                payment_id=r.id,
                payment_date=r.payment_date,
                amount=r.amount,
                payment_method=r.payment_method,
                utr_reference=r.utr_reference,
                cheque_number=r.cheque_number,
                notes=r.notes,
                source_reference=r.source_reference,
                linked_amount=already,
                available_amount=available,
                days_apart=abs((r.payment_date - payment.payment_date).days),
                match_reasons=reasons,
            )
        )
    out.sort(key=lambda c: (
        "UTR" not in c.match_reasons,
        "CHEQUE_NUMBER" not in c.match_reasons,
        "AMOUNT" not in c.match_reasons,
        c.days_apart,
        str(c.payment_id),
    ))
    return out


async def link_tally_receipt(
    session: AsyncSession, payment_id: uuid.UUID, receipt_id: uuid.UUID, actor_user_id: uuid.UUID
) -> Payment:
    """Admin confirmation that a VERIFIED field collection is the same money as an
    imported Tally receipt of the same outlet."""
    # Lock the receipt first: concurrent links to the same receipt serialise on
    # it, so the "total may not exceed the receipt" check cannot be raced.
    receipt = (
        await session.execute(
            select(Payment).where(Payment.id == receipt_id).with_for_update().execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    payment = await _get_field_collection(session, payment_id, lock=True)

    async def fail(status_code: int, code: str, detail: str):
        await session.rollback()
        raise _err(status_code, code, detail)

    if receipt is None:
        await fail(404, "TALLY_RECEIPT_NOT_FOUND", "Tally receipt not found")
    if receipt.source != PaymentSource.TALLY:
        await fail(422, "RECEIPT_NOT_FROM_TALLY", "The selected payment is not a receipt imported from Tally.")
    if payment.status != PaymentStatus.VERIFIED:
        await fail(409, "PAYMENT_NOT_VERIFIED", "Verify the collection against the bank before linking it to a Tally receipt.")
    if payment.tally_receipt_payment_id is not None:
        await fail(409, "PAYMENT_ALREADY_LINKED", "This collection is already linked to a Tally receipt; unlink it first.")
    job = (await payment_tally.load_jobs(session, [payment.id])).get(payment.id)
    if payment_tally.derive_tally_status(payment, job) == payment_tally.TallyStatus.POSTED:
        await fail(409, "PAYMENT_ALREADY_POSTED", "This collection is already posted to Tally by write-back.")
    if receipt.customer_id != payment.customer_id:
        await fail(422, "RECEIPT_OUTLET_MISMATCH", "The Tally receipt belongs to a different outlet than the collection.")
    already = (await _linked_amounts(session, [receipt.id])).get(receipt.id, Decimal("0.00"))
    if already + payment.amount - receipt.amount > _MONEY_TOLERANCE:
        await fail(
            422,
            "RECEIPT_AMOUNT_EXCEEDED",
            f"Linking would exceed the Tally receipt: receipt {receipt.amount:,.2f}, already linked "
            f"{already:,.2f}, this collection {payment.amount:,.2f}.",
        )

    before = payment_tally.derive_tally_status(payment, job).value
    payment.tally_receipt_payment_id = receipt.id
    payment.tally_linked_at = datetime.now(timezone.utc)
    payment.tally_linked_by = actor_user_id
    session.add(payment)
    await session.flush()
    await tally_audit_service.record_review_audit(
        session,
        operation="PAYMENT_TALLY_LINK",
        actor_user_id=actor_user_id,
        payment_id=payment.id,
        before_status=before,
        after_status=payment_tally.TallyStatus.POSTED.value,
        details={
            "tally_receipt_payment_id": str(receipt.id),
            "tally_receipt_source_reference": receipt.source_reference,
            "collection_amount": str(payment.amount),
            "receipt_amount": str(receipt.amount),
            "receipt_linked_total_after": str(already + payment.amount),
        },
    )
    await session.commit()
    return await PaymentRepository(session).get_by_id(payment_id)


async def unlink_tally_receipt(
    session: AsyncSession, payment_id: uuid.UUID, reason: str, actor_user_id: uuid.UUID
) -> Payment:
    """Admin correction of a wrong link; the collection returns to AWAITING_TALLY."""
    payment = await _get_field_collection(session, payment_id, lock=True)
    if payment.tally_receipt_payment_id is None:
        await session.rollback()
        raise _err(409, "PAYMENT_NOT_LINKED", "This collection is not linked to a Tally receipt.")
    receipt_id = payment.tally_receipt_payment_id
    payment.tally_receipt_payment_id = None
    payment.tally_linked_at = None
    payment.tally_linked_by = None
    session.add(payment)
    await session.flush()
    job = (await payment_tally.load_jobs(session, [payment.id])).get(payment.id)
    await tally_audit_service.record_review_audit(
        session,
        operation="PAYMENT_TALLY_UNLINK",
        actor_user_id=actor_user_id,
        payment_id=payment.id,
        before_status=payment_tally.TallyStatus.POSTED.value,
        after_status=payment_tally.derive_tally_status(payment, job).value,
        details={"tally_receipt_payment_id": str(receipt_id), "reason": reason},
    )
    await session.commit()
    return await PaymentRepository(session).get_by_id(payment_id)
