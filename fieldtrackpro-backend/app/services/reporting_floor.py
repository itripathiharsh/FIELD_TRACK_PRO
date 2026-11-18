"""
Release 2.2.0 - the reporting floor: the first day of the LIVE financial year.

Tally rows dated before it are HISTORY (FY 2025-26 and earlier, imported only on explicit approval).
Live screens - collections overview, outlet account summary, BI without an explicit window, monthly
reporting periods - only count rows on or after the floor, so a historical import can never:
  * create pending-close reporting periods for past years (B1),
  * show long-paid historical invoices as outstanding / >90 days, or mix them into live totals (B4).
Live outstanding, reconciliation and positions were already anchored on each ledger's
opening_balance_as_of (account_position `since_ok`) and are unaffected.
History stays visible where it belongs: the outlet's account history (a statement) and any report
asked for an explicit date window that reaches back.

Config: TALLY_REPORTING_FLOOR (YYYY-MM-DD), default 2026-04-01 = the agent's SYNC_FROM_DATE. It moves only
with the year-end procedure, together with the agent's SYNC_FROM_DATE.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Optional

from sqlalchemy import or_

from app.config import settings


def reporting_floor() -> date:
    return date.fromisoformat(str(settings.tally_reporting_floor))


def effective_start(start: Optional[date]) -> date:
    """An explicit window start is honoured (it may reach into history); no start means the live FY."""
    return start if start is not None else reporting_floor()


def live_invoice_clause(model: Any):
    """Tally invoices on/after the floor; non-Tally invoices are never historical imports."""
    from app.models.invoice import InvoiceSource
    return or_(model.source.notin_((InvoiceSource.TALLY, InvoiceSource.TALLY_RETIRED)), model.invoice_date >= reporting_floor())


def live_payment_clause(model: Any):
    """Tally receipts on/after the floor; field collections are always live."""
    from app.models.payment import PaymentSource
    return or_(model.source.notin_((PaymentSource.TALLY, PaymentSource.TALLY_RETIRED)), model.payment_date >= reporting_floor())


def is_live_invoice(inv: Any) -> bool:
    from app.models.invoice import InvoiceSource
    return (inv.source not in (InvoiceSource.TALLY, InvoiceSource.TALLY_RETIRED) or inv.invoice_date is None
            or inv.invoice_date >= reporting_floor())


def is_live_payment(p: Any) -> bool:
    from app.models.payment import PaymentSource
    return (p.source not in (PaymentSource.TALLY, PaymentSource.TALLY_RETIRED) or p.payment_date is None
            or p.payment_date >= reporting_floor())
