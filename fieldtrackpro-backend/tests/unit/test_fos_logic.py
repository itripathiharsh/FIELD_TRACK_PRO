"""Pure rules of the Tally FOS synchronisation (no database)."""
from __future__ import annotations

import uuid

import pytest

from app.models.tally_fos import (
    GROUP_MAPPED, GROUP_NOT_FOS, GROUP_UNMAPPED, SRC_APP, SRC_LEGACY, SRC_TALLY,
    ST_ASSIGNED, ST_CONFLICT, ST_MULTIPLE, ST_NO_TALLY, ST_UNASSIGNED, ST_UNMAPPED_GROUP,
)
from app.services import fos_logic as L

RAUNAK, SAHIL, YOGESH = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()


def key(name):
    return L.normalize_group_key(name)


def rules(**kw):
    return {key(k): v for k, v in kw.items()}


def led(group, guid="G1"):
    return L.LedgerRef(guid=guid, group_name=group)


def row(emp, source=SRC_TALLY):
    return L.CurrentRow(uuid.uuid4(), emp, source)


MAP = {"Raunak Usha": L.GroupRule(GROUP_MAPPED, RAUNAK), "Sahil Gautam (Usha)": L.GroupRule(GROUP_MAPPED, SAHIL),
       "Sundry Debtors- PH.": L.GroupRule(GROUP_NOT_FOS), "Mystery Group": L.GroupRule(GROUP_UNMAPPED)}


@pytest.fixture
def R():
    return rules(**MAP)


# ---- normalisation / suggestions --------------------------------------------------------------------------------

def test_group_key_ignores_case_and_padding():
    assert L.normalize_group_key("  Neeraj  (ZBR) ") == L.normalize_group_key("neeraj (zbr)")


@pytest.mark.parametrize("name,tokens", [
    ("Sahil Gautam (Usha)", ["sahil", "gautam"]), ("Raunak ZBR", ["raunak"]), ("JITENDRA SIR (VU)", ["jitendra"]),
    ("Neeraj  (ZBR)", ["neeraj"]), ("Sundry Debtors ZBR", []), ("Indirect Expenses", []), ("Sunil Kumar 2.0", ["sunil", "kumar"]),
])
def test_person_tokens(name, tokens):
    assert L.person_tokens(name) == tokens


EMPS = [(RAUNAK, "Raunak"), (SAHIL, "Sahil"), (YOGESH, "Yogesh"), (uuid.uuid4(), "Dharmendar")]


def test_suggest_exact_first_name():
    eid, basis = L.suggest_employee("Raunak Usha", EMPS)
    assert eid == RAUNAK and "exactly" in basis


def test_suggest_tolerates_spelling_difference():
    eid, basis = L.suggest_employee("Dharmendra (RR)", EMPS)
    assert eid == EMPS[3][0] and "spelling" in basis


def test_no_suggestion_for_generic_or_unknown_groups():
    assert L.suggest_employee("Sundry Debtors- PH.", EMPS) == (None, None)
    assert L.suggest_employee("Tejinder pal Singh", EMPS) == (None, None)


def test_two_employees_with_the_same_first_name_are_never_guessed():
    emps = EMPS + [(uuid.uuid4(), "Amit Jaiswal"), (uuid.uuid4(), "Amit Bagchi")]
    assert L.suggest_employee("Amit (VU)", emps) == (None, None)


def test_short_names_are_not_fuzzy_matched():
    assert L.suggest_employee("Ali ZBR", [(uuid.uuid4(), "Alok")]) == (None, None)


# ---- plan_outlet --------------------------------------------------------------------------------------------------

def test_no_tally_ledger_touches_nothing(R):
    p = L.plan_outlet([], R, [row(RAUNAK, SRC_APP)])
    assert p.status == ST_NO_TALLY and p.changes == []


def test_new_assignment_from_tally(R):
    p = L.plan_outlet([led("Raunak Usha")], R, [])
    assert p.status == ST_ASSIGNED
    assert [(c.kind, c.employee_id) for c in p.changes] == [("ASSIGNED", RAUNAK)]


def test_group_name_spelling_padding_resolves_to_the_same_mapping(R):
    p = L.plan_outlet([led("RAUNAK  usha")], R, [])
    assert p.status == ST_ASSIGNED and p.changes[0].employee_id == RAUNAK


def test_idempotent_when_already_synced(R):
    p = L.plan_outlet([led("Raunak Usha")], R, [row(RAUNAK)])
    assert p.status == ST_ASSIGNED and p.changes == []


def test_fos_changed_in_tally_replaces_the_synced_assignment(R):
    old = row(SAHIL)
    p = L.plan_outlet([led("Raunak Usha")], R, [old])
    kinds = {(c.kind, c.employee_id) for c in p.changes}
    assert kinds == {("REMOVED", SAHIL), ("ASSIGNED", RAUNAK)}


def test_blank_fos_in_tally_removes_the_synced_assignment(R):
    p = L.plan_outlet([led("Sundry Debtors- PH.")], R, [row(RAUNAK)])
    assert p.status == ST_UNASSIGNED and [c.kind for c in p.changes] == ["REMOVED"]


def test_unmapped_group_never_drops_existing_access(R):
    p = L.plan_outlet([led("Mystery Group")], R, [row(RAUNAK)])
    assert p.status == ST_UNMAPPED_GROUP and p.changes == [] and p.unmapped_groups == ["Mystery Group"]


def test_group_missing_from_the_table_is_treated_as_unmapped(R):
    p = L.plan_outlet([led("Brand New Group")], R, [row(RAUNAK)])
    assert p.status == ST_UNMAPPED_GROUP and p.changes == []


def test_legacy_matching_tally_is_adopted_without_changing_access(R):
    r = row(RAUNAK, SRC_LEGACY)
    p = L.plan_outlet([led("Raunak Usha")], R, [r])
    assert [(c.kind, c.row_id) for c in p.changes] == [("ADOPTED", r.id)]


def test_legacy_conflict_is_kept_and_flagged_under_report_only(R):
    r = row(SAHIL, SRC_LEGACY)
    p = L.plan_outlet([led("Raunak Usha")], R, [r])
    assert p.status == ST_CONFLICT and p.changes == [] and p.conflicts == [r]


def test_legacy_conflict_is_replaced_under_tally_wins(R):
    r = row(SAHIL, SRC_LEGACY)
    p = L.plan_outlet([led("Raunak Usha")], R, [r], L.POLICY_TALLY_WINS)
    assert {(c.kind, c.employee_id) for c in p.changes} == {("REPLACED_LEGACY", SAHIL), ("ASSIGNED", RAUNAK)}
    assert p.status == ST_ASSIGNED


def test_legacy_assignment_where_tally_has_no_fos_is_a_conflict(R):
    p = L.plan_outlet([led("Sundry Debtors- PH.")], R, [row(RAUNAK, SRC_LEGACY)])
    assert p.status == ST_CONFLICT and p.wanted == {}


def test_two_ledgers_of_one_shop_in_two_fos_groups_give_two_fos(R):
    p = L.plan_outlet([led("Raunak Usha", "G1"), led("Sahil Gautam (Usha)", "G2")], R, [])
    assert p.status == ST_MULTIPLE and {c.employee_id for c in p.changes} == {RAUNAK, SAHIL}


def test_one_unmapped_ledger_pauses_the_whole_outlet(R):
    p = L.plan_outlet([led("Raunak Usha", "G1"), led("Mystery Group", "G2")], R, [row(SAHIL)])
    assert p.status == ST_UNMAPPED_GROUP and p.changes == []


def test_mapped_employee_who_is_already_present_via_app_row_is_adopted_not_duplicated(R):
    r = row(RAUNAK, SRC_APP)
    p = L.plan_outlet([led("Raunak Usha")], R, [r])
    assert [c.kind for c in p.changes] == ["ADOPTED"]
