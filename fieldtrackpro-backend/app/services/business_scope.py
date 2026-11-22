"""
Business scope (release 3.1): FieldTrack holds the SGRG Distribution business only.

A debtor ledger is DISTRIBUTION, EXCLUDED or PENDING:
  1. a ledger-level MANUAL decision wins;
  2. otherwise the rule of its Tally group (tally_scope_groups);
  3. otherwise PENDING (unknown group / ambiguous ledger): hidden until an admin decides.

Out of scope (EXCLUDED / PENDING) means: the outlet is no longer a debtor in FieldTrack (customers.tally_is_debtor
= false, which every outlet / collection / ageing / account-position / reconciliation query already honours), and
the ledger's invoices, receipts and adjustments are RETIRED with reason OUT_OF_SCOPE / SCOPE_PENDING - never
deleted. Payment allocations and the voucher index are not touched, so a decision back to DISTRIBUTION restores
exactly the previous state, and reconciliation never re-sends those vouchers.

Enforcement is ON only while tally_scope_groups holds at least one rule (no rule = pre-3.1 behaviour).
Nothing here writes to Tally; the agent is unchanged.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.customer import Customer
from app.models.tally_debtor_ledger import (
    SCOPE_DISTRIBUTION,
    SCOPE_EXCLUDED,
    SCOPE_PENDING,
    SCOPE_SOURCE_DEFAULT,
    SCOPE_SOURCE_GROUP,
    SCOPE_SOURCE_MANUAL,
    TallyDebtorLedger,
)
from app.models.tally_scope_group import TallyScopeGroup

R_OUT_OF_SCOPE = "OUT_OF_SCOPE"
R_SCOPE_PENDING = "SCOPE_PENDING"
SCOPE_REASONS = (R_OUT_OF_SCOPE, R_SCOPE_PENDING)
SCOPES = (SCOPE_DISTRIBUTION, SCOPE_EXCLUDED, SCOPE_PENDING)
_RULES_KEY = "business_scope_rules"
_ZERO = {"invoices": 0, "payments": 0, "adjustments": 0}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def retire_reason(scope: str) -> str:
    return R_OUT_OF_SCOPE if scope == SCOPE_EXCLUDED else R_SCOPE_PENDING


async def load_rules(session: AsyncSession, refresh: bool = False) -> dict[str, str]:
    """{group name (lower-case) -> scope}; cached on the session for one request / batch."""
    if not refresh and _RULES_KEY in session.info:
        return session.info[_RULES_KEY]
    rows = (await session.execute(select(TallyScopeGroup.group_name, TallyScopeGroup.scope))).all()
    rules = {(g or "").strip().lower(): s for g, s in rows}
    session.info[_RULES_KEY] = rules
    return rules


def forget_rules(session: AsyncSession) -> None:
    session.info.pop(_RULES_KEY, None)


def decide(led: TallyDebtorLedger, rules: dict[str, str]) -> tuple[str, str, str]:
    """(scope, source, reason) for one ledger under the current rules."""
    if led.scope_source == SCOPE_SOURCE_MANUAL and led.business_scope in SCOPES:
        return led.business_scope, SCOPE_SOURCE_MANUAL, led.scope_reason or "manual decision"
    group = (led.parent_group or "").strip()
    rule = rules.get(group.lower())
    if rule in (SCOPE_DISTRIBUTION, SCOPE_EXCLUDED):
        return rule, SCOPE_SOURCE_GROUP, f"Tally group '{group}' is {rule}"
    return SCOPE_PENDING, SCOPE_SOURCE_DEFAULT, f"no scope rule for Tally group '{group or '(none)'}'"


async def _retire_live(session: AsyncSession, ledger_id, reason: str, now: datetime) -> dict:
    """Retire every LIVE Tally row of one ledger. MANUAL (field-collected) payments are never touched."""
    p = {"l": ledger_id, "r": reason, "now": now}
    return {
        "invoices": (await session.execute(text(
            "UPDATE invoices SET source = 'TALLY_RETIRED', tally_retired_at = :now, tally_retired_reason = :r "
            "WHERE tally_debtor_ledger_id = :l AND source = 'TALLY'"), p)).rowcount or 0,
        "payments": (await session.execute(text(
            "UPDATE payments SET source = 'TALLY_RETIRED', tally_retired_at = :now, tally_retired_reason = :r "
            "WHERE tally_debtor_ledger_id = :l AND source = 'TALLY'"), p)).rowcount or 0,
        "adjustments": (await session.execute(text(
            "UPDATE tally_ledger_adjustments SET state = 'RETIRED', retired_at = :now, retired_reason = :r "
            "WHERE tally_debtor_ledger_id = :l AND state = 'ACTIVE'"), p)).rowcount or 0,
    }


async def _relabel_scope_retired(session: AsyncSession, ledger_id, reason: str) -> None:
    p = {"l": ledger_id, "r": reason, "a": R_OUT_OF_SCOPE, "b": R_SCOPE_PENDING}
    await session.execute(text(
        "UPDATE invoices SET tally_retired_reason = :r WHERE tally_debtor_ledger_id = :l AND source = 'TALLY_RETIRED' "
        "AND tally_retired_reason IN (:a, :b) AND tally_retired_reason <> :r"), p)
    await session.execute(text(
        "UPDATE payments SET tally_retired_reason = :r WHERE tally_debtor_ledger_id = :l AND source = 'TALLY_RETIRED' "
        "AND tally_retired_reason IN (:a, :b) AND tally_retired_reason <> :r"), p)
    await session.execute(text(
        "UPDATE tally_ledger_adjustments SET retired_reason = :r WHERE tally_debtor_ledger_id = :l AND state = 'RETIRED' "
        "AND retired_reason IN (:a, :b) AND retired_reason <> :r"), p)


async def _restore_scope_retired(session: AsyncSession, ledger_id) -> dict:
    """Only rows retired for business scope come back (rows retired as deleted / reclassified in Tally stay)."""
    p = {"l": ledger_id, "a": R_OUT_OF_SCOPE, "b": R_SCOPE_PENDING}
    return {
        "invoices": (await session.execute(text(
            "UPDATE invoices SET source = 'TALLY', tally_retired_at = NULL, tally_retired_reason = NULL "
            "WHERE tally_debtor_ledger_id = :l AND source = 'TALLY_RETIRED' AND tally_retired_reason IN (:a, :b)"),
            p)).rowcount or 0,
        "payments": (await session.execute(text(
            "UPDATE payments SET source = 'TALLY', tally_retired_at = NULL, tally_retired_reason = NULL "
            "WHERE tally_debtor_ledger_id = :l AND source = 'TALLY_RETIRED' AND tally_retired_reason IN (:a, :b)"),
            p)).rowcount or 0,
        "adjustments": (await session.execute(text(
            "UPDATE tally_ledger_adjustments SET state = 'ACTIVE', retired_at = NULL, retired_reason = NULL "
            "WHERE tally_debtor_ledger_id = :l AND state = 'RETIRED' AND retired_reason IN (:a, :b)"),
            p)).rowcount or 0,
    }


async def refresh_customer_flag(session: AsyncSession, cust: Customer) -> None:
    """An outlet is a FieldTrack debtor only while at least one of its ledgers is a debtor AND in scope."""
    rows = (await session.execute(
        select(TallyDebtorLedger.is_debtor, TallyDebtorLedger.business_scope)
        .where(TallyDebtorLedger.customer_id == cust.id)
    )).all()
    if not rows:
        return
    if any(d and (s in (None, SCOPE_DISTRIBUTION)) for d, s in rows):
        cust.tally_is_debtor = True
    elif any(d for d, _ in rows) or all(d is False for d, _ in rows):
        cust.tally_is_debtor = False


async def transition(session: AsyncSession, led: TallyDebtorLedger, scope: str, source: str, reason: str,
                     now: Optional[datetime] = None, actor_id=None) -> dict:
    """Set the ledger's scope and bring its rows in line with it (idempotent, based on the rows' actual state)."""
    now = now or _now()
    changed = (led.business_scope, led.scope_source) != (scope, source)
    led.business_scope, led.scope_source, led.scope_reason = scope, source, (reason or "")[:300]
    if changed or led.scope_decided_at is None:
        led.scope_decided_at = now
        if actor_id is not None:
            led.scope_decided_by = actor_id
    if scope == SCOPE_DISTRIBUTION:
        moved = await _restore_scope_retired(session, led.id)
    else:
        moved = await _retire_live(session, led.id, retire_reason(scope), now)
        await _relabel_scope_retired(session, led.id, retire_reason(scope))
    await session.flush()
    cust = await session.get(Customer, led.customer_id)
    if cust is not None:
        await refresh_customer_flag(session, cust)
    return {"changed": changed, "scope": scope, "source": source, "reason": reason, **moved}


async def apply_ledger_scope(session: AsyncSession, led: TallyDebtorLedger, now: Optional[datetime] = None,
                             rules: Optional[dict] = None, force: bool = False) -> dict:
    """Sync hook: evaluate one debtor ledger. No-op while enforcement is off (no rules) or for a non-debtor.
    Without `force`, rows are only touched when the decision changes."""
    rules = rules if rules is not None else await load_rules(session)
    if not rules or led.is_debtor is not True:
        return {"changed": False, **_ZERO}
    scope, source, reason = decide(led, rules)
    if not force and (led.business_scope, led.scope_source) == (scope, source):
        led.scope_reason = reason[:300]
        cust = await session.get(Customer, led.customer_id)
        if cust is not None:  # the caller may just have set tally_is_debtor = True
            await refresh_customer_flag(session, cust)
        return {"changed": False, "scope": scope, **_ZERO}
    return await transition(session, led, scope, source, reason, now)


async def set_manual_scope(session: AsyncSession, led: TallyDebtorLedger, scope: Optional[str], reason: str,
                           actor_id=None) -> dict:
    """Admin decision for one ledger (MANUAL); scope=None drops the manual decision (back to the group rule)."""
    if scope is not None and scope not in SCOPES:
        raise ValueError(f"unknown scope {scope!r}")
    if scope is None:
        led.scope_source = None
        rules = await load_rules(session)
        s, src, why = decide(led, rules) if rules else (SCOPE_DISTRIBUTION, SCOPE_SOURCE_DEFAULT, "no scope rules")
        return await transition(session, led, s, src, why, actor_id=actor_id)
    return await transition(session, led, scope, SCOPE_SOURCE_MANUAL, reason or "manual decision", actor_id=actor_id)


async def retire_out_of_scope_row(session: AsyncSession, led: Optional[TallyDebtorLedger], kind: str, key: str,
                                  now: datetime) -> bool:
    """A voucher line just upserted on an out-of-scope ledger is stored retired (its content stays up to date)."""
    if led is None or led.in_scope:
        return False
    p = {"now": now, "r": retire_reason(led.business_scope), "k": key}
    if kind == "INVOICE":
        sql = ("UPDATE invoices SET source = 'TALLY_RETIRED', tally_retired_at = :now, tally_retired_reason = :r "
               "WHERE source_reference = :k AND source = 'TALLY'")
    elif kind == "PAYMENT":
        sql = ("UPDATE payments SET source = 'TALLY_RETIRED', tally_retired_at = :now, tally_retired_reason = :r "
               "WHERE source_reference = :k AND source = 'TALLY'")
    else:
        sql = ("UPDATE tally_ledger_adjustments SET state = 'RETIRED', retired_at = :now, retired_reason = :r "
               "WHERE source_reference = :k AND state = 'ACTIVE'")
    return bool((await session.execute(text(sql), p)).rowcount)


async def excluded_summary(session: AsyncSession) -> list[dict]:
    """Per scope (EXCLUDED / PENDING): ledgers, Tally receivable (-closing), open bills, rows retired for scope."""
    rows = (await session.execute(text("""
        WITH lb AS (SELECT MAX(as_of_date) d FROM tally_open_bills),
        l AS (SELECT d.id, d.business_scope s, -COALESCE(d.closing_balance, 0) recv
                FROM tally_debtor_ledgers d WHERE d.is_debtor IS TRUE AND d.business_scope IN ('EXCLUDED','PENDING'))
        SELECT l.s AS scope, COUNT(*) AS ledgers, COALESCE(SUM(l.recv), 0) AS receivable,
               COALESCE(SUM((SELECT SUM(b.pending_amount) FROM tally_open_bills b, lb
                              WHERE b.tally_debtor_ledger_id = l.id AND b.as_of_date = lb.d)), 0) AS open_bills,
               COALESCE(SUM((SELECT COUNT(*) FROM invoices i WHERE i.tally_debtor_ledger_id = l.id
                              AND i.tally_retired_reason IN ('OUT_OF_SCOPE','SCOPE_PENDING'))), 0) AS invoices,
               COALESCE(SUM((SELECT COUNT(*) FROM payments p WHERE p.tally_debtor_ledger_id = l.id
                              AND p.tally_retired_reason IN ('OUT_OF_SCOPE','SCOPE_PENDING'))), 0) AS payments,
               COALESCE(SUM((SELECT COUNT(*) FROM tally_ledger_adjustments a WHERE a.tally_debtor_ledger_id = l.id
                              AND a.retired_reason IN ('OUT_OF_SCOPE','SCOPE_PENDING'))), 0) AS adjustments
          FROM l GROUP BY l.s ORDER BY l.s
    """))).mappings().all()
    return [{"scope": r["scope"], "ledgers": r["ledgers"], "receivable": str(r["receivable"]),
             "open_bills": str(r["open_bills"]), "invoices_retired": int(r["invoices"]),
             "receipts_retired": int(r["payments"]), "adjustments_retired": int(r["adjustments"])} for r in rows]
