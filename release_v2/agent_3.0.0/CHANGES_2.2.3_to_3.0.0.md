# Agent 2.2.3 → 3.0.0 (with backend release 3.0)

**Purpose:** one final agent in which reconciliation, not the AlterID cursor, guarantees FieldTrack = Tally.
- **Design:** `ARCHITECTURE_3.0.md`.
- **Proof:** `harness/` and `REPORT_3.0.0.md`.

**Status:** nothing here is deployed.
- **Backend:** the changes are on branch `feature/tally-reconciliation` (from `99e40e7`), uncommitted, in the developer checkout.
- **Agent:** the changes are in the working source `tally_sync_agent/`.

## 1. Backend changes (minimum)

| File | Change |
|---|---|
| `app/models/tally_voucher_index.py` (new) | Table `tally_voucher_index`, one row per processed voucher GUID:<br>• `alter_id` (latest)<br>• `voucher_date`<br>• `state` `ACTIVE`/`DELETED`<br>• `company_guid`, `updated_at`<br>• index on (`state`, `voucher_date`) |
| `alembic/versions/r3c0n1d2x3y4_tally_voucher_index.py` (new, revises `j3d4e5f6a7b8`) | Creates the table and backfills it from the rows FieldTrack already holds (invoices, payments, adjustments with a voucher GUID):<br>• `MAX(alter_id)`<br>• `MIN(date)`<br>• `ACTIVE` if any row is active<br>Additive: no existing row changes. Downgrade drops the table. |
| `app/services/tally_v2_sync.py` | • `_index_voucher()`: an upsert that never lowers the AlterID, written in the same savepoint as the voucher's rows, on both the excluded path and the normal path (so a failed voucher is never indexed).<br>• `_finish_manifest` also marks absent index rows of the window `DELETED` (count reported as `details.index_deleted`; the existing `retired` counts are unchanged).<br>• **Defect fix (pre-existing, found by the harness):** new `relink_receipts_of_invoices()`, called whenever invoices are retired (cancelled, deleted by manifest, re-classified). Every Tally receipt linked to a retired invoice is linked again from its stored bill allocations to the invoice Tally still holds under that bill name (bill numbers restart each FY), or left unlinked. Before, the receipt kept pointing at the retired row and the live invoice showed as unpaid.<br>• New `reconcile()` (read-only; 409 `ReconcileCompanyMismatch` when the company differs from the agent's bound company). |
| `app/schemas/tally_sync_v2.py` | `ReconcileEntry`, `ReconcileBatch` (at most 50,000 entries per call), `ReconcileResult` |
| `app/api/v1/tally_integration.py` | `POST /api/v1/integrations/tally/sync/reconcile`: agent-authenticated, read-only |
| `app/models/__init__.py` | Exports the model |
| `scripts/tally_v2_cutover.py`, `scripts/preflight_db_revision.py`, `tests/test_outlet_ledgers_v21.py` | Know the new head revision |
| `tests/test_tally_reconcile.py` (new) | 10 tests:<br>• a receipt is relinked when its invoice is cancelled / deleted (2 cases)<br>• rowless vouchers are indexed<br>• missing / stale / extra<br>• a resend fixes stale; an older copy never lowers the index<br>• a failed voucher stays missing<br>• the manifest marks `DELETED`; a restored voucher is missing again<br>• re-dating moves the date<br>• company isolation<br>• authentication |

**Unchanged:**
- the voucher, ledger, bills and manifest contracts (the agent 2.2.x payloads are accepted as before)
- GUID idempotency
- the `STALE_VERSION` skip
- the 50% manifest floor
- authentication and HTTPS

The working tree also holds unrelated, older modifications. They are **not** part of this release:
- `.github/workflows/keep_alive.yml`
- `USER_MANUAL.md`
- `deploy/ovh-vps/README.md`
- android `build.gradle.kts`
- web `.gitignore`

## 2. Agent changes (2.2.3 → 3.0.0)

| File | +/− lines | Change |
|---|---|---|
| `engine/sync_engine_v2.py` | +348 −142 | **Fast path:** the checkpoint becomes the highest AlterID read (no quarantine cap).<br>**Removed:** post-dated register, future scan, one-time catch-up.<br>**New:**<br>• `_window_entries` (headers only, validated, day fallback)<br>• `repair` (affected dates only, AlterID-narrowed)<br>• `reconcile_window`, `_retire_window_extras` (local floor)<br>• `hourly_reconcile`, `nightly_reconcile` (month by month, resumable, one full-FY manifest)<br>• `reconcile_if_due`, `_rebuild_invalid_checkpoint`<br>**Changed:**<br>• `run_sync`: corrupt checkpoint → fast path paused, nightly runs, checkpoint rebuilt<br>• `nightly_reconcile`: a checkpoint above Tally's highest AlterID is lowered to it (`CHECKPOINT_AHEAD_CORRECTED`; found by the harness — before, such a checkpoint silently skipped every later edit until reconciliation caught it)<br>• `historical_step`: weekly nightly reconcile instead of a bare manifest<br>• first-load state, approval and validation result in SQLite<br>• injectable `now` / `clock_hour` |
| `core/state_store.py` (new) | +97 | `KvStore`: table `agent_kv` in `data/sync_agent.db`, with migration of the 2.2.x JSON files (renamed `*.migrated-3.0`, kept) |
| `core/tally_guard.py` | +19 −3 | Circuit breaker persisted in SQLite (key `tally_breaker`, migrates `tally_breaker.json`) |
| `core/backend_client.py` | +13 −69 | `sync_reconcile()`.<br>Removed: v1 `sync_customers` / `sync_invoices` / `sync_payments`, and write-back `get_pending_writeback_jobs` / `ack_writeback_job` / `fail_writeback_job`.<br>The dry-run backend answers reconcile with nothing to compare. |
| `core/tally_client.py` | +1 −735 | Removed all write-back code. Only Export requests remain. |
| `core/agent_state.py`, `core/heartbeat.py` | +15 −6 | Health stream `reconcile`; the health copy is written to SQLite (`agent_health`) |
| `core/checkpoint_manager.py` | +3 −2 | Injectable clock (used by the replay harness only) |
| `config/settings.py` | +8 −7 | Version 3.0.0.<br>Added: `RECONCILE_HOURLY_MINUTES` (60), `RECONCILE_HOURLY_DAYS` (31), `RECONCILE_NIGHTLY_HOUR` (1).<br>Removed: `TALLY_WRITEBACK_ENABLED`, `MANIFEST_INTERVAL_HOURS`. |
| `config/fiscal.py` | +10 | Checkpoint names `reconcile_hourly_v3[@fy]`, `reconcile_nightly_v3[@fy]` |
| `main.py` | +36 −11 | **`status`:** reads health from SQLite and shows approvals, nightly progress and Tally telemetry.<br>**`approve-first-load`:** records the approval in SQLite.<br>**New `withdraw-first-load`.** |
| `extractors/ledger_fields.py` (new) | +256 | `DMS_REGEX`, `_first_text`, `parse_zone_and_area`, moved unchanged from the removed v1 `customer_extractor` |
| `extractors/v2_extractors.py` | +1 −1 | Imports from `ledger_fields` |
| `deploy/env.template` | +9 −5 | Reconciliation settings; write-back and manifest-interval lines removed |
| `tests/test_3_0_reconcile.py` (new) | +363 | 20 tests (incl. checkpoint-ahead correction): the three paths; M1, M4, R5, R6 under the new model; safety floors; checkpoint faults; scheduling |
| `tests/test_ledger_inspection.py` (new) | +32 | The ledger-inspection test kept from the removed v1 stage-3 module |
| Existing tests | | Updated to the 3.0 semantics:<br>• quarantine no longer caps<br>• state in SQLite<br>• nightly instead of the daily manifest<br>• the backend doubles answer reconcile |

## 3. Removed code (verified: no 3.0 dependency)

**How this was verified:**
- Every removed module was moved out first.
- Then the daemon, `sync`, `dry-run`, `validate-fy`, `inspect-ledgers`, `status` and `health` imports were loaded.
- Then the full agent suite was run: 228 passed, 1 skipped (229 passed, 1 skipped after the checkpoint-ahead test was added).
- The only things 3.0 still used from removed modules were moved, not deleted:
  - `_safe_checkpoint_alter_id`: no longer needed
  - the three ledger-field helpers: now in `ledger_fields.py`

| Removed | Lines | What it was |
|---|---|---|
| `engine/sync_engine.py` | 442 | v1 engine: customer / invoice / payment streams and the write-back job loop |
| `engine/full_extraction.py` | 245 | v1 `sync --full` report |
| `extractors/invoice_extractor.py` | 218 | v1 invoice extractor |
| `extractors/payment_extractor.py` | 177 | v1 payment extractor |
| `extractors/customer_extractor.py` | 384 | v1 customer extractor (its 3 helpers moved to `ledger_fields.py`) |
| `transformers/normalizer.py` (+ package) | 72 | v1 normaliser |
| `validators/data_validator.py` (+ package) | 99 | v1 validator |
| `service_runner.py`, `install_service.ps1` | 131 | v1 Python-script service (the exe installer `deploy/install_agent.ps1` is the only installer) |
| `core/deferred_store.py` | 132 | 2.2.3 post-dated register (M4); reconciliation replaces it |
| `core/tally_client.py`, lines 175–875 | 735 | Write-back: `build_receipt_xml`, `import_receipt`, `import_sales_order`, `delete_voucher_by_guid_or_number`, marker lookups |
| `core/backend_client.py` v1 / write-back methods | 69 | See §2 |
| Tests of the removed code | 1,594 | `test_2_2_3.py` (register; replaced by `test_3_0_reconcile.py`), `test_cancelled_voucher_filtering.py`, `test_checkpoint_safety.py`, `test_e2e_agent_sync.py`, `test_stage3_extraction.py` (its ledger-inspection test kept), `test_validators.py`, `test_writeback_agent.py`, `test_writeback_gate.py` |

**About 4,300 lines removed in total. The agent is now read-only towards Tally by construction:**
- it contains no Import request builder at all
- the replay Tally refuses anything but an Export, and no request was refused in the harness

## 4. Behaviour changes an operator sees

| Situation | 2.2.3 | 3.0.0 |
|---|---|---|
| A voucher the backend rejects | Quarantined; caps the checkpoint; re-read every 5 min | Quarantined for retry; the checkpoint moves on; reconciliation retries it hourly (31 days) or nightly (FY) |
| A voucher dated in the future | Registered; uploaded on its date | Uploaded on its date by the hourly reconciliation (no register) |
| A deletion in Tally | Retired by the daily manifest | Retired hourly (31-day window) or nightly (the rest of the FY) |
| `CHECKPOINT_INVALID` after a completed load | Agent stops | Fast path pauses; a nightly reconciliation runs at once and rebuilds the checkpoint (`CHECKPOINT_REBUILT` in the log) |
| `CHECKPOINT_INVALID` / zero before any completed load | Agent stops | Unchanged: stops; a first load needs `approve-first-load` |
| `approve-first-load` | Marker file `data\approve_first_load_<fy>.json` | Row in `data\sync_agent.db`; `withdraw-first-load <fy>` withdraws it |
| State files | 4–6 JSON files in `data\` | `data\sync_agent.db` only (old files migrated, renamed `.migrated-3.0`) |
| Backend | Any 2.2-capable release | **Requires release 3.0** (`/sync/reconcile`). Against an older backend, the reconcile call fails with HTTP 404 → `BACKEND_ERROR` for the cycle; the fast path still runs. |
