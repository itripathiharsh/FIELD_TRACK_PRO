"""
FieldTrack Pro — Tally Sync Agent Windows Service Runner
Unattended background daemon service that coordinates periodic synchronization,
heartbeats, graceful shutdown handling, and failure auto-recovery.
"""
import os
import sys
import time
import signal
from datetime import datetime

# Ensure project root is in sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from tally_sync_agent.config.settings import settings, AGENT_VERSION
from tally_sync_agent.core.logger import logger
from tally_sync_agent.engine.sync_engine import SyncEngine

running = True

def handle_shutdown(signum, frame):
    global running
    logger.info(f"Shutdown signal received ({signum}). Initiating graceful termination...")
    running = False

def run_service():
    global running
    signal.signal(signal.SIGINT, handle_shutdown)
    signal.signal(signal.SIGTERM, handle_shutdown)

    logger.info("=" * 60)
    logger.info("FieldTrack Pro Tally Sync Service STARTED (Background Daemon)")
    logger.info(f"Target Tally Endpoint: {settings.tally_url}")
    logger.info(f"Backend Cloud URL:     {settings.backend_url}")
    logger.info(f"Agent ID:              {settings.agent_id}")
    logger.info(f"Sync Interval:         {settings.sync_interval_seconds}s")
    logger.info(f"Heartbeat Interval:    {settings.heartbeat_interval_seconds}s")
    logger.info("=" * 60)

    engine = SyncEngine()
    last_sync = 0.0
    last_heartbeat = 0.0

    while running:
        now = time.time()

        # 1. Periodic Heartbeat
        if now - last_heartbeat >= settings.heartbeat_interval_seconds:
            try:
                is_tally_up = engine.tally.is_reachable()
                tally_status_str = "ONLINE" if is_tally_up else "OFFLINE"
                company_name = None
                company_guid = None
                if is_tally_up:
                    try:
                        c_info = engine.tally.get_company_info()
                        if c_info:
                            company_name = c_info.get("name")
                            company_guid = c_info.get("guid")
                    except Exception:
                        pass

                engine.backend.heartbeat(
                    agent_version=AGENT_VERSION,
                    tally_status=tally_status_str,
                    company_name=company_name,
                    company_guid=company_guid,
                    checkpoints=engine.checkpoints.get_all_checkpoints(),
                )
            except Exception as ex:
                logger.warning(f"Heartbeat transient warning: {ex}")
            last_heartbeat = now

        # 2. Periodic Incremental Sync
        if now - last_sync >= settings.sync_interval_seconds:
            try:
                res = engine.run_sync(is_initial=False)
                logger.info(f"Sync cycle completed: status={res['status']} duration={res['duration_seconds']}s")
            except Exception as ex:
                logger.error(f"Sync cycle execution error: {ex}", exc_info=True)
            last_sync = now

        # Short sleep to keep loop responsive to termination signals
        time.sleep(1)

    logger.info("FieldTrack Pro Tally Sync Service has cleanly stopped.")

if __name__ == "__main__":
    run_service()
