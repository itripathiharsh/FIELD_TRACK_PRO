# FieldTrack Tally Sync Agent 3.0: architecture

One executable, one process, one scheduler, one SQLite database, one checkpoint system, one retry mechanism, one
quarantine, one agent identity and one backend connection.

**The core idea:**
- the AlterID cursor gives speed
- reconciliation gives correctness

## 1. Diagram

```
                              CLIENT VM (Windows)                                         FIELDTRACK BACKEND (HTTPS)
 ┌──────────────────────────────────────────────────────────────────────────────┐      ┌──────────────────────────────┐
 │ FieldTrackTallyAgent.exe daemon  (single-instance mutex, one process)        │      │  X-Agent-Id / X-Agent-Key    │
 │                                                                              │      │  company GUID bound to agent │
 │  heartbeat thread (60 s) ─────────────────────────── /heartbeat ───────────────────▶│                              │
 │                                                                              │      │                              │
 │  scheduler loop (every SYNC_INTERVAL_SECONDS = 300 s), per FY:               │      │                              │
 │                                                                              │      │                              │
 │   0. retry queue replay ───────────────────────────── /sync/vouchers ─────────────▶│  GUID-keyed upserts,         │
 │   1. company by GUID (CompanyCol)                                            │      │  older AlterID skipped,      │
 │   2. masters + changed debtors (AlterID) ─────────── /sync/ledgers ──────────────▶│  every processed voucher     │
 │   3. FAST PATH  headers AlterID > checkpoint (month-scoped)                  │      │  indexed (GUID, AlterID,     │
 │                 -> changed days' vouchers (day-scoped, lean) ─ /sync/vouchers ──▶│  date, ACTIVE/DELETED)       │
 │                 -> checkpoint = highest AlterID read                         │      │  in tally_voucher_index      │
 │   4. balances (hourly): ledger + bills snapshots ─── /sync/ledgers, /bills ──────▶│                              │
 │   5. HOURLY RECONCILE  headers only, today-31..today ─ /sync/reconcile ──────────▶│  read-only compare:          │
 │                 <- missing / stale / extra ◀─────────────────────────────────────── │  missing / stale / extra     │
 │                 -> fetch only affected dates (AlterID-narrowed) ─ /sync/vouchers ▶│                              │
 │                 -> retire extras: window manifest (floors) ─ /sync/manifest ─────▶│  50% completeness floor      │
 │   6. NIGHTLY RECONCILE  whole FY, month by month (resumable)                 │      │                              │
 │                 same compare + repair per month ──── /sync/reconcile, /vouchers ▶│                              │
 │                 -> ONE full-FY manifest retires extras ─ /sync/manifest ─────────▶│                              │
 │                                                                              │      └──────────────────────────────┘
 │  every Tally request ──▶ TallyGuard (breaker, machine-wide lock, duty-cycle pacing, telemetry)
 │                              │
 │                              ▼ XML Export only (read-only)
 │                         TallyPrime :9000
 │                                                                              │
 │  data\sync_agent.db  (ONE SQLite database)                                   │
 │    checkpoints          vouchers_v2[@fy], debtors_v2, balances_v2, manifest_v2, manifest_count_v2,
 │                         reconcile_hourly_v3, reconcile_nightly_v3
 │    retry_queue          batches the backend did not take (network / 5xx), replayed with backoff
 │    validation_quarantine rejected vouchers: RETRY ONLY (reconciliation keeps asking for them)
 │    agent_kv             first-load progress, approvals, breaker, health, nightly progress, telemetry,
 │                         first-load reconciliation result
 └──────────────────────────────────────────────────────────────────────────────┘
```

## 2. How reconciliation works

**The backend voucher index.**
- `tally_voucher_index` has one row per Tally voucher GUID that FieldTrack has processed:
  - its latest AlterID
  - its date
  - `ACTIVE` or `DELETED`
- It is written in the same database savepoint as the voucher's invoice / payment / adjustment rows.
- It therefore never claims a version whose rows were not written.
- Vouchers that leave no row are indexed too, for example:
  - purchases
  - contras
  - cancelled vouchers
  - optional vouchers

**`POST /api/v1/integrations/tally/sync/reconcile`.**
- **Input:** a date window plus every voucher header Tally holds in it, as `{guid, alter_id}`.
- **It returns, without writing anything:**

| List | Meaning |
|---|---|
| `missing` | Tally lists it; FieldTrack never processed it, or holds it as `DELETED` (re-created or restored in Tally) |
| `stale` | Tally lists a higher AlterID than the version FieldTrack processed |
| `extra` | FieldTrack holds it `ACTIVE` in the window, but Tally no longer lists it (deleted, or re-dated out of the window) |

- It returns 409 when the company GUID differs from the one bound to the agent.

**Repair.**
- `missing` and `stale` vouchers are fetched again:
  - one day-scoped request per affected date
  - each narrowed with `AlterID >= (lowest needed AlterID of that date)`
  - only the needed GUIDs are kept
- They are re-sent through the normal idempotent `/sync/vouchers` path.
- Dates without a discrepancy are never read in full.

**Retirement.**
- **Hourly extras** are retired by a manifest of exactly that window. It is refused locally in two cases, and the
  nightly run then decides:
  - Tally listed nothing
  - the extras exceed `max(10, half of what FieldTrack holds in the window)`, i.e. a truncated answer
- **Nightly extras** are retired by the existing full-FY manifest, with these floors:
  - never empty
  - never below half of the last accepted manifest
  - the backend refuses a manifest below half of what it holds

**What this removes.**

| Removed | Why it is no longer needed |
|---|---|
| Post-dated register (2.2.3 M4) | When a post-dated voucher's date arrives, the hourly window lists it; FieldTrack reports it missing; it is fetched. A voucher moved further into the future is retired as extra until its new date. |
| Quarantine capping the checkpoint (2.2.2 M1) | A rejected voucher is not in the index, so it stays `missing` and is retired hourly (31-day window) or nightly (whole FY) until it loads. The checkpoint moves on. |
| Catch-up mechanisms (2.2.3 one-time future scan, the R5/R6 "watermark" fix proposed for 2.2.4) | Reconciliation compares Tally with the backend directly. Neither the agent's local memory nor the version that ran meanwhile matters. |
| Checkpoint as a correctness mechanism | The checkpoint only decides how fast a change arrives:<br>• **rolled back:** it re-reads idempotently<br>• **too far ahead:** reconciliation repairs the gap<br>• **corrupt:** the fast path pauses, a nightly run executes at once, and the checkpoint is rebuilt from it |

## 3. Schedule and Tally load

| Path | When | Tally requests (headers = GUID, date, type, flags, AlterID only) |
|---|---|---|
| Fast path | every cycle (5 min) | one header request per FY month (AlterID-filtered), plus one day request per changed date |
| Hourly reconcile | every 60 min | 2 header requests (today-31 .. today, split at the month boundary), plus one narrowed day request per affected date |
| Nightly reconcile | once per IST date from 01:00 (historical FY: weekly) | one header request per FY month, plus one narrowed day request per affected date |
| Balances | every 60 min | masters, debtors, Group Summary ×2, Bills Receivable |

**Properties:**
- The whole FY is never downloaded in full again after the first load.
- Every request goes through TallyGuard, so the 2.2.1 protections still apply:
  - circuit breaker
  - machine-wide lock
  - duty cycle ≤ 50%

## 4. One database

**Moved into `data/sync_agent.db`, key-value table `agent_kv`.** These were JSON files in 2.2.x:

| 2.2.x file | 3.0 key |
|---|---|
| `initial_load_v2.json`, `initial_load_fy<label>.json` | `initial_load:<label>` |
| `tally_breaker.json` | `tally_breaker` |
| `agent_state.json` | `agent_health` |
| `approve_first_load_<label>.json` | `approve_first_load:<label>` |
| `validation_fy<label>.json` | `validation:<label>` |
| (new) | `nightly:<label>` (resumable nightly progress), `telemetry:tally` |

**Migration from the old files.**
- Each legacy file is migrated the first time its key is read.
- The file is renamed `<name>.migrated-3.0` and kept.
- A rollback can rename it back.

**Not moved.**
- The log file.
- `validate-fy`'s own output folder. It is a report tool, not agent state.
