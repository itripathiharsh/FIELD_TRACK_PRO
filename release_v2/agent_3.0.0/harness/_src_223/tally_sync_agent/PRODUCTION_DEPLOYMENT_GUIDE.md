# FieldTrack Pro — Tally Sync Agent (Phase 1: Read-Only Bridge)
## Production Deployment & Operations Manual

This document provides complete instructions for installing, configuring, registering, running, and maintaining the FieldTrack Pro Tally Sync Agent on a client's Windows machine running TallyPrime.

---

### 1. Architecture Overview
- **Execution Environment**: Runs locally on the Windows machine where TallyPrime is installed.
- **TallyPrime Connection**: Outbound HTTP/XML requests to `http://127.0.0.1:9000` (Localhost only). No public exposure of Tally.
- **FieldTrack Pro Backend**: Outbound HTTPS requests to `https://<backend-domain>/api/v1/integrations/tally`.
- **Inbound Ports**: **0** (Zero inbound ports required. Agent functions purely as an outbound client).
- **Scope**: Strictly **READ-ONLY** (Phase 1). Never creates vouchers, alters ledgers, or modifies Tally data.

---

### 2. Prerequisites
1. **Operating System**: Windows 10, Windows 11, Windows Server 2016/2019/2022.
2. **Python**: Python 3.10, 3.11, or 3.12 (Add to PATH during installation).
3. **TallyPrime Configuration**:
   - TallyPrime must be running with ODBC/HTTP XML Server enabled on port 9000.
   - Verify in Tally: `F1 (Help) > Settings > Connectivity > Client/Server configuration > TallyPrime acts as: Both/Server` and `Port: 9000`.
   - The target company must be loaded.

---

### 3. Installation Steps

1. **Copy the Agent Folder**:
   Copy the `tally_sync_agent` folder to a permanent path on the Tally machine, for example:
   ```cmd
   C:\FieldTrackPro\tally_sync_agent
   ```

2. **Install Dependencies**:
   Open Command Prompt (`cmd.exe`) or PowerShell:
   ```cmd
   cd C:\FieldTrackPro
   python -m pip install -r tally_sync_agent\requirements.txt
   ```

3. **Configure Environment Variables**:
   Copy `.env.example` to `.env`:
   ```cmd
   copy tally_sync_agent\.env.example tally_sync_agent\.env
   ```

---

### 4. Agent Registration & Provisioning

Before the Agent can sync, register it in FieldTrack Pro to generate unique cryptographic API credentials:

1. **Via Admin Web Dashboard or API**:
   Make a POST request to `/api/v1/integrations/tally/agents` with admin authentication:
   ```json
   {
     "name": "Headquarters Tally Machine",
     "organization_id": "<client_organization_id>",
     "tally_company_name": "<Tally_Company_Name>",
     "tally_company_guid": "<Optional_Guid>"
   }
   ```
2. **Receive Credentials**:
   The response returns:
   - `agent.id`: UUID (e.g. `c6376299-28cc-470d-8b2b-19d27a8ac1cb`)
   - `api_key`: Secret Token (e.g. `ft_agent_...`)

3. **Update `.env`**:
   Populate `tally_sync_agent\.env` with:
   ```ini
   TALLY_URL=http://127.0.0.1:9000
   TALLY_TIMEOUT_SECONDS=180
   BACKEND_URL=https://api.fieldtrackpro.com
   BACKEND_TIMEOUT_SECONDS=60

   AGENT_ID=<agent_uuid>
   AGENT_KEY=<raw_api_key>
   ORGANIZATION_ID=<client_org_id>

   BATCH_SIZE=100
   SYNC_INTERVAL_SECONDS=300
   HEARTBEAT_INTERVAL_SECONDS=60
   LOG_LEVEL=INFO
   ```

---

### 5. Verification Commands

Run the built-in diagnostic tools to confirm all connectivity:

1. **Test Tally Connection**:
   ```cmd
   python -m tally_sync_agent.main test-tally
   ```
   *Expected*: `STATUS: PASS` with detected company name.

2. **Test Cloud Backend Connection**:
   ```cmd
   python -m tally_sync_agent.main test-backend
   ```
   *Expected*: `STATUS: PASS` with server timestamp.

3. **Execute Initial Historical Synchronization**:
   ```cmd
   python -m tally_sync_agent.main sync --initial
   ```
   *Expected*: `SYNC_CYCLE_FINISHED status=COMPLETED`.

4. **Check Status & Checkpoints**:
   ```cmd
   python -m tally_sync_agent.main status
   ```

---

### 6. Running in Production (Daemon / Service)

#### Option A: Running via Windows Task Scheduler (Recommended for standard Windows)
Create a scheduled task that starts at Windows startup and runs indefinitely:
1. Open **Task Scheduler** > **Create Task**.
2. **General**: Name `FieldTrack_TallySyncAgent`, check *Run whether user is logged on or not*.
3. **Triggers**: *At startup* (or *At log on*).
4. **Actions**:
   - Action: *Start a program*
   - Program: `python.exe` (or `pythonw.exe` for hidden window)
   - Arguments: `-m tally_sync_agent.main daemon`
   - Start in: `C:\FieldTrackPro`
5. **Settings**: Check *Restart if task fails*, uncheck *Stop task if it runs longer than*.

#### Option B: Running as Windows Service via NSSM
1. Download NSSM (Non-Sucking Service Manager).
2. Install service:
   ```cmd
   nssm install FieldTrackTallySync "C:\Python311\python.exe" "-m tally_sync_agent.main daemon"
   nssm set FieldTrackTallySync AppDirectory "C:\FieldTrackPro"
   nssm set FieldTrackTallySync Start SERVICE_AUTO_START
   nssm start FieldTrackTallySync
   ```

---

### 7. File Locations & Persistence

All persistent operational data is stored in `tally_sync_agent/data/`:
- **Checkpoints & Retry DB**: `tally_sync_agent/data/sync_agent.db` (SQLite)
  - Records highest Alter IDs and sync timestamps.
  - Holds durable retry queue for network outage survivability.
- **Log Files**: `tally_sync_agent/data/sync_agent.log`
  - Rotated, sanitized log entries.
  - Automatically redacts passwords, tokens, and API keys.

---

### 8. Troubleshooting Guide

| Issue | Root Cause | Solution |
|---|---|---|
| `TALLY_UNAVAILABLE` or `[WinError 10061]` | TallyPrime is not running or port 9000 is disabled. | Start TallyPrime. Press `F1 > Settings > Connectivity > Client/Server configuration`, ensure Server is enabled on port 9000. |
| `NO_COMPANY_LOADED` | Tally is running on port 9000, but no company is opened. | Open and log into the client company in TallyPrime. |
| `timed out communicating with Tally` | Tally database is very large (hundreds of megabytes) and collection generation takes >30s. | Set `TALLY_TIMEOUT_SECONDS=180` in `.env`. |
| `BackendAuthError (401/403)` | Invalid `AGENT_ID` or `AGENT_KEY`. | Verify `.env` credentials match the registration record in FieldTrack Admin. |
| `BackendServerError (500/502)` | Network drop or server maintenance. | No action required. Agent enqueues payloads in `sync_agent.db` and automatically flushes on server recovery. |
| `Duplicate check assertions` | N/A | Agent and backend use deterministic upserts (`outlet_code`, `invoice_number`, `source_reference`) ensuring 0 duplicates on repeat syncs. |
