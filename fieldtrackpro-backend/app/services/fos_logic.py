"""
Pure (database-free) rules of the Tally FOS synchronisation, so they can be unit-tested and reused by the
reconciliation script on exported data.

Vocabulary
  group    a Tally ledger group that holds outlet ledgers ("Raunak Usha", "Sahil Gautam (Usha)", "Sundry Debtors")
  mapping  what an admin decided a group means: an employee (MAPPED), NOT_FOS, or nothing yet (UNMAPPED)
  outlet   a FieldTrack customer, with one or more in-scope Tally debtor ledgers, each sitting in a group

Rules (plan_outlet)
  * No in-scope Tally ledger          -> NO_TALLY, nothing is touched (e.g. an employee's own prospect outlet).
  * Any ledger in an UNMAPPED group   -> UNMAPPED_GROUP, nothing is touched (existing access is never dropped
                                         because of something FieldTrack does not understand yet).
  * Otherwise the wanted FOS set is the employees of the MAPPED groups of its ledgers (NOT_FOS groups add nobody).
      - rows the sync owns (source TALLY) that are no longer wanted are removed; wanted ones are added.
      - rows from before the sync (LEGACY / APP): the same employee is ADOPTED (relabelled, access unchanged);
        a different employee is a CONFLICT -> the outlet is left completely untouched (REPORT_ONLY) or replaced
        (TALLY_WINS).
  * Nothing wanted and nothing conflicting -> UNASSIGNED (Tally has no FOS for it): the sync's own rows are removed.
"""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Iterable, Optional

from app.models.tally_fos import (
    GROUP_MAPPED, GROUP_NOT_FOS, GROUP_UNMAPPED, SRC_TALLY,
    ST_ASSIGNED, ST_CONFLICT, ST_MULTIPLE, ST_NO_TALLY, ST_UNASSIGNED, ST_UNMAPPED_GROUP,
)

POLICY_REPORT_ONLY = "REPORT_ONLY"
POLICY_TALLY_WINS = "TALLY_WINS"

# Words in this client's group names that are brands / qualifiers, never part of the person's name.
_QUALIFIERS = {
    "usha", "zbr", "zebronics", "vu", "rr", "singer", "oppo", "sir", "ph", "ji", "ce", "mobile", "sgrg",
    "sundry", "debtors", "debtor", "creditors", "creditor", "2.0", "uk",
}
_GENERIC = {"debtors", "debtor", "creditors", "creditor", "expenses", "income", "incomes", "assets", "accounts"}


def normalize_group_key(name: Optional[str]) -> str:
    """Case / whitespace-insensitive identity of a Tally group name (Tally pads names with double spaces)."""
    return " ".join((name or "").lower().split())[:150]


def person_tokens(group_name: str) -> list[str]:
    """The name part of a group name: 'Sahil Gautam (Usha)' -> ['sahil', 'gautam']; 'Sundry Debtors ZBR' -> []."""
    text = re.sub(r"\([^)]*\)", " ", (group_name or "").lower())
    tokens = [t for t in re.split(r"[^a-z0-9.]+", text) if t]
    if any(t in _GENERIC for t in tokens):
        return []
    return [t for t in tokens if t not in _QUALIFIERS]


def _name_tokens(full_name: str) -> list[str]:
    return [t for t in re.split(r"[^a-z0-9]+", (full_name or "").lower()) if t]


def suggest_employee(group_name: str, employees: Iterable[tuple[uuid.UUID, str]]) -> tuple[Optional[uuid.UUID], Optional[str]]:
    """
    A SUGGESTION for the admin, never applied by itself. Returns (employee_id, basis) only when exactly one
    employee fits: same first name (exact), else a first name that differs by at most a letter or two
    ("Dharmendra" / "Dharmendar"). Two employees sharing a first name, or no fit, give no suggestion.
    """
    gt = person_tokens(group_name)
    if not gt:
        return None, None
    first = gt[0]
    emps = [(eid, _name_tokens(name)) for eid, name in employees]
    exact = [eid for eid, nt in emps if nt and nt[0] == first]
    if len(exact) == 1:
        return exact[0], f"first name '{first}' matches exactly"
    if len(exact) > 1:
        return None, None
    fuzzy = [eid for eid, nt in emps if nt and len(first) >= 4 and SequenceMatcher(None, nt[0], first).ratio() >= 0.85]
    if len(fuzzy) == 1:
        return fuzzy[0], f"first name '{first}' is close to the employee's name (spelling difference)"
    return None, None


@dataclass(frozen=True)
class LedgerRef:
    guid: str
    group_name: str


@dataclass(frozen=True)
class GroupRule:
    status: str                       # MAPPED | NOT_FOS | UNMAPPED
    employee_id: Optional[uuid.UUID] = None


@dataclass(frozen=True)
class CurrentRow:
    id: uuid.UUID
    employee_id: uuid.UUID
    source: str


@dataclass
class Change:
    kind: str                         # ASSIGNED | REMOVED | ADOPTED | REPLACED_LEGACY
    employee_id: uuid.UUID
    row_id: Optional[uuid.UUID] = None
    group_name: Optional[str] = None
    ledger_guid: Optional[str] = None
    detail: Optional[str] = None


@dataclass
class OutletPlan:
    status: str
    changes: list[Change] = field(default_factory=list)
    wanted: dict = field(default_factory=dict)          # employee_id -> (group_name, ledger_guid)
    conflicts: list[CurrentRow] = field(default_factory=list)
    unmapped_groups: list[str] = field(default_factory=list)
    not_fos_groups: list[str] = field(default_factory=list)


def plan_outlet(
    ledgers: list[LedgerRef],
    rules: dict[str, GroupRule],
    current: list[CurrentRow],
    legacy_policy: str = POLICY_REPORT_ONLY,
) -> OutletPlan:
    if not ledgers:
        return OutletPlan(status=ST_NO_TALLY)

    wanted: dict = {}
    unmapped: list[str] = []
    not_fos: list[str] = []
    for led in ledgers:
        rule = rules.get(normalize_group_key(led.group_name))
        if rule is None or rule.status == GROUP_UNMAPPED:
            unmapped.append(led.group_name)
        elif rule.status == GROUP_MAPPED and rule.employee_id is not None:
            wanted.setdefault(rule.employee_id, (led.group_name, led.guid))
        else:
            not_fos.append(led.group_name)
    if unmapped:
        return OutletPlan(status=ST_UNMAPPED_GROUP, wanted=wanted, unmapped_groups=sorted(set(unmapped)),
                          not_fos_groups=sorted(set(not_fos)))

    owned = [r for r in current if r.source == SRC_TALLY]
    prior = [r for r in current if r.source != SRC_TALLY]
    conflicts = [r for r in prior if r.employee_id not in wanted]
    if conflicts and legacy_policy != POLICY_TALLY_WINS:
        return OutletPlan(status=ST_CONFLICT, wanted=wanted, conflicts=conflicts, not_fos_groups=sorted(set(not_fos)))

    changes: list[Change] = []
    have = set()
    for r in owned:
        if r.employee_id in wanted:
            have.add(r.employee_id)
        else:
            changes.append(Change("REMOVED", r.employee_id, r.id, detail="no longer in this FOS's Tally group"))
    for r in prior:
        if r.employee_id in wanted:
            g, guid = wanted[r.employee_id]
            changes.append(Change("ADOPTED", r.employee_id, r.id, g, guid, "matches Tally: now managed by the sync"))
            have.add(r.employee_id)
        else:  # TALLY_WINS
            changes.append(Change("REPLACED_LEGACY", r.employee_id, r.id, detail="Tally has a different FOS"))
    for emp_id, (g, guid) in wanted.items():
        if emp_id not in have:
            changes.append(Change("ASSIGNED", emp_id, None, g, guid))

    status = ST_UNASSIGNED if not wanted else (ST_MULTIPLE if len(wanted) > 1 else ST_ASSIGNED)
    return OutletPlan(status=status, changes=changes, wanted=wanted, not_fos_groups=sorted(set(not_fos)))
