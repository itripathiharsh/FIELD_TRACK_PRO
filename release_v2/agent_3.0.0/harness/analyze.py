"""Analyse an Agent 3.0 lifecycle replay harness run.

Usage:  python analyze.py <run_dir>

Reads <run_dir>/cycles.jsonl (required), summary.json and events.json (optional),
writes <run_dir>/analysis.md and <run_dir>/analysis.json and prints the markdown.
Stdlib only; tolerant of None / missing fields (e.g. 2.2.3 rollback records).
"""
from __future__ import annotations

import json
import math
import sys
from collections import Counter
from datetime import date, datetime
from pathlib import Path

DISCREPANCY = ("missing", "extra", "alter", "rows_missing", "rows_extra", "rows_wrong", "duplicates",
               "links_missing", "links_extra", "links_wrong", "outstanding", "links_to_retired_invoices")
# (label, Tally key, FieldTrack key)
COUNTS = (("vouchers", "tally_vouchers", "fieldtrack_index_active"),
          ("rows", "tally_rows", None), ("links", "tally_links", None))


# ---------------------------------------------------------------- helpers
def num(x, default=0):
    if isinstance(x, bool):
        return int(x)
    if isinstance(x, (int, float)):
        return x
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


def d(obj, *path):
    """Safe nested get: d(rec, 'hourly', 'repair', 'days')."""
    for p in path:
        if not isinstance(obj, dict):
            return None
        obj = obj.get(p)
    return obj


def stats(values):
    vals = sorted(num(v) for v in values if v is not None)
    if not vals:
        return {"n": 0, "mean": None, "p95": None, "max": None, "sum": 0}
    k = max(0, math.ceil(0.95 * len(vals)) - 1)  # nearest-rank p95
    return {"n": len(vals), "mean": round(sum(vals) / len(vals), 3), "p95": vals[k], "max": vals[-1],
            "sum": round(sum(vals), 3)}


def load_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def load_cycles(path: Path):
    out, bad = [], 0
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
                if isinstance(r, dict):
                    out.append(r)
            except ValueError:
                bad += 1  # a run still being written may end in a partial line
    return out, bad


def sim_date(rec):
    s = rec.get("sim")
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s)).date()
    except ValueError:
        try:
            return date.fromisoformat(str(s)[:10])
        except ValueError:
            return None


def fy_start(day: date) -> date:
    return date(day.year if day.month >= 4 else day.year - 1, 4, 1)


def is_first_load(rec) -> bool:
    if rec.get("initial_load"):
        return True
    if "first load" in str(rec.get("label") or "").lower():
        return True
    hist = rec.get("history")
    return isinstance(hist, dict) and any(str(v).upper() == "LOADING" for v in hist.values())


def has_agent(rec) -> bool:
    return rec.get("tally_requests") is not None or isinstance(rec.get("by_kind"), dict)


def tally_secs(rec) -> float:
    bk = rec.get("by_kind") or {}
    return round(sum(num(v.get("s")) for v in bk.values() if isinstance(v, dict)), 3)


def kind(rec, k, field):
    return num(d(rec, "by_kind", k, field))


def path_of(rec) -> str:
    if isinstance(rec.get("nightly"), dict):
        return "nightly"
    if isinstance(rec.get("hourly"), dict):
        return "hourly_only"
    return "neither"


def load_block(recs):
    return {
        "cycles": len(recs),
        "requests": stats(r.get("tally_requests") for r in recs),
        "ftpvch_requests": stats(kind(r, "FtpVch", "n") for r in recs),
        "vouchers_returned": stats(r.get("tally_vouchers_returned") for r in recs),
        "bytes": stats(r.get("tally_bytes") for r in recs),
        "tally_seconds": stats(tally_secs(r) for r in recs),
    }


# ---------------------------------------------------------------- analysis
def analyse(run: Path) -> dict:
    cycles, bad_lines = load_cycles(run / "cycles.jsonl")
    summary = load_json(run / "summary.json")
    events = load_json(run / "events.json")
    first = [r for r in cycles if is_first_load(r)]
    replay = [r for r in cycles if not is_first_load(r)]
    replay_agent = [r for r in replay if has_agent(r)]
    final = cycles[-1] if cycles else {}
    fv = final.get("verify") or {}

    eq = [r for r in cycles if d(r, "verify", "equal") is True]
    not_eq = [r for r in cycles if d(r, "verify", "equal") is not True]

    res: dict = {"run_dir": str(run), "bad_lines": bad_lines,
                 "files": {"summary.json": summary is not None, "events.json": events is not None}}

    # 1. totals
    res["totals"] = {
        "cycles": len(cycles), "first_load_cycles": len(first), "replay_cycles": len(replay),
        "replay_cycles_without_agent_fields": len(replay) - len(replay_agent),
        "equal": len(eq), "not_equal": len(not_eq),
        "not_equal_first_load": sum(1 for r in not_eq if is_first_load(r)),
        "not_equal_replay": sum(1 for r in not_eq if not is_first_load(r)),
        "statuses": dict(Counter(str(r.get("status")) for r in cycles)),
        "labels": dict(Counter(str(r.get("label")) for r in cycles)),
        "faults": dict(Counter(f for r in cycles for f in (r.get("fault") or []))),
        "final": {"cycle": final.get("cycle"), "sim": final.get("sim"), "label": final.get("label"),
                  "status": final.get("status"), "equal": fv.get("equal")},
        "sim_span": [cycles[0].get("sim"), final.get("sim")] if cycles else None,
    }
    if isinstance(events, list):
        res["totals"]["events"] = len(events)
        res["totals"]["events_by_kind"] = dict(Counter(str(e.get("kind")) for e in events if isinstance(e, dict)))

    # 2. correctness
    counts = []
    for name, tk, fk in COUNTS:
        counts.append({"metric": name, "tally": fv.get(tk), "fieldtrack": fv.get(fk) if fk else None})
    res["correctness"] = {
        "final_counts": counts,
        "final_discrepancies": {k: fv.get(k) for k in DISCREPANCY},
        "replay_max": {k: max((num(d(r, "verify", k)) for r in replay), default=0) for k in DISCREPANCY},
        "replay_cycles_with_any_discrepancy": sum(
            1 for r in replay if any(num(d(r, "verify", k)) for k in DISCREPANCY)),
        "not_equal_cycles": [
            {"cycle": r.get("cycle"), "sim": r.get("sim"), "label": r.get("label"), "status": r.get("status"),
             "fault": r.get("fault") or [], "first_load": is_first_load(r),
             "nonzero": {k: d(r, "verify", k) for k in DISCREPANCY if num(d(r, "verify", k))}}
            for r in not_eq],
    }

    # 3. Tally load (replay, agent records only)
    by_kind_tot: dict = {}
    for r in replay_agent:
        for k, v in (r.get("by_kind") or {}).items():
            if not isinstance(v, dict):
                continue
            a = by_kind_tot.setdefault(k, {"n": 0, "s": 0.0, "bytes": 0, "vouchers": 0})
            for f in a:
                a[f] += num(v.get(f))
    for a in by_kind_tot.values():
        a["s"] = round(a["s"], 3)
        a["n_per_cycle"] = round(a["n"] / len(replay_agent), 2) if replay_agent else None
    res["load"] = {
        "all_replay": load_block(replay_agent),
        "nightly": load_block([r for r in replay_agent if path_of(r) == "nightly"]),
        "hourly_only": load_block([r for r in replay_agent if path_of(r) == "hourly_only"]),
        "neither": load_block([r for r in replay_agent if path_of(r) == "neither"]),
        "snapshot": load_block([r for r in replay_agent if r.get("snapshot")]),
        "no_snapshot": load_block([r for r in replay_agent if not r.get("snapshot")]),
        "snapshot_field_present": any("snapshot" in r for r in cycles),
        "by_kind_totals": dict(sorted(by_kind_tot.items(), key=lambda kv: -kv[1]["n"])),
    }

    # 4. reconciliation
    hr = [r["hourly"] for r in replay if isinstance(r.get("hourly"), dict)]
    nr = [r["nightly"] for r in replay if isinstance(r.get("nightly"), dict)]
    retire = [x.get("retire") for x in hr + nr if "retire" in x]
    retired = Counter()
    for x in retire:
        for k, v in (d(x, "retired") or {}).items():
            retired[k] += num(v)
    res["reconcile"] = {
        "hourly_runs": len(hr),
        "hourly": {k: sum(num(x.get(k)) for x in hr) for k in ("listed", "missing", "stale", "extra")},
        "hourly_repair": {k: sum(num(d(x, "repair", k)) for x in hr)
                          for k in ("requested", "days", "fetched", "rejected", "failed", "queued")},
        "hourly_found_something": sum(1 for x in hr if num(x.get("missing")) + num(x.get("stale")) + num(x.get("extra"))),
        "hourly_seconds": stats(x.get("seconds") for x in hr),
        "nightly_runs": len(nr),
        "nightly": {k: sum(num(x.get(k)) for x in nr) for k in ("missing", "stale", "extra", "guids", "months")},
        "nightly_repair_days": sum(num(x.get("repair_days")) for x in nr),
        "nightly_repair_fetched": sum(num(x.get("repair_fetched")) for x in nr),
        "nightly_found_something": sum(1 for x in nr if num(x.get("missing")) + num(x.get("stale")) + num(x.get("extra"))),
        "nightly_seconds": stats(x.get("seconds") for x in nr),
        "checkpoint_rebuilt": sum(1 for x in hr + nr if x.get("checkpoint_rebuilt")),
        "retire_runs": len(retire),
        "retire_refused": sum(1 for x in retire if isinstance(x, dict) and "refused" in x),
        "retire_skipped": sum(1 for x in retire if isinstance(x, dict) and "skipped" in x),
        "retire_messages": sorted({str(x.get("refused") or x.get("skipped")) for x in retire
                                   if isinstance(x, dict) and ("refused" in x or "skipped" in x)})[:10],
        "retired": dict(retired),
        "voucher_path": {k: sum(num(d(r, "vouchers", k)) for r in replay)
                         for k in ("changed_headers", "days", "validated", "sent", "failed", "queued")},
    }

    # 5. first load
    fa = [r for r in first if has_agent(r)]
    done = next((r for r in first if d(r, "verify", "equal") is True), None)
    res["first_load"] = {
        "cycles": len(first),
        "requests": sum(num(r.get("tally_requests")) for r in fa),
        "agent_seconds": round(sum(num(r.get("agent_seconds")) for r in fa), 2),
        "tally_seconds": round(sum(tally_secs(r) for r in fa), 3),
        "vouchers_returned": sum(num(r.get("tally_vouchers_returned")) for r in fa),
        "bytes": sum(num(r.get("tally_bytes")) for r in fa),
        "ftpvch_requests": sum(kind(r, "FtpVch", "n") for r in fa),
        "equal_reached_at_cycle": done.get("cycle") if done else None,
        "tally_vouchers_at_end": d(first[-1], "verify", "tally_vouchers") if first else None,
    }

    # 6. wall time
    res["timing"] = {
        "replay_agent_seconds": stats(r.get("agent_seconds") for r in replay_agent),
        "replay_verify_seconds": stats(r.get("verify_seconds") for r in replay),
        "first_load_agent_seconds": stats(r.get("agent_seconds") for r in fa),
        "all_verify_seconds": stats(r.get("verify_seconds") for r in cycles),
    }

    # 7. full-FY re-download baseline vs actual nightly repair days
    rows = []
    for r in replay:
        n = r.get("nightly")
        sd = sim_date(r)
        if not isinstance(n, dict) or sd is None:
            continue
        fy_days = (sd - fy_start(sd)).days + 1
        rows.append({"cycle": r.get("cycle"), "sim": r.get("sim"), "fy_days": fy_days,
                     "repair_days": num(n.get("repair_days")), "ftpvch_requests": kind(r, "FtpVch", "n")})
    base = sum(x["fy_days"] for x in rows)
    act = sum(x["repair_days"] for x in rows)
    res["fy_baseline"] = {
        "nightly_cycles": len(rows), "baseline_day_requests": base, "actual_repair_days": act,
        "actual_nightly_ftpvch_requests": sum(x["ftpvch_requests"] for x in rows),
        "ratio_actual_over_baseline": round(act / base, 4) if base else None,
        "reduction_factor": round(base / act, 1) if act else None,
        "per_nightly": rows,
    }
    if isinstance(summary, dict):
        res["summary_json"] = {k: summary.get(k) for k in ("cycles", "equal", "expected_divergence", "unexpected",
                                                          "final_equal", "statuses", "faults") if k in summary}
    return res


# ---------------------------------------------------------------- markdown
def f(x, nd=2):
    if x is None:
        return "-"
    if isinstance(x, float):
        return f"{x:,.{nd}f}" if not x.is_integer() else f"{int(x):,}"
    if isinstance(x, int):
        return f"{x:,}"
    return str(x)


def mb(x):
    return "-" if x is None else f"{num(x) / 1e6:,.2f}"


def stat_row(name, s, conv=f):
    return f"| {name} | {conv(s['mean'])} | {conv(s['p95'])} | {conv(s['max'])} |"


def render(a: dict) -> str:
    t, c, L, R, F, T, B = (a["totals"], a["correctness"], a["load"], a["reconcile"], a["first_load"],
                           a["timing"], a["fy_baseline"])
    o = [f"# Agent 3.0 harness analysis", "", f"Run: `{a['run_dir']}`", ""]
    missing = [k for k, v in a["files"].items() if not v]
    if missing or a["bad_lines"]:
        o += [f"_Notes: missing files: {', '.join(missing) or 'none'}; unparsable cycle lines: {a['bad_lines']}_", ""]

    o += ["## 1. Totals", "",
          f"- Cycles: **{t['cycles']}** ({t['first_load_cycles']} first-load, {t['replay_cycles']} replay"
          + (f", {t['replay_cycles_without_agent_fields']} replay records without agent fields" if t["replay_cycles_without_agent_fields"] else "") + ")",
          f"- Sim span: {t['sim_span'][0] if t['sim_span'] else '-'} -> {t['sim_span'][1] if t['sim_span'] else '-'}",
          f"- Verify equal: **{t['equal']}**, not equal: **{t['not_equal']}** "
          f"(first-load {t['not_equal_first_load']}, replay {t['not_equal_replay']})",
          f"- Statuses: {', '.join(f'{k}={v}' for k, v in t['statuses'].items())}",
          f"- Faults injected: {', '.join(f'{k}={v}' for k, v in t['faults'].items()) or 'none'}"]
    if "events" in t:
        o.append(f"- Events: {t['events']} ({', '.join(f'{k}={v}' for k, v in t['events_by_kind'].items())})")
    fn = t["final"]
    o += [f"- Final cycle {fn['cycle']} ({fn['label']}, {fn['sim']}): status {fn['status']}, equal **{fn['equal']}**", ""]

    o += ["## 2. Data correctness", "", "Final cycle counts:", "", "| Entity | Tally | FieldTrack |", "|---|---:|---:|"]
    for x in c["final_counts"]:
        o.append(f"| {x['metric']} | {f(x['tally'])} | {f(x['fieldtrack']) if x['fieldtrack'] is not None else '(diff-only)'} |")
    o += ["", "| Discrepancy | Final | Max over replay cycles |", "|---|---:|---:|"]
    for k in DISCREPANCY:
        o.append(f"| {k} | {f(c['final_discrepancies'].get(k))} | {f(c['replay_max'].get(k))} |")
    o += ["", f"Replay cycles with any discrepancy: **{c['replay_cycles_with_any_discrepancy']}**", ""]
    ne_replay = [x for x in c["not_equal_cycles"] if not x["first_load"]]
    ne_first = [x for x in c["not_equal_cycles"] if x["first_load"]]
    if ne_first:
        o.append(f"Not-equal first-load cycles (expected while loading): {', '.join(str(x['cycle']) for x in ne_first)}")
        o.append("")
    if ne_replay:
        o += ["Not-equal replay cycles:", "", "| Cycle | Sim | Label | Status | Fault | Non-zero |", "|---:|---|---|---|---|---|"]
        for x in ne_replay:
            o.append(f"| {x['cycle']} | {x['sim']} | {x['label']} | {x['status']} | {','.join(x['fault']) or '-'} | "
                     f"{', '.join(f'{k}={v}' for k, v in x['nonzero'].items()) or '-'} |")
    else:
        o.append("Not-equal replay cycles: **none**")
    o.append("")

    o += ["## 3. Tally load per cycle (replay cycles only)", "",
          "Voucher counts include both header-only and full-detail FtpVch responses (not distinguishable).", "",
          "| Path | Cycles | Requests mean / p95 / max | FtpVch req mean / p95 / max | Vouchers mean / p95 / max | MB mean / p95 / max | Tally s mean / p95 / max |",
          "|---|---:|---|---|---|---|---|"]
    for name, key in (("all replay", "all_replay"), ("nightly reconcile", "nightly"), ("hourly only", "hourly_only"),
                      ("neither", "neither"), ("ledger snapshot", "snapshot"), ("no snapshot", "no_snapshot")):
        b = L[key]
        if not b["cycles"]:
            o.append(f"| {name} | 0 | - | - | - | - | - |")
            continue
        tri = lambda s, cv=f: f"{cv(s['mean'])} / {cv(s['p95'])} / {cv(s['max'])}"
        o.append(f"| {name} | {b['cycles']} | {tri(b['requests'])} | {tri(b['ftpvch_requests'])} | "
                 f"{tri(b['vouchers_returned'])} | {tri(b['bytes'], mb)} | {tri(b['tally_seconds'], lambda x: f(x, 3))} |")
    if not L["snapshot_field_present"]:
        o.append("")
        o.append("_No `snapshot` field in these records (older runner); snapshot split not available._")
    o += ["", "Requests by Tally collection (replay totals):", "", "| Collection | Requests | Per cycle | Seconds | MB | Vouchers |",
          "|---|---:|---:|---:|---:|---:|"]
    for k, v in L["by_kind_totals"].items():
        o.append(f"| {k} | {f(v['n'])} | {f(v['n_per_cycle'])} | {f(v['s'], 3)} | {mb(v['bytes'])} | {f(v['vouchers'])} |")
    o.append("")

    o += ["## 4. Reconciliation effectiveness", "",
          f"- Hourly runs: {R['hourly_runs']}; found something in **{R['hourly_found_something']}**; "
          f"totals missing={f(R['hourly']['missing'])}, stale={f(R['hourly']['stale'])}, extra={f(R['hourly']['extra'])}",
          f"- Hourly repair: requested={f(R['hourly_repair']['requested'])}, days={f(R['hourly_repair']['days'])}, "
          f"fetched={f(R['hourly_repair']['fetched'])}, rejected={f(R['hourly_repair']['rejected'])}, "
          f"failed={f(R['hourly_repair']['failed'])}, queued={f(R['hourly_repair']['queued'])}",
          f"- Nightly runs: {R['nightly_runs']}; found something in **{R['nightly_found_something']}**; "
          f"totals missing={f(R['nightly']['missing'])}, stale={f(R['nightly']['stale'])}, extra={f(R['nightly']['extra'])}",
          f"- Nightly repair: days fetched={f(R['nightly_repair_days'])}, vouchers fetched={f(R['nightly_repair_fetched'])}",
          f"- Retire: runs={R['retire_runs']}, refused={R['retire_refused']}, skipped={R['retire_skipped']}, "
          f"retired={', '.join(f'{k}={f(v)}' for k, v in R['retired'].items()) or 'none'}",
          f"- Checkpoint rebuilds: {R['checkpoint_rebuilt']}",
          f"- Incremental voucher path (replay totals): "
          + ", ".join(f"{k}={f(v)}" for k, v in R["voucher_path"].items())]
    if R["retire_messages"]:
        o.append(f"- Retire refusal/skip reasons: {'; '.join(R['retire_messages'])}")
    o.append("")

    o += ["## 5. First load", "",
          f"- Cycles: {F['cycles']} (verify equal reached at cycle {F['equal_reached_at_cycle'] or '-'})",
          f"- Requests: {f(F['requests'])} (FtpVch {f(F['ftpvch_requests'])}); Tally seconds {f(F['tally_seconds'], 3)}; "
          f"agent seconds {f(F['agent_seconds'])}",
          f"- Vouchers returned: {f(F['vouchers_returned'])} (Tally holds {f(F['tally_vouchers_at_end'])}); "
          f"data {mb(F['bytes'])} MB", ""]

    o += ["## 6. Wall time", "", "| Measure | Mean | p95 | Max |", "|---|---:|---:|---:|",
          stat_row("Agent s / replay cycle", T["replay_agent_seconds"]),
          stat_row("Verify s / replay cycle", T["replay_verify_seconds"]),
          stat_row("Agent s / first-load cycle", T["first_load_agent_seconds"]), ""]

    o += ["## 7. Nightly vs full-FY re-download baseline", "",
          "Baseline = one day request per FY day (2026-04-01 .. sim date) at every nightly; actual = nightly repair_days.", ""]
    if B["nightly_cycles"]:
        o += [f"- Nightly cycles: {B['nightly_cycles']}; baseline day requests: **{f(B['baseline_day_requests'])}**; "
              f"actual repair days: **{f(B['actual_repair_days'])}** (nightly FtpVch requests incl. manifests: "
              f"{f(B['actual_nightly_ftpvch_requests'])})",
              f"- Ratio actual/baseline: **{f(B['ratio_actual_over_baseline'], 4)}**"
              + (f" ({B['reduction_factor']}x fewer day fetches)" if B["reduction_factor"] else ""), "",
              "| Cycle | Sim | FY days | Repair days | FtpVch requests |", "|---:|---|---:|---:|---:|"]
        for x in B["per_nightly"][:60]:
            o.append(f"| {x['cycle']} | {x['sim']} | {x['fy_days']} | {f(x['repair_days'])} | {f(x['ftpvch_requests'])} |")
        if len(B["per_nightly"]) > 60:
            o.append(f"| ... | {len(B['per_nightly']) - 60} more in analysis.json | | | |")
    else:
        o.append("No nightly reconcile cycles in this run.")
    o.append("")
    return "\n".join(o)


def main(argv):
    if len(argv) != 2:
        print(__doc__)
        return 2
    run = Path(argv[1])
    if not (run / "cycles.jsonl").is_file():
        print(f"no cycles.jsonl in {run}", file=sys.stderr)
        return 1
    a = analyse(run)
    md = render(a)
    (run / "analysis.json").write_text(json.dumps(a, indent=1, default=str), encoding="utf-8")
    (run / "analysis.md").write_text(md, encoding="utf-8")
    try:
        print(md)
    except UnicodeEncodeError:
        sys.stdout.buffer.write(md.encode("utf-8"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
