"""
Monthly Period Lifecycle & Financial Lock Service.
Handles automatic IST month rollover, period reviews, financial transaction locking,
and audited Admin finalization/reopening.
"""
from __future__ import annotations

import logging
import uuid
from calendar import monthrange
from datetime import date, datetime, time, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import get_current_request_id
from app.exceptions.custom import BaseAPIException
from app.models.customer import Customer
from app.models.invoice import Invoice
from app.models.monthly_reporting_period import MonthlyPeriodStatus, MonthlyReportingPeriod
from app.models.outlet_financial_snapshot import OutletFinancialSnapshot
from app.models.payment import Payment, PaymentStatus
from app.models.visit import Visit, VisitStatus, VisitType
from app.schemas.financial_snapshot import MonthlyPeriodRead, MonthlyPeriodReviewSummary

logger = logging.getLogger("fieldtrackpro")

MONTH_NAMES = [
    "", "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December"
]
IST_TZ = ZoneInfo("Asia/Kolkata")


def get_current_ist_year_month() -> tuple[int, int, date]:
    """Returns current year, month, and date in Indian Standard Time (IST)."""
    ist_now = datetime.now(IST_TZ)
    return ist_now.year, ist_now.month, ist_now.date()


async def ensure_monthly_periods_synced(session: AsyncSession) -> list[MonthlyReportingPeriod]:
    """
    Idempotently ensures that:
    1. Current IST month exists as an active OPEN period.
    2. Any past unclosed periods transition to PENDING_CLOSE state so Admin can review and close them.
    3. MonthlyReportingPeriod exists for any historical snapshot data.
    """
    req_id = get_current_request_id()
    cur_year, cur_month, _ = get_current_ist_year_month()
    now_dt = datetime.now(timezone.utc)

    # 1. Fetch distinct snapshot months
    snap_stmt = select(
        func.extract("year", OutletFinancialSnapshot.snapshot_date).label("s_year"),
        func.extract("month", OutletFinancialSnapshot.snapshot_date).label("s_month"),
        func.count(OutletFinancialSnapshot.id).label("snap_cnt"),
        func.count(func.distinct(OutletFinancialSnapshot.customer_id)).label("outlets_cnt"),
        func.sum(OutletFinancialSnapshot.sales).label("s_sales"),
        func.sum(OutletFinancialSnapshot.collection).label("s_collection"),
        func.sum(OutletFinancialSnapshot.market_outstanding).label("s_os"),
        func.sum(OutletFinancialSnapshot.bucket_gt_90).label("s_gt90"),
    ).group_by(
        func.extract("year", OutletFinancialSnapshot.snapshot_date),
        func.extract("month", OutletFinancialSnapshot.snapshot_date),
    )
    snap_res = await session.execute(snap_stmt)
    snap_months = {
        (int(r.s_year), int(r.s_month)): r for r in snap_res.all()
    }

    # 2. Fetch all existing periods
    existing_res = await session.execute(select(MonthlyReportingPeriod))
    existing_periods = {
        (p.period_year, p.period_month): p for p in existing_res.scalars().all()
    }

    # 3. Ensure current month exists
    if (cur_year, cur_month) not in existing_periods:
        cur_snap = snap_months.get((cur_year, cur_month))
        cur_period = MonthlyReportingPeriod(
            period_year=cur_year,
            period_month=cur_month,
            period_name=f"{MONTH_NAMES[cur_month]} {cur_year}",
            status=MonthlyPeriodStatus.OPEN,
            opened_at=now_dt,
            snapshot_count=cur_snap.snap_cnt if cur_snap else 0,
            total_outlets=cur_snap.outlets_cnt if cur_snap else 0,
            total_sales=cur_snap.s_sales if cur_snap and cur_snap.s_sales else Decimal("0.00"),
            total_collection=cur_snap.s_collection if cur_snap and cur_snap.s_collection else Decimal("0.00"),
            total_market_os=cur_snap.s_os if cur_snap and cur_snap.s_os else Decimal("0.00"),
            total_overdue_gt_90=cur_snap.s_gt90 if cur_snap and cur_snap.s_gt90 else Decimal("0.00"),
        )
        session.add(cur_period)
        existing_periods[(cur_year, cur_month)] = cur_period
        logger.info(
            "event=monthly_period_created request_id=%s year=%s month=%s period_name='%s' status=OPEN",
            req_id,
            cur_year,
            cur_month,
            cur_period.period_name,
        )

    # 4. Sync historical snapshot months and update past OPEN months to PENDING_CLOSE
    for (y, m), snap_r in snap_months.items():
        if (y, m) not in existing_periods:
            is_past = (y < cur_year) or (y == cur_year and m < cur_month)
            init_status = MonthlyPeriodStatus.PENDING_CLOSE if is_past else MonthlyPeriodStatus.OPEN
            p_obj = MonthlyReportingPeriod(
                period_year=y,
                period_month=m,
                period_name=f"{MONTH_NAMES[m]} {y}",
                status=init_status,
                opened_at=now_dt,
                snapshot_count=snap_r.snap_cnt or 0,
                total_outlets=snap_r.outlets_cnt or 0,
                total_sales=snap_r.s_sales or Decimal("0.00"),
                total_collection=snap_r.s_collection or Decimal("0.00"),
                total_market_os=snap_r.s_os or Decimal("0.00"),
                total_overdue_gt_90=snap_r.s_gt90 or Decimal("0.00"),
            )
            session.add(p_obj)
            existing_periods[(y, m)] = p_obj
            logger.info(
                "event=monthly_period_created request_id=%s year=%s month=%s period_name='%s' status=%s",
                req_id,
                y,
                m,
                p_obj.period_name,
                init_status.value,
            )

    # 5. Check all existing periods for rollover transition (OPEN past months -> PENDING_CLOSE)
    for (y, m), period in existing_periods.items():
        is_past = (y < cur_year) or (y == cur_year and m < cur_month)
        if is_past and period.status == MonthlyPeriodStatus.OPEN:
            period.status = MonthlyPeriodStatus.PENDING_CLOSE
            period.updated_at = now_dt
            logger.info(
                "event=monthly_period_pending_close request_id=%s period_id=%s period_name='%s'",
                req_id,
                period.id,
                period.period_name,
            )

        # Update snapshot counts for non-finalized periods
        if period.status != MonthlyPeriodStatus.FINALIZED and (y, m) in snap_months:
            snap_r = snap_months[(y, m)]
            period.snapshot_count = snap_r.snap_cnt or 0
            period.total_outlets = snap_r.outlets_cnt or 0
            period.total_sales = snap_r.s_sales or Decimal("0.00")
            period.total_collection = snap_r.s_collection or Decimal("0.00")
            period.total_market_os = snap_r.s_os or Decimal("0.00")
            period.total_overdue_gt_90 = snap_r.s_gt90 or Decimal("0.00")

    await session.commit()

    # Return sorted descending
    all_periods_stmt = select(MonthlyReportingPeriod).order_by(
        MonthlyReportingPeriod.period_year.desc(),
        MonthlyReportingPeriod.period_month.desc(),
    )
    res = await session.execute(all_periods_stmt)
    return list(res.scalars().all())


async def assert_period_open_for_date(target_date: date, session: AsyncSession) -> None:
    """
    Authoritative backend financial lock enforcement.
    Blocks creating backdated transactions (payments, invoices, adjustments) into a FINALIZED period.
    """
    req_id = get_current_request_id()
    y = target_date.year
    m = target_date.month

    stmt = select(MonthlyReportingPeriod).where(
        MonthlyReportingPeriod.period_year == y,
        MonthlyReportingPeriod.period_month == m,
    )
    res = await session.execute(stmt)
    period = res.scalar_one_or_none()

    if period and period.status == MonthlyPeriodStatus.FINALIZED:
        logger.warning(
            "event=period_locked_transaction_rejected request_id=%s target_date=%s period='%s'",
            req_id,
            target_date.isoformat(),
            period.period_name,
        )
        raise BaseAPIException(
            status_code=409,
            detail=f"{period.period_name} is closed for accounting. This transaction cannot be recorded in the closed period.",
            error_code="PERIOD_LOCKED",
        )


async def get_monthly_period_review(period_id: uuid.UUID, session: AsyncSession) -> MonthlyPeriodReviewSummary:
    """
    Aggregates comprehensive operational & financial metrics for period close review.
    """
    stmt = select(MonthlyReportingPeriod).where(MonthlyReportingPeriod.id == period_id)
    res = await session.execute(stmt)
    period = res.scalar_one_or_none()
    if not period:
        raise BaseAPIException(status_code=404, detail="Monthly period not found", error_code="PERIOD_NOT_FOUND")

    y = period.period_year
    m = period.period_month
    _, last_day = monthrange(y, m)
    start_dt = datetime(y, m, 1, 0, 0, 0, tzinfo=timezone.utc)
    end_dt = datetime(y, m, last_day, 23, 59, 59, tzinfo=timezone.utc)
    start_date = date(y, m, 1)
    end_date = date(y, m, last_day)

    # 1. Visits metrics
    v_stmt = select(
        func.count(Visit.id).label("total"),
        func.count(Visit.id).filter(Visit.status == VisitStatus.COMPLETED).label("completed"),
        func.count(Visit.id).filter(Visit.visit_type == VisitType.AD_HOC).label("adhoc"),
    ).where(
        Visit.scheduled_at >= start_dt,
        Visit.scheduled_at <= end_dt,
    )
    v_res = await session.execute(v_stmt)
    v_row = v_res.one()

    # 2. Collections metrics
    p_stmt = select(
        func.count(Payment.id).label("total_cnt"),
        func.coalesce(func.sum(Payment.amount), Decimal("0.00")).label("total_amt"),
        func.coalesce(
            func.sum(Payment.amount).filter(Payment.status == PaymentStatus.VERIFIED),
            Decimal("0.00"),
        ).label("verified_amt"),
        func.coalesce(
            func.sum(Payment.amount).filter(Payment.status == PaymentStatus.PENDING_VERIFICATION),
            Decimal("0.00"),
        ).label("pending_amt"),
    ).where(
        Payment.payment_date >= start_date,
        Payment.payment_date <= end_date,
    )
    p_res = await session.execute(p_stmt)
    p_row = p_res.one()

    # 3. Invoices count
    inv_stmt = select(func.count(Invoice.id)).where(
        Invoice.invoice_date >= start_date,
        Invoice.invoice_date <= end_date,
    )
    inv_cnt = (await session.execute(inv_stmt)).scalar() or 0

    # 4. Outlets count
    snap_outlets_stmt = select(func.count(func.distinct(OutletFinancialSnapshot.customer_id))).where(
        func.extract("year", OutletFinancialSnapshot.snapshot_date) == y,
        func.extract("month", OutletFinancialSnapshot.snapshot_date) == m,
    )
    outlets_cnt = (await session.execute(snap_outlets_stmt)).scalar() or period.total_outlets

    status_str = period.status.value if hasattr(period.status, "value") else str(period.status)
    can_finalize = (status_str != "FINALIZED")

    return MonthlyPeriodReviewSummary(
        period_id=period.id,
        period_year=y,
        period_month=m,
        period_name=period.period_name,
        status=status_str,
        visits_completed=v_row.completed or 0,
        visits_adhoc=v_row.adhoc or 0,
        visits_total=v_row.total or 0,
        collections_submitted_amount=p_row.total_amt,
        collections_verified_amount=p_row.verified_amt,
        collections_pending_amount=p_row.pending_amt,
        collections_count=p_row.total_cnt or 0,
        total_outstanding=period.total_market_os,
        total_invoices_count=inv_cnt,
        total_outlets_count=outlets_cnt or 0,
        can_finalize=can_finalize,
    )


async def finalize_monthly_period(
    period_id: uuid.UUID,
    user_id: uuid.UUID,
    session: AsyncSession,
) -> MonthlyPeriodRead:
    """
    Finalizes and locks a monthly reporting period.
    """
    req_id = get_current_request_id()
    stmt = select(MonthlyReportingPeriod).where(MonthlyReportingPeriod.id == period_id)
    res = await session.execute(stmt)
    period = res.scalar_one_or_none()
    if not period:
        raise BaseAPIException(status_code=404, detail="Monthly period not found", error_code="PERIOD_NOT_FOUND")

    now_dt = datetime.now(timezone.utc)
    period.status = MonthlyPeriodStatus.FINALIZED
    period.finalized_at = now_dt
    period.finalized_by = user_id
    period.updated_at = now_dt
    await session.commit()

    logger.info(
        "event=monthly_period_finalized request_id=%s period_id=%s period_name='%s' user_id=%s",
        req_id,
        period.id,
        period.period_name,
        user_id,
    )

    return MonthlyPeriodRead(
        id=period.id,
        period_year=period.period_year,
        period_month=period.period_month,
        period_name=period.period_name,
        status="FINALIZED",
        snapshot_count=period.snapshot_count,
        total_outlets=period.total_outlets,
        total_sales=period.total_sales,
        total_collection=period.total_collection,
        total_market_os=period.total_market_os,
        total_overdue_gt_90=period.total_overdue_gt_90,
        opened_at=period.opened_at,
        finalized_at=now_dt,
        finalized_by=user_id,
        reopened_at=period.reopened_at,
        reopened_by=period.reopened_by,
        reopen_reason=period.reopen_reason,
        created_at=period.created_at or now_dt,
        updated_at=now_dt,
    )


async def reopen_monthly_period(
    period_id: uuid.UUID,
    user_id: uuid.UUID,
    reason: str,
    session: AsyncSession,
) -> MonthlyPeriodRead:
    """
    Reopens a finalized monthly reporting period with mandatory reason tracking.
    """
    req_id = get_current_request_id()
    clean_reason = (reason or "").strip()
    if not clean_reason:
        raise BaseAPIException(
            status_code=422,
            detail="A non-empty reason is required to reopen a locked accounting period.",
            error_code="REOPEN_REASON_REQUIRED",
        )

    stmt = select(MonthlyReportingPeriod).where(MonthlyReportingPeriod.id == period_id)
    res = await session.execute(stmt)
    period = res.scalar_one_or_none()
    if not period:
        raise BaseAPIException(status_code=404, detail="Monthly period not found", error_code="PERIOD_NOT_FOUND")

    cur_year, cur_month, _ = get_current_ist_year_month()
    is_current = (period.period_year == cur_year and period.period_month == cur_month)
    target_status = MonthlyPeriodStatus.OPEN if is_current else MonthlyPeriodStatus.PENDING_CLOSE

    now_dt = datetime.now(timezone.utc)
    period.status = target_status
    period.finalized_at = None
    period.finalized_by = None
    period.reopened_at = now_dt
    period.reopened_by = user_id
    period.reopen_reason = clean_reason
    period.updated_at = now_dt
    await session.commit()

    logger.info(
        "event=monthly_period_reopened request_id=%s period_id=%s period_name='%s' user_id=%s reason='%s'",
        req_id,
        period.id,
        period.period_name,
        user_id,
        clean_reason,
    )

    return MonthlyPeriodRead(
        id=period.id,
        period_year=period.period_year,
        period_month=period.period_month,
        period_name=period.period_name,
        status=target_status.value,
        snapshot_count=period.snapshot_count,
        total_outlets=period.total_outlets,
        total_sales=period.total_sales,
        total_collection=period.total_collection,
        total_market_os=period.total_market_os,
        total_overdue_gt_90=period.total_overdue_gt_90,
        opened_at=period.opened_at,
        finalized_at=None,
        finalized_by=None,
        reopened_at=now_dt,
        reopened_by=user_id,
        reopen_reason=clean_reason,
        created_at=period.created_at or now_dt,
        updated_at=now_dt,
    )
