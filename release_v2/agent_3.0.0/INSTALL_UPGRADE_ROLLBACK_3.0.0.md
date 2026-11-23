# Agent 3.0.0 + backend release 3.0: upgrade, rollback, recovery

**Nothing in this guide has been executed on production, on the client's VM, or on staging.** Every step on those systems needs your separate approval. This follows the deployment boundary of the 3.0 approval:
- no production financial data was touched
- no credentials changed
- no checkpoints reset
- no agent started
- nothing installed on the VM
- no first load run
- no backend deployed

## 0. Order of operations

The agent depends on the backend, so:

1. Backend release 3.0 (migration `r3c0n1d2x3y4`) on **staging**.
2. Agent 3.0.0 on the **staging** agent (H1).
3. H2 scenario test on a test copy.
4. Production backend.
5. Production agent.

**The backend is backward compatible:**
- 2.2.x agents keep working against it unchanged
- the new table is additive
- the new endpoint is used only by 3.0

**Agent 3.0 against a pre-3.0 backend:**
- every reconcile call returns HTTP 404, and the cycle ends with `BACKEND_ERROR`
- the fast path still uploads
- never run it that way on purpose

## 1. Package check (any machine)

```powershell
$Zip = 'C:\3.0.0\FieldTrack_TallyAgent_Production_v3.0.0.zip'
(Get-FileHash $Zip -Algorithm SHA256).Hash            # must equal SHA256SUMS.txt in the release folder
Expand-Archive $Zip -DestinationPath 'C:\3.0.0' -Force
Set-Location 'C:\3.0.0\FieldTrack_TallyAgent_Production_v3.0.0'
(Get-FileHash .\FieldTrackTallyAgent.exe -Algorithm SHA256).Hash   # must equal VERSION.txt
if (Test-Path .\.env) { throw 'Unexpected .env in the package - STOP' }
.\FieldTrackTallyAgent.exe --help                     # lists withdraw-first-load (3.0)
```

## 2. Backend release 3.0 (staging first; production only after approval)

```bash
# on the server, in the backend checkout, after taking the usual pg_dump backup
git fetch && git checkout <release-3.0 commit>          # branch feature/tally-reconciliation once reviewed and merged
alembic upgrade head                                     # j3d4e5f6a7b8 -> r3c0n1d2x3y4: creates + backfills tally_voucher_index
python scripts/preflight_db_revision.py                  # must report tally_voucher_index
sudo systemctl restart fieldtrack-backend                # (the service name used for 99e40e7)
```

**What the migration does and does not do:**
- It writes only the new table.
- Its backfill indexes every voucher GUID that already has an invoice, payment or adjustment row.
- Vouchers that left no row (purchases, contras, cancelled ones) are not known yet. The first nightly reconciliation of an upgraded agent reports them missing **once** and re-sends them **once**: idempotent, no new invoice or payment rows. After that the index is complete.

**Rollback:**

```bash
alembic downgrade j3d4e5f6a7b8     # drops tally_voucher_index only; no other table is touched
```

## 3. Agent upgrade (STAGING agent, H1; needs approval)

Same procedure as 2.2.3 §3. The installer:
- keeps `.env` and `data\`
- makes its own quiescent backup
- restarts the task

```powershell
Set-Location 'C:\3.0.0\FieldTrack_TallyAgent_Production_v3.0.0'
$Stg = 'C:\FieldTrackAgent_STAGING'
$Safe = "C:\FieldTrack_Staging_Rollback_$(Get-Date -Format yyyyMMdd-HHmmss)"
New-Item -ItemType Directory -Force $Safe | Out-Null
Copy-Item "$Stg\FieldTrackTallyAgent.exe" "$Safe\FieldTrackTallyAgent_previous.exe"
Copy-Item "$Stg\data" "$Safe\data_before_3.0.0" -Recurse
Copy-Item "$Stg\.env" "$Safe\env_before_3.0.0"
powershell -ExecutionPolicy Bypass -File .\install_agent.ps1 -InstanceName STAGING -WhatIf
powershell -ExecutionPolicy Bypass -File .\install_agent.ps1 -InstanceName STAGING
```

**What the first 3.0 cycle does:**
- **State migration:** it moves the JSON state into `data\sync_agent.db`. The files are renamed `*.migrated-3.0` and kept.
- **Fast path:** it continues the existing checkpoint incrementally.
- **Hourly reconcile:** it runs at once, because it has never run (2 header requests).
- **Nightly reconcile:** the first one runs after 01:00 IST.

**Expected one-time extra load on the first nightly:** one AlterID-narrowed day request per date that holds a never-indexed rowless voucher (see §2).

**Check:**

```powershell
& "$Stg\FieldTrackTallyAgent.exe" status
Select-String "$Stg\data\sync_agent.log" -Pattern 'RECONCILE |RECONCILE_NIGHTLY|STATE_MIGRATED|CHECKPOINT_REBUILT' | Select-Object -Last 20 | ForEach-Object Line
```

**Watch for:**
- `RECONCILE ... missing=0 stale=0 extra=0` on consecutive hours
- the backend admin reconciliation page shows zero differences

## 4. Production agent (documented only; needs your separate approval)

**Production facts:**
- the production identity still reports 2.1.0
- its checkpoint is `vouchers_v2` = 0, an empty completion

**So 3.0 behaves exactly like 2.2.3 on the first cycle:**
- **`CHECKPOINT_ZERO`**: no voucher request
- **first load:** only after `approve-first-load 2026-27`

The 3.0 first load is the proven 2.2.x day-by-day load:
- day-scoped lean requests
- resumable
- ledger snapshot checked against Group Summary
- manifest

**The 3.0 first load indexes every voucher. Reconciliation then starts from a complete index:**
- no backfill pass
- the nightly clock starts at the end of the load

**The rest is the 2.2.3 guide, §5 P1–P6, with these differences:**
- the package is `v3.0.0`
- the backend must already be on release 3.0
- the rollback target remains **STOPPED**. Never run 2.1.0 again with checkpoint 0 (B10).

## 5. Rollback (agent)

```powershell
$Dir = 'C:\FieldTrackAgent_STAGING'        # or the production folder
$Safe = (Get-ChildItem C:\ -Directory -Filter 'FieldTrack_*_Rollback_*' | Sort-Object Name -Descending | Select-Object -First 1).FullName
Stop-ScheduledTask -TaskName FieldTrack_TallySyncAgent_STAGING
Get-CimInstance Win32_Process -Filter "Name='FieldTrackTallyAgent.exe'" | Where-Object { $_.ExecutablePath -like "$Dir\*" } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
Copy-Item "$Safe\FieldTrackTallyAgent_previous.exe" "$Dir\FieldTrackTallyAgent.exe" -Force
Remove-Item "$Dir\data" -Recurse -Force; Copy-Item "$Safe\data_before_3.0.0" "$Dir\data" -Recurse
Start-ScheduledTask -TaskName FieldTrack_TallySyncAgent_STAGING      # production: leave STOPPED
```

**After a rollback, the restored `data\` is the 2.2.x state exactly:**
- its JSON files
- its checkpoints
- its post-dated register

**Returning to 3.0 later is safe.** This was proven in the harness: day 68 ran 2.2.3 for three cycles on the same folder, then 3.0 again.
- Anything the older version did not see (a post-dated voucher, a deletion, a missed edit) is found by the first 3.0 reconciliation.
- Nothing is duplicated.

**If `data\` was not restored (exe swapped only):**
- 2.2.x does not find its renamed JSON files
- it still runs incrementally from the shared checkpoint table
- rename `*.migrated-3.0` back to restore its first-load / breaker state

## 6. Recovery situations (3.0)

| Situation | What happens / what to do |
|---|---|
| `TALLY_UNAVAILABLE`, `TALLY_COOLDOWN` | Nothing to do. The breaker waits and probes. A nightly run that was cut off resumes from the last completed month (`status` shows "Nightly reconciliation in progress"). |
| `BACKEND_ERROR` | Uploads go to the retry queue. The next reconciliation repairs anything still missing. |
| `CHECKPOINT_INVALID` after a completed load | The fast path pauses, a nightly reconciliation runs in the same cycle, and the checkpoint is rebuilt from it (`CHECKPOINT_REBUILT`). Send the log so the cause of the corruption is understood. |
| `CHECKPOINT_INVALID` / `CHECKPOINT_ZERO` before any completed load | Stops, as in 2.2.x. The first load needs `approve-first-load`. |
| `RECONCILE_RETIRE_REFUSED` | Tally listed far fewer vouchers for the hourly window than FieldTrack holds, so nothing was retired. The nightly full-FY manifest decides, with its own floors. If it repeats, check Tally (wrong company, partial data). |
| `QUARANTINE_STALE` | A voucher has been rejected for more than 24 h. It is retried by every reconciliation; fix the cause (usually a ledger mapping). |
| `withdraw-first-load <fy>` | Withdraws an approval given by mistake, before the first load starts |
