"""
Offline reconciliation of FieldTrack's existing FOS assignments against Tally's ledger groups.

READ-ONLY and database-free: it works on four CSV files exported (read-only) from a database:
  customers.csv    customer_id,name,outlet_code,tally_parent_group,tally_is_debtor,merged
  ledgers.csv      customer_id,tally_guid,parent_group,is_debtor,business_scope,is_primary
  assignments.csv  customer_id,employee_id,source,created_at
  employees.csv    employee_id,full_name,role,is_active

It applies exactly the production rules (app.services.fos_logic.plan_outlet) under a PROPOSED group mapping and
writes a Markdown summary plus one CSV per category. Nothing is written anywhere except the output folder.

Proposed mapping, per Tally ledger group (an admin must still confirm each one):
  * all existing assignments of the group's outlets point to one employee  -> that employee      (basis: existing)
  * no person name in the group name ("Sundry Debtors ZBR", "Other Debtor") -> NOT a FOS group    (basis: generic)
  * exactly one employee has the group's first name                         -> suggestion         (basis: name)
  * otherwise (a salesperson group without a FieldTrack employee)           -> UNMATCHED

Usage:  python -m scripts.fos_reconciliation_report <export_dir> <out_dir>
"""
from __future__ import annotations

import csv
import sys
import uuid
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.models.tally_fos import GROUP_MAPPED, GROUP_NOT_FOS, GROUP_UNMAPPED  # noqa: E402
from app.services import fos_logic as L  # noqa: E402

NO_GROUP = "(no group)"


def read(path: Path) -> list[dict]:
    with open(path, encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def truthy(v) -> bool:
    return str(v).strip().lower() in ("t", "true", "1", "yes")


def main(export_dir: str, out_dir: str) -> int:
    src, out = Path(export_dir), Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    customers = read(src / "customers.csv")
    ledgers = read(src / "ledgers.csv")
    assignments = read(src / "assignments.csv")
    employees = {e["employee_id"]: e for e in read(src / "employees.csv")}
    ok_roles = {"EMPLOYEE", "ADMIN", "SUPER_ADMIN"}
    cands = [(uuid.UUID(i), e["full_name"]) for i, e in employees.items() if truthy(e["is_active"]) and e["role"] in ok_roles]
    ename = {uuid.UUID(i): e["full_name"] for i, e in employees.items()}

    visible = {c["customer_id"]: c for c in customers if c["tally_is_debtor"].strip().lower() != "false" and not truthy(c["merged"])}
    in_scope = defaultdict(list)
    for l in ledgers:
        if l["is_debtor"].strip().lower() == "false":
            continue
        if l["business_scope"] not in ("", "DISTRIBUTION"):
            continue
        in_scope[l["customer_id"]].append(L.LedgerRef(l["tally_guid"], (l["parent_group"] or "").strip() or NO_GROUP))
    cur = defaultdict(list)
    for a in assignments:
        cur[a["customer_id"]].append(L.CurrentRow(uuid.uuid4(), uuid.UUID(a["employee_id"]), a["source"] or "LEGACY"))

    # ---- groups: outlets, existing assignments, proposal
    group_name: dict[str, str] = {}
    group_outlets: Counter = Counter()
    group_existing: dict[str, Counter] = defaultdict(Counter)
    for cid, refs in in_scope.items():
        if cid not in visible:
            continue
        for g in {r.group_name for r in refs}:
            k = L.normalize_group_key(g)
            group_name.setdefault(k, g)
            group_outlets[k] += 1
            for row in cur.get(cid, []):
                group_existing[k][row.employee_id] += 1

    proposal: dict[str, tuple[str, uuid.UUID | None, str]] = {}
    for k, name in group_name.items():
        existing = group_existing.get(k)
        sugg, basis = L.suggest_employee(name, cands)
        if not L.person_tokens(name):
            # A generic group ("Sundry Debtors", "Other Debtor") never means a salesperson, even if a stray
            # assignment sits on one of its outlets: that assignment is reported as a conflict instead.
            proposal[k] = (GROUP_NOT_FOS, None, "generic group: no salesperson name in it"
                           + (f" ({sum(existing.values())} existing assignment(s) will be flagged)" if existing else ""))
        elif existing and len(existing) == 1:
            eid = next(iter(existing))
            proposal[k] = (GROUP_MAPPED, eid, f"existing: {existing[eid]} of {group_outlets[k]} outlets already assigned")
        elif existing:
            proposal[k] = (GROUP_UNMAPPED, None, "existing assignments disagree: " + ", ".join(sorted(ename.get(e, str(e)) for e in existing)))
        elif sugg:
            proposal[k] = (GROUP_MAPPED, sugg, "name suggestion (needs confirmation): " + str(basis))
        else:
            proposal[k] = (GROUP_UNMAPPED, None, "salesperson-style group with no matching FieldTrack employee")

    def scenario(include_name_suggestions: bool, policy: str):
        rules = {}
        for k, (status, eid, basis) in proposal.items():
            if status == GROUP_MAPPED and basis.startswith("name suggestion") and not include_name_suggestions:
                rules[k] = L.GroupRule(GROUP_UNMAPPED)
            else:
                rules[k] = L.GroupRule(status, eid)
        buckets, status_counts = defaultdict(list), Counter()
        for cid, c in visible.items():
            refs = in_scope.get(cid, [])
            rows = cur.get(cid, [])
            plan = L.plan_outlet(refs, rules, rows, policy)
            status_counts[plan.status] += 1
            item = {"customer_id": cid, "outlet": c["name"], "outlet_code": c["outlet_code"],
                    "tally_group": "; ".join(sorted({r.group_name for r in refs})) or "",
                    "existing_fos": ", ".join(sorted(ename.get(r.employee_id, "?") for r in rows)),
                    "tally_fos": ", ".join(sorted(ename.get(e, "?") for e in plan.wanted))}
            kinds = {ch.kind for ch in plan.changes}
            if plan.status == "CONFLICT":
                buckets["conflicting" if plan.wanted else "assigned_here_blank_in_tally"].append(item)
            elif plan.status == "UNMAPPED_GROUP":
                item["unmapped_groups"] = "; ".join(plan.unmapped_groups)
                buckets["missing_employee_mapping"].append(item)
            elif plan.status in ("ASSIGNED", "MULTIPLE"):
                if "ASSIGNED" in kinds and not rows:
                    buckets["new_from_tally"].append(item)
                elif kinds - {"ADOPTED"}:
                    buckets["changed"].append(item)
                else:
                    buckets["matching"].append(item)
            elif plan.status == "UNASSIGNED":
                buckets["assigned_here_blank_in_tally" if rows else "unassigned_in_both"].append(item)
            elif plan.status == "NO_TALLY" and rows:
                buckets["no_tally_ledger_with_assignment"].append(item)
        return buckets, status_counts

    resultA = scenario(False, L.POLICY_REPORT_ONLY)
    resultB = scenario(True, L.POLICY_REPORT_ONLY)

    def write_csv(name: str, rows: list[dict]):
        if not rows:
            return
        with open(out / name, "w", encoding="utf-8-sig", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)

    for label, (buckets, _sc) in (("A_existing_only", resultA), ("B_with_name_suggestions", resultB)):
        for k, rows in buckets.items():
            write_csv(f"{label}__{k}.csv", rows)

    grows = []
    for k, name in sorted(group_name.items(), key=lambda kv: (-group_outlets[kv[0]], kv[1].lower())):
        status, eid, basis = proposal[k]
        grows.append({"tally_group": name, "outlets": group_outlets[k],
                      "outlets_with_existing_assignment": sum(group_existing[k].values()),
                      "proposed_status": status, "proposed_employee": ename.get(eid, "") if eid else "", "basis": basis})
    write_csv("groups_proposed_mapping.csv", grows)

    total = len(visible)
    with_fos = sum(1 for cid in visible if cur.get(cid))
    lines = ["# FOS reconciliation: FieldTrack production vs Tally ledger groups", "",
             "Read-only analysis of an export of the production database. Nothing was written to production or Tally.", "",
             f"- Visible outlets: **{total}**; with an existing FOS assignment: **{with_fos}**; without: **{total - with_fos}**",
             f"- Tally ledger groups holding in-scope outlets: **{len(group_name)}**",
             f"- Existing assignment rows: **{len(assignments)}** (all LEGACY: created in one batch before the sync existed)", ""]
    for label, (buckets, sc), title in (("A", resultA, "Scenario A: only mappings proven by the existing assignments, plus generic groups as 'not a FOS group'"),
                                        ("B", resultB, "Scenario B: A plus name-based suggestions confirmed")):
        lines += [f"## {title}", "", "| Outcome | Outlets |", "|---|---:|"]
        names = {"matching": "Matching: existing FOS = Tally FOS (will be adopted)",
                 "new_from_tally": "New: Tally assigns a FOS, FieldTrack has none",
                 "conflicting": "Conflicting: existing FOS differs from Tally's (kept, flagged)",
                 "assigned_here_blank_in_tally": "Assigned in FieldTrack, blank (non-FOS group) in Tally (kept, flagged)",
                 "missing_employee_mapping": "Group has no employee mapping yet (existing access kept)",
                 "unassigned_in_both": "Unassigned in both",
                 "no_tally_ledger_with_assignment": "No Tally ledger, has assignment (prospects, untouched)",
                 "changed": "Other change"}
        for k, label_text in names.items():
            lines.append(f"| {label_text} | {len(buckets.get(k, []))} |")
        lines += ["", "Outlet status after the sync: " + ", ".join(f"{k} {v}" for k, v in sorted(sc.items())), ""]
    um = [g for g in grows if g["proposed_status"] == GROUP_UNMAPPED]
    lines += ["## Tally salesperson groups with no FieldTrack employee / unclear mapping", "",
              "| Tally group | Outlets | Why |", "|---|---:|---|"]
    lines += [f"| {g['tally_group']} | {g['outlets']} | {g['basis']} |" for g in um]
    lines += ["", "## Proposed mapping per group", "", "| Tally group | Outlets | Existing assignments | Proposal | Employee | Basis |", "|---|---:|---:|---|---|---|"]
    lines += [f"| {g['tally_group']} | {g['outlets']} | {g['outlets_with_existing_assignment']} | {g['proposed_status']} | {g['proposed_employee']} | {g['basis']} |"
              for g in grows]
    (out / "RECONCILIATION_REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines[:40]))
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(2)
    sys.exit(main(sys.argv[1], sys.argv[2]))
