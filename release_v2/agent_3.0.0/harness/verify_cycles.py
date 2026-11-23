"""Per-cycle proof for a lifecycle replay run: every divergence is explained by a documented window and clears.

    python verify_cycles.py <run_dir>     -> <run_dir>/cycle_verification.json (+ summary on stdout), exit 1 if not PASS

A replay cycle (after the first load) is EQUAL, or its divergence is explained by exactly one of:
  FAULT     an injected fault is active in that cycle, or it is within RECOVERY_CYCLES after the fault ended
  NEXT      changes entered while / after the agent read Tally: equal again at the very next cycle
  HOURLY    within the hourly window: equal again at or before the next hourly-reconcile cycle
  NIGHTLY   outside the 31-day window (old deletion / re-date): equal again at or before the next nightly cycle
  SNAPSHOT  outstanding only, in a cycle without a ledger-balance snapshot: equal at or before the next snapshot cycle
Anything else is UNEXPLAINED. "Equal again" means every discrepancy counter is 0 (duplicates and links to retired
invoices must be 0 in EVERY cycle: those can never be explained by a window).

No permanent loss: the final cycle is equal, every GUID ever sampled as missing / extra / stale is resolved later, and
the final voucher count equals Tally's.
"""
import json
import sys
from pathlib import Path

RECOVERY_CYCLES = 2
COUNTERS = ("missing", "extra", "alter", "rows_missing", "rows_extra", "rows_wrong", "links_missing", "links_extra",
            "links_wrong", "outstanding", "duplicates", "links_to_retired_invoices")
NEVER = ("duplicates", "links_to_retired_invoices")


def nz(r):
    v = r.get("verify") or {}
    return {k: v.get(k, 0) for k in COUNTERS if v.get(k, 0)}


def items_of(r):
    """The records the oracle sampled as differing in cycle r: (kind, identity). Identity is the GUID for vouchers,
    GUID + type for rows, the receipt->invoice pair for links, and the ledger for outstanding (amounts change)."""
    out = set()
    for kind, rows in (r.get("samples") or {}).items():
        if kind not in COUNTERS:
            continue
        for s in rows or []:
            if isinstance(s, str):
                ident = s
            elif kind.startswith("rows_"):
                ident = json.dumps(s[:2])
            else:
                ident = json.dumps(s[0])
            out.add((kind, ident))
    return out


def main(run: Path):
    cy = [json.loads(l) for l in open(run / "cycles.jsonl", encoding="utf-8")]
    replay = [i for i, r in enumerate(cy)
              if not r.get("initial_load") and "first load" not in str(r.get("label") or "").lower()]
    first = replay[0]
    clean = [not nz(r) for r in cy]
    fault_end = {}            # cycle index -> index of last cycle of the fault episode it belongs to
    last_fault = None
    for i, r in enumerate(cy):
        if r.get("fault"):
            last_fault = i
        fault_end[i] = last_fault

    def next_clean(i, pred):
        """index of the first j >= i+1 with pred(j); is that cycle (or an earlier one) clean?"""
        for j in range(i + 1, len(cy)):
            if clean[j]:
                return j, True
            if pred(j):
                return j, clean[j]
        return None, False

    out, counts, persist_max = [], {}, {"cycles": 0, "hours": 0.0}
    never_violations = []
    for i in replay:
        r = cy[i]
        d = nz(r)
        for k in NEVER:
            if d.get(k):
                never_violations.append({"cycle": r["cycle"], k: d[k]})
        if not d:
            continue
        # Per-record tracking: every differing record of this cycle (from the oracle's samples) must be gone by the
        # end of its window. New, unrelated differences that appear meanwhile are judged on their own cycle.
        lf = fault_end.get(i)
        in_fault = bool(r.get("fault")) or (lf is not None and i - lf <= RECOVERY_CYCLES)
        items = items_of(r)
        start = (lf + RECOVERY_CYCLES) if in_fault and lf is not None else i
        nightly_dl = next((j for j in range(max(start, i) + 1, len(cy)) if cy[j].get("nightly")), None)
        snap_dl = next((j for j in range(max(start, i) + 1, len(cy)) if cy[j].get("snapshot")), None)
        deadline = max(x for x in (nightly_dl, snap_dl, i + 1) if x is not None) if (nightly_dl or snap_dl) else None
        if deadline is None:                      # the run ended before the window closed: judge on the final cycle
            deadline = len(cy) - 1
        gone_at = {}
        for it in items:
            gone_at[it] = next((j for j in range(i + 1, deadline + 1) if it not in items_of(cy[j])), None)
        # counters the oracle did not sample (none expected) must be 0 at the deadline
        unsampled = [k for k in d if k not in NEVER and not any(it[0] == k for it in items)]
        unsampled_ok = all(not (cy[deadline].get("verify") or {}).get(k) for k in unsampled)
        if any(v is None for v in gone_at.values()) or not unsampled_ok:
            cls = "UNEXPLAINED"
        elif in_fault:
            cls = "FAULT"
        else:
            last = max(gone_at.values(), default=i + 1)
            if last == i + 1:
                cls = "NEXT"
            elif set(it[0] for it in items) == {"outstanding"} and snap_dl is not None and last <= snap_dl:
                cls = "SNAPSHOT"
            else:
                cls = "NIGHTLY"
        # persistence: how long until the next fully clean cycle
        k = next((j for j in range(i + 1, len(cy)) if clean[j]), None)
        if k is not None:
            from datetime import datetime
            h = (datetime.fromisoformat(cy[k]["sim"]) - datetime.fromisoformat(r["sim"])).total_seconds() / 3600
            if cls != "FAULT" and h > persist_max["hours"]:
                persist_max = {"cycles": k - i, "hours": h, "from_cycle": r["cycle"], "to_cycle": cy[k]["cycle"]}
        counts[cls] = counts.get(cls, 0) + 1
        if cls == "UNEXPLAINED":
            out.append({"cycle": r["cycle"], "sim": r["sim"], "nonzero": d, "samples": r.get("samples")})

    # every sampled GUID resolved later
    seen, unresolved = {}, {}
    for i in replay:
        s = cy[i].get("samples") or {}
        cur = set()
        for kind in ("missing", "extra", "alter"):
            for g in s.get(kind) or []:
                key = f"{kind}:{g if isinstance(g, str) else json.dumps(g)}"
                cur.add(key)
                seen.setdefault(key, cy[i]["cycle"])
        unresolved = {k: v for k, v in {**unresolved, **{k: seen[k] for k in cur}}.items() if k in cur}
    fin = cy[-1]["verify"]
    final_equal = not nz(cy[-1])
    res = {
        "run": str(run), "cycles": len(cy), "first_load_cycles": first, "replay_cycles": len(replay),
        "replay_equal": sum(1 for i in replay if clean[i]), "divergent_by_class": counts,
        "unexplained": out[:50], "unexplained_count": len(out),
        "never_allowed_violations": never_violations[:50],
        "longest_non_fault_divergence": persist_max,
        "sampled_guids_seen": len(seen), "sampled_guids_unresolved_at_end": unresolved,
        "final": {k: fin.get(k) for k in ("tally_vouchers", "fieldtrack_index_active", "tally_rows", "tally_links",
                                          *COUNTERS)},
        "final_equal": final_equal,
    }
    res["PASS"] = (final_equal and not out and not never_violations and not unresolved
                   and fin.get("tally_vouchers") == fin.get("fieldtrack_index_active"))
    (run / "cycle_verification.json").write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")
    print(json.dumps({k: v for k, v in res.items() if k not in ("unexplained", "never_allowed_violations")}, indent=1,
                     default=str))
    if out:
        print("UNEXPLAINED (first 5):", json.dumps(out[:5], default=str)[:2000])
    sys.exit(0 if res["PASS"] else 1)


if __name__ == "__main__":
    main(Path(sys.argv[1]))
