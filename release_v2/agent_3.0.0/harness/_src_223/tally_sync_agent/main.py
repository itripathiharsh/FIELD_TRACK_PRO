import argparse
import json
import sys
import time
from datetime import datetime

from tally_sync_agent.config.settings import settings, AGENT_VERSION, BASE_DIR, DATA_DIR, InstanceConfigError, instance_config
from tally_sync_agent.core.agent_state import AgentState, build_health
from tally_sync_agent.core.heartbeat import HeartbeatThread
from tally_sync_agent.core.quarantine_store import QuarantineStore
from tally_sync_agent.core.backend_client import BackendClient
from tally_sync_agent.core.checkpoint_manager import CheckpointManager
from tally_sync_agent.core.logger import logger
from tally_sync_agent.core.retry_queue import RetryQueue
from tally_sync_agent.core.single_instance import SingleInstanceLock
from tally_sync_agent.core.tally_client import TallyClient, TallyConnectionError
from tally_sync_agent.engine.sync_engine_v2 import BalanceCheckFailed, InitialLoadEmpty, ManifestRejected, SyncEngineV2
from tally_sync_agent.engine.multi_fy import MultiFySync


STATE_FILE = DATA_DIR / "agent_state.json"


def _instance_or_exit() -> dict:
    """Validates AGENT_INSTANCE_NAME / backend combination before anything talks to the backend."""
    try:
        return instance_config(settings)
    except InstanceConfigError as ex:
        logger.error(f"INSTANCE_CONFIG_REFUSED {ex}")
        print(f"Refusing to start: {ex}")
        sys.exit(2)


def cmd_test_tally(args):
    """Test local TallyPrime connectivity."""
    print("========================================")
    print("Testing TallyPrime Local Connectivity...")
    print(f"Target Endpoint: {settings.tally_url}")
    print("========================================")
    client = TallyClient()
    try:
        info = client.get_company_info()
        if info and info.get("error"):
            print(f"STATUS: FAIL ({info['error']})")
            print(f"Loaded companies: {info.get('companies')}   expected GUID: {settings.expected_company_guid}")
        elif info and info.get("name"):
            print("STATUS: PASS")
            print(f"Company Detected: {info['name']}")
            print(f"Company GUID:     {info.get('guid')}")
            print(f"Starting Date:    {info.get('starting_date')}")
            print(f"Ending Date:      {info.get('ending_date')}")
            print(f"Books From:       {info.get('books_from')}")
        else:
            print("STATUS: WARNING")
            print("Connected to Tally port 9000, but no active company is currently loaded.")
            print("Please open and log into the company inside TallyPrime.")
    except Exception as ex:
        print("STATUS: FAIL")
        print(f"Error: {ex}")


def cmd_test_backend(args):
    """Test FieldTrack Pro Cloud / Backend connectivity."""
    _instance_or_exit()
    print("========================================")
    print("Testing FieldTrack Pro Backend...")
    print(f"Backend URL: {settings.backend_url}")
    print(f"Agent ID:    {settings.agent_id}")
    print("========================================")
    client = BackendClient()
    try:
        res = client.heartbeat(
            agent_version=AGENT_VERSION,
            tally_status="TESTING",
            checkpoints={},
        )
        print("STATUS: PASS")
        print(f"Response: {res}")
    except Exception as ex:
        print("STATUS: FAIL")
        print(f"Error: {ex}")


def cmd_status(args):
    """Show local sync state, checkpoints, and pending retry queue."""
    checkpoints = CheckpointManager()
    retry_queue = RetryQueue()

    print("========================================")
    print("FieldTrack Pro - Tally Sync Agent Status")
    print("========================================")
    print(f"Tally URL:       {settings.tally_url}")
    print(f"Backend URL:     {settings.backend_url}")
    print(f"Agent ID:        {settings.agent_id}")
    print(f"Batch Size:      {settings.batch_size}")
    print(f"Sync Interval:   {settings.sync_interval_seconds}s")
    print(f"Pending Retries: {retry_queue.count_pending()}")
    try:
        inst = instance_config(settings)["instance"]
    except InstanceConfigError as ex:
        inst = f"INVALID ({ex})"
    print(f"Instance:        {inst}")
    print(f"Agent Version:   {AGENT_VERSION}")
    print(f"Sync Interval:   {settings.sync_interval_seconds}s   Heartbeat: {settings.heartbeat_interval_seconds}s")
    q = retry_queue.health_stats()
    age = "-" if q["oldest_age_seconds"] is None else f"{q['oldest_age_seconds']}s"
    print(f"Retry Queue:     pending={q['pending']} oldest_age={age} "
          f"max_attempts={q['max_attempts']} rejected_4xx={q['rejected_4xx']}")
    if q["last_error"]:
        print(f"  last error:    {q['last_error']}")
    quarantine = QuarantineStore()
    print(f"Quarantine:      unresolved={quarantine.count_unresolved('vouchers')} (live FY)  all FYs={quarantine.count_unresolved()}")
    print(f"Financial years: configured={settings.financial_years}  history_upload={settings.history_upload or 'none (disabled)'}")
    if STATE_FILE.exists():
        try:
            saved = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            h = saved.get("health") or {}
            print(f"\nLast health (written by the running daemon at {saved.get('written_at')}):")
            print(f"  Phase:         {h.get('phase')} {h.get('phase_detail') or ''}")
            print(f"  Last cycle:    {h.get('last_cycle_status')} at {h.get('last_cycle_completed_at')} "
                  f"({h.get('last_cycle_duration_seconds')}s)")
            for stream, ts in (h.get("last_success") or {}).items():
                print(f"  Last success:  {stream:<9} {ts}")
            if h.get("last_error"):
                print(f"  Last error:    {h['last_error'].get('at')} {h['last_error'].get('message')}")
        except Exception as ex:
            print(f"(could not read {STATE_FILE}: {ex})")
    else:
        print("\nNo daemon health written yet (daemon not running on this install, or never started).")
    print("\nCheckpoints:")
    all_cp = checkpoints.get_all_checkpoints()
    if not all_cp:
        print("  No checkpoints recorded yet (Initial sync pending).")
    else:
        for entity, data in all_cp.items():
            print(f"  [{entity.upper()}]:")
            print(f"    Last Sync Date: {data.get('last_sync_date')}")
            print(f"    Last Alter ID:  {data.get('last_alter_id')}")
            print(f"    Total Records:  {data.get('total_synced_records')}")
            print(f"    Last Sync At:   {data.get('last_successful_sync_at')}")


def cmd_sync(args):
    """Execute one sync cycle. 2.2.1: refuses while this instance's daemon runs (no overlapping cycles, item 11);
    a first load still needs `approve-first-load` (item 1)."""
    inst = _instance_or_exit()
    lock = SingleInstanceLock(inst["mutex"])
    if not lock.acquire():
        print("The agent daemon of this instance is running: a manual sync would overlap it. Nothing was done.")
        sys.exit(2)
    try:
        print("Starting synchronization run...")
        if args.initial:
            results = SyncEngineV2().run_sync(is_initial=True)  # live FY only
        else:
            results = MultiFySync().run_cycle()
        print(json.dumps(results, indent=2, default=str))
    finally:
        lock.release()


def cmd_approve_first_load(args):
    """Item 1: a zero / missing voucher checkpoint stops the agent. This EXPLICIT command allows the bounded,
    resumable, day-by-day first load of the LIVE FY. It writes data/approve_first_load_<fy>.json (who, when,
    the checkpoint it saw) and changes nothing else: no checkpoint, no .env, no request to Tally."""
    import getpass
    import socket
    from tally_sync_agent.config.fiscal import build_contexts, ist_today
    ctx = build_contexts(settings.financial_years, settings.sync_from_date, settings.history_upload, ist_today())
    live = ctx["live"]
    if args.fy != live.label:
        print(f"Refusing: {args.fy} is not the live FY ({live.label}). Historical FYs are loaded only via HISTORY_UPLOAD "
              "and the backend's history_safe interlock.")
        sys.exit(2)
    engine = SyncEngineV2(fy=live)
    status = engine.checkpoint_status()
    cp = engine.checkpoints.get_checkpoint(live.cp_vouchers)
    if status == "OK":
        print(f"Refusing: FY {live.label} has a valid voucher checkpoint (AlterID {cp.get('last_alter_id')}); no first load is needed.")
        sys.exit(2)
    if status.startswith("INVALID"):
        print(f"Refusing: FY {live.label} checkpoint is {status}. It must be investigated, not overwritten by a load.")
        sys.exit(2)
    marker = DATA_DIR / f"approve_first_load_{live.label}.json"
    rec = {"fy": live.label, "approved_at": datetime.now().astimezone().isoformat(), "by": getpass.getuser(),
           "machine": socket.gethostname(), "checkpoint_status": status, "checkpoint_seen": cp, "agent_version": AGENT_VERSION}
    marker.write_text(json.dumps(rec, indent=1, default=str), encoding="utf-8")
    logger.warning(f"FIRST_LOAD_APPROVED {json.dumps(rec, default=str)}")
    print(f"First load of FY {live.label} approved (checkpoint status {status}). Marker: {marker}")
    print("The next agent cycle starts the day-by-day first load. Delete the marker before that to withdraw the approval.")


def cmd_dry_run(args):
    """Read Tally exactly as a real full load would, but write every payload to JSON files
    instead of uploading. Uses its own checkpoint / queue files: the live agent's state,
    the backend and Tally are not changed."""
    from pathlib import Path

    from tally_sync_agent.core.backend_client import DryRunBackend
    from tally_sync_agent.core.quarantine_store import QuarantineStore
    from tally_sync_agent.config.settings import DATA_DIR

    out = Path(args.out) if args.out else DATA_DIR / f"dry_run_{datetime.now():%Y%m%d_%H%M%S}"
    out.mkdir(parents=True, exist_ok=True)
    db = out / "dry_run_state.db"
    engine = SyncEngineV2(
        backend_client=DryRunBackend(out / "payloads"),
        checkpoint_manager=CheckpointManager(db), retry_queue=RetryQueue(db), quarantine_store=QuarantineStore(db),
        data_dir=out,
    )
    print(f"Dry run (nothing is uploaded; Tally is only read). Output: {out}")
    try:
        company = engine.tally.get_company_info()
    except TallyConnectionError as ex:
        print(f"Tally is not reachable: {ex}")
        sys.exit(2)
    if company and company.get("error"):
        print(f"Refusing: {company['error']} (loaded: {company.get('companies')}; expected GUID {settings.expected_company_guid}). "
              "Nothing was read.")
        sys.exit(2)
    if not company or not company.get("name"):
        print("No company is loaded in TallyPrime.")
        sys.exit(2)
    engine.company_name = company["name"]  # sent as SVCURRENTCOMPANY with every collection (R1)
    engine.company_guid = company.get("guid")
    try:
        report = engine.initial_load(company.get("guid"))
    except InitialLoadEmpty as ex:
        print(f"Dry run found NO voucher: {ex}")
        sys.exit(3)
    except BalanceCheckFailed as ex:
        print(f"Dry run STOPPED: {ex}")
        sys.exit(4)
    # R6: a dry run proves extraction only. Nothing was uploaded, so no backend field is reported.
    report = {"upload_status": "NOT_UPLOADED - dry run: payloads written to files; no backend accepted anything",
              **_strip_backend_fields(report),
              "counters_extracted_validated": {k: v for k, v in engine.counters.items()
                                               if k in ("extracted", "validated", "rejected_local", "outside_fy")}}
    report["company"] = {"name": company["name"], "guid": company.get("guid")}
    report["quarantined"] = engine.quarantine.list_unresolved("vouchers")
    (out / "dry_run_report.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "quarantined"}, indent=2, default=str))
    print(f"Quarantined vouchers: {len(report['quarantined'])}")
    print(f"Report: {out / 'dry_run_report.json'}")


def _strip_backend_fields(obj):
    """Remove what a dry-run 'backend' invents (result / created / updated / retired / manifest details), so
    a dry-run report can never be read as backend acceptance (R6)."""
    drop = {"result", "created", "updated", "retired", "failed", "queued", "sent", "manifest"}
    if isinstance(obj, dict):
        return {k: _strip_backend_fields(v) for k, v in obj.items() if k not in drop}
    if isinstance(obj, list):
        return [_strip_backend_fields(v) for v in obj]
    return obj


def cmd_validate_fy(args):
    """Read-only validation of financial years against Tally (nothing uploaded, no state touched).
    2.2.1: one validation per machine (exclusive lock), guarded requests, responsiveness sampling, --resume."""
    from pathlib import Path
    from tally_sync_agent.config.fiscal import fy_containing, ist_today, parse_fy_list
    from tally_sync_agent.core.tally_guard import ExclusiveJobLock
    from tally_sync_agent.core.tally_responsiveness import ResponsivenessSampler
    from tally_sync_agent.engine.fy_validation import run_validation

    try:  # a Windows console (cp1252) must never turn a passed validation into a crash
        sys.stdout.reconfigure(errors="replace")
    except Exception:
        pass
    job = ExclusiveJobLock()
    if not job.acquire():
        print("Another validate-fy is already running on this machine. Nothing was started.")
        sys.exit(2)
    try:
        fys = parse_fy_list(settings.financial_years if args.fy in (None, "", "all") else args.fy)
        if args.resume:
            out = Path(args.resume)
        else:
            out = Path(args.out) if args.out else DATA_DIR / f"validate_fy_{datetime.now():%Y%m%d_%H%M%S}"
        print(f"READ-ONLY validation of FY {', '.join(f.label for f in fys)}  (full detail: {not args.headers_only}). "
              f"Nothing is uploaded. Output: {out}" + ("  (resuming)" if args.resume else ""))
        sampler = ResponsivenessSampler().start()
        try:
            report = run_validation(fys, out, full=not args.headers_only, pause=settings.day_request_pause_seconds,
                                    sampler=sampler, live_label=fy_containing(ist_today()).label)
        finally:
            sampler.stop()
        print((out / "validation_summary.txt").read_text(encoding="utf-8"))
        print(f"Result: {report.get('result')}")
        sys.exit(0 if report.get("result") == "ALL CHECKS PASSED" else 5)
    finally:
        job.release()


def _new_heartbeat(state: AgentState) -> HeartbeatThread:
    """The heartbeat thread gets its OWN backend client and store objects (fresh SQLite connection
    per call), so nothing it does shares a connection or a lock with the sync loop."""
    return HeartbeatThread(
        state=state, backend=BackendClient(), checkpoints=CheckpointManager(), retry_queue=RetryQueue(),
        quarantine=QuarantineStore(), interval_seconds=settings.heartbeat_interval_seconds,
        agent_version=AGENT_VERSION, state_file=STATE_FILE,
    )


def cmd_daemon(args, max_cycles: int | None = None):
    """
    Run the continuous service: a sync cycle every SYNC_INTERVAL_SECONDS (main thread) and an
    independent heartbeat every HEARTBEAT_INTERVAL_SECONDS (its own thread).

    Guarded by a machine-wide named mutex so only one daemon per instance can run - see
    core/single_instance.py (PyInstaller onefile's bootloader/child split can defeat Task
    Scheduler's own "don't start a new instance" setting). The default instance keeps the
    historical mutex name shared with Agent 1.2.1; a named instance (AGENT_INSTANCE_NAME) has
    its own. max_cycles is for tests only.
    """
    inst = _instance_or_exit()
    lock = SingleInstanceLock(inst["mutex"])
    if not lock.acquire():
        logger.warning(
            "Another FieldTrack Pro Tally Sync Agent daemon instance is already running on this "
            "machine. Exiting immediately without starting heartbeat or sync."
        )
        print("Another daemon instance is already running. Exiting.")
        return

    heartbeat = None
    try:
        logger.info(
            f"Starting FieldTrack Pro Tally Sync Agent Daemon {AGENT_VERSION} instance={inst['instance']} "
            f"folder={BASE_DIR} backend={settings.backend_url} interval={settings.sync_interval_seconds}s "
            f"heartbeat={settings.heartbeat_interval_seconds}s expected_company={settings.expected_company_guid}"
        )
        state = AgentState(instance=inst["instance"], interval_seconds=settings.sync_interval_seconds,
                           agent_version=AGENT_VERSION, secrets=(settings.agent_key or "",))
        engine = MultiFySync(state=state)
        heartbeat = _new_heartbeat(state)
        heartbeat.start()
        last_sync = 0.0
        cycles = 0

        try:
            while True:
                if not heartbeat.is_alive():
                    logger.error("HEARTBEAT_THREAD_DEAD - restarting it")
                    state.record_error("Heartbeat thread stopped unexpectedly and was restarted")
                    heartbeat = _new_heartbeat(state)
                    heartbeat.start()

                now = time.time()
                if now - last_sync >= settings.sync_interval_seconds:
                    state.cycle_start()
                    started = time.time()
                    try:
                        status = engine.run_cycle().get("status", "ERROR")
                    except KeyboardInterrupt:
                        raise
                    except Exception as ex:
                        status = "ERROR"
                        logger.error(f"Daemon sync cycle error: {ex}")
                        state.record_error(f"Sync cycle error: {ex}")
                    state.cycle_end(status, time.time() - started)
                    last_sync = now
                    cycles += 1
                    if max_cycles is not None and cycles >= max_cycles:
                        break

                time.sleep(2)
        except KeyboardInterrupt:
            logger.info("Daemon stopped by user.")
    finally:
        if heartbeat is not None:
            heartbeat.stop()
        # Always released on the way out - graceful stop, KeyboardInterrupt, or any
        # unhandled exception. If the process is killed outright instead (Task Manager,
        # crash, power loss), Windows itself releases the mutex at the OS level
        # regardless of whether this line ever runs.
        lock.release()


def cmd_inspect_ledgers(args):
    """Read-only: which debtor-ledger fields are populated in Tally (counts + masked shapes only)."""
    from tally_sync_agent.engine.ledger_inspection import inspect_debtor_ledgers

    try:
        report = inspect_debtor_ledgers(TallyClient())
    except TallyConnectionError as ex:
        print(f"Tally is not reachable: {ex}")
        sys.exit(2)
    print(f"Debtor ledgers inspected: {report['ledger_count']} (fetch: {report['fetch_method']})")
    for path, info in report["fields"].items():
        shapes = ", ".join(s["shape"] for s in info["top_shapes"][:3])
        print(f"  {path}: {info['ledgers_with_value']}  [{shapes}]")
    print(f"Report: {report['report_path']}")


def cmd_health(args):
    """Run full health check across Tally, Agent, checkpoints, retry queue, and Backend."""
    _instance_or_exit()
    checkpoints = CheckpointManager()
    retry_queue = RetryQueue()
    tally = TallyClient()
    backend = BackendClient()

    print("========================================")
    print("FieldTrack Pro - Tally Sync Agent Health")
    print("========================================")
    print("Agent Status:     ONLINE")
    print(f"Agent Version:    {AGENT_VERSION}")
    print(f"Agent ID:         {settings.agent_id}")
    print(f"Organization ID:  {settings.organization_id}")

    c_info = None
    try:
        c_info = tally.get_company_info()
        if c_info and c_info.get("name"):
            print("Tally Status:     CONNECTED")
            print(f"Active Company:   {c_info['name']}")
            print(f"Company GUID:     {c_info.get('guid', 'N/A')}")
        else:
            print("Tally Status:     CONNECTED (No Company Loaded)")
    except Exception as ex:
        print(f"Tally Status:     OFFLINE ({ex})")

    try:
        backend.heartbeat(
            agent_version=AGENT_VERSION,
            tally_status="ONLINE" if (c_info and c_info.get("name")) else "OFFLINE",
            company_name=c_info.get("name") if c_info else None,
            company_guid=c_info.get("guid") if c_info else None,
            checkpoints=checkpoints.get_all_checkpoints(),
        )
        print("Backend Status:   CONNECTED")
    except Exception as ex:
        print(f"Backend Status:   OFFLINE ({ex})")

    pending = retry_queue.count_pending()
    print(f"Pending Retries:  {pending}")

    all_cp = checkpoints.get_all_checkpoints()
    last_sync = None
    for entity, data in all_cp.items():
        ts = data.get("last_successful_sync_at")
        if ts and (last_sync is None or ts > last_sync):
            last_sync = ts
    print(f"Last Sync Time:   {last_sync or 'None'}")
    for entity, data in all_cp.items():
        print(f"  [{entity.upper()}]: AlterID={data.get('last_alter_id')} TotalRecords={data.get('total_synced_records')}")


def main():
    parser = argparse.ArgumentParser(description="FieldTrack Pro - Tally Sync Agent (Local Bridge)")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # test-tally
    subparsers.add_parser("test-tally", help="Test local TallyPrime connectivity")

    # test-backend
    subparsers.add_parser("test-backend", help="Test FieldTrack Pro cloud backend connectivity")

    # status
    subparsers.add_parser("status", help="Show checkpoints and local sync status")

    # health
    subparsers.add_parser("health", help="Run comprehensive health and connectivity check")

    # sync
    sync_parser = subparsers.add_parser("sync", help="Execute a sync cycle")
    sync_parser.add_argument("--initial", action="store_true", help="Force the full load (resumable)")

    # dry-run
    dry = subparsers.add_parser("dry-run", help="Full read of Tally written to JSON files; nothing is uploaded")
    dry.add_argument("--out", help="Output folder (default: data/dry_run_<timestamp>)")

    # inspect-ledgers
    subparsers.add_parser("inspect-ledgers", help="Read-only report of which debtor-ledger fields Tally populates")

    # validate-fy (2.2.0)
    vfy = subparsers.add_parser("validate-fy", help="READ-ONLY validation of financial years against Tally; nothing is uploaded")
    vfy.add_argument("--fy", help="e.g. 2025-26 or 2024-25,2025-26 (default: all FINANCIAL_YEARS)")
    vfy.add_argument("--headers-only", action="store_true", help="skip the day-by-day full-detail read and reconciliation")
    vfy.add_argument("--out", help="Output folder (default: data/validate_fy_<timestamp>)")
    vfy.add_argument("--resume", help="Continue an interrupted validation in this output folder")

    # approve-first-load (2.2.1)
    afl = subparsers.add_parser("approve-first-load", help="Explicitly allow the day-by-day first load of the live FY")
    afl.add_argument("fy", help="the live FY label, e.g. 2026-27")

    # daemon
    subparsers.add_parser("daemon", help="Run sync agent as a background daemon")

    args = parser.parse_args()

    if args.command == "test-tally":
        cmd_test_tally(args)
    elif args.command == "test-backend":
        cmd_test_backend(args)
    elif args.command == "status":
        cmd_status(args)
    elif args.command == "health":
        cmd_health(args)
    elif args.command == "sync":
        cmd_sync(args)
    elif args.command == "dry-run":
        cmd_dry_run(args)
    elif args.command == "daemon":
        cmd_daemon(args)
    elif args.command == "inspect-ledgers":
        cmd_inspect_ledgers(args)
    elif args.command == "validate-fy":
        cmd_validate_fy(args)
    elif args.command == "approve-first-load":
        cmd_approve_first_load(args)


if __name__ == "__main__":
    main()
