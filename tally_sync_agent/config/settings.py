import os
import sys
from pathlib import Path
from typing import Optional
from pydantic import BaseModel, Field

# Single source of truth for the agent's own version string (sent in heartbeats,
# printed by `health`/`status`, and used to name the release build).
AGENT_VERSION = "3.0.0"

# The production FieldTrack backend. A NAMED agent instance (AGENT_INSTANCE_NAME set, e.g. a staging
# acceptance instance running beside the production agent) refuses to talk to it unless explicitly allowed.
PRODUCTION_BACKEND_URL = "https://51-79-158-138.sslip.io"
DEFAULT_MUTEX_NAME = "Global\\FieldTrackTallyAgent_SingleInstance"  # unchanged since 1.2.1 (verified in its exe)
INSTANCE_NAME_RE = r"^[A-Z0-9_]{1,20}$"

# Base directories. When packaged as a single .exe (PyInstaller) the code lives in a temp folder, so
# config (.env), data and logs must sit next to the executable instead.
if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys.executable).resolve().parent
else:
    BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

class SyncAgentSettings(BaseModel):
    """Configuration settings for FieldTrack Pro Tally Sync Agent."""
    
    # TallyPrime local interface
    tally_url: str = Field(default="http://127.0.0.1:9000")
    tally_timeout_seconds: int = Field(default=180)
    
    # FieldTrack Pro Cloud / Backend interface
    backend_url: str = Field(default="http://127.0.0.1:8000")
    backend_timeout_seconds: int = Field(default=60)
    
    # Agent Credentials (obtained upon registration or from env)
    agent_id: Optional[str] = Field(default=None)
    agent_key: Optional[str] = Field(default=None)
    organization_id: Optional[str] = Field(default=None)
    
    # Operational Sync Parameters
    batch_size: int = Field(default=100)
    sync_interval_seconds: int = Field(default=300)      # 5 minutes
    heartbeat_interval_seconds: int = Field(default=60) # 1 minute

    # Earliest voucher date synced (financial-year start; balances before it come
    # from the opening-balance import). Incremental cycles always look back to
    # this date and rely on AlterID for "what changed", so a voucher keyed in
    # today but dated earlier (a backdated receipt) is still picked up.
    sync_from_date: str = Field(default="2026-04-01")

    # Agent 2.0 schedule and load limits
    balance_interval_minutes: int = Field(default=60)    # ledger balances + Bills Receivable
    # Agent 3.0 reconciliation (the daily manifest is now the last step of the nightly reconciliation)
    reconcile_hourly_minutes: int = Field(default=60)    # hourly: today-31 .. today
    reconcile_hourly_days: int = Field(default=31)
    reconcile_nightly_hour: int = Field(default=1)       # nightly: whole FY, once per IST date from this hour
    day_request_pause_seconds: float = Field(default=0.5)  # pause between one-day requests to Tally
    snapshot_chunk_size: int = Field(default=500)
    # Voucher GUID manifest: "month" = one date-range request per month (2.0.1 default),
    # "day" = one request per day (the 2.0.0 behaviour). Anything else falls back to "month".
    manifest_scan_mode: str = Field(default="month")
    # Named instance (empty = the default, single production instance). See instance_config().
    agent_instance_name: str = Field(default="")
    allow_named_instance_on_production: bool = Field(default=False)
    # The company is selected BY GUID (2.2.0). Strongly recommended; without it the agent accepts only
    # the case of exactly one company loaded in Tally, and refuses when several are loaded.
    expected_company_guid: Optional[str] = Field(default=None)

    # Agent 2.2.0 - financial years (see config/fiscal.py)
    # Every FY the agent knows; today's FY must be listed and must start on SYNC_FROM_DATE.
    financial_years: str = Field(default="2024-25,2025-26,2026-27")
    # Historical FYs whose vouchers are UPLOADED by the daemon. EMPTY BY DEFAULT: nothing historical is
    # uploaded until explicitly approved AND the backend reports history_safe (B1/B4 deployed).
    history_upload: str = Field(default="")
    history_days_per_cycle: int = Field(default=31)          # first load of a historical FY: days per cycle
    history_incremental_minutes: int = Field(default=60)     # edits / back-dated vouchers in a historical FY
    history_manifest_hours: int = Field(default=168)         # deletions in a historical FY (weekly)

    # Agent 2.2.1 - protection of TallyPrime (core/tally_guard.py)
    tally_duty_factor: float = Field(default=1.0)            # pause after a request = factor x its duration
    tally_min_pause_seconds: float = Field(default=2.0)      # ... but at least this long
    tally_lock_wait_seconds: float = Field(default=300.0)    # machine-wide request lock wait
    tally_cooldown_seconds: float = Field(default=180.0)     # first cool-down after a failed request
    tally_cooldown_max_seconds: float = Field(default=1800.0)  # cool-down doubles up to this

    # Checkpoint & Retry Storage
    db_path: Path = Field(default=DATA_DIR / "sync_agent.db")
    log_file: Path = Field(default=DATA_DIR / "sync_agent.log")
    
    # Logging
    log_level: str = Field(default="INFO")
    
    @classmethod
    def load(cls) -> "SyncAgentSettings":
        """Load settings from environment variables or .env file."""
        env_path = BASE_DIR / ".env"
        if env_path.exists():
            with open(env_path, "r", encoding="utf-8-sig") as f:  # 2.2.0: a BOM no longer eats the first key
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k, v = line.split("=", 1)
                    k = k.strip()
                    v = v.strip().strip("\"'")
                    if k not in os.environ:
                        os.environ[k] = v
                        
        return cls(
            tally_url=os.getenv("TALLY_URL", "http://127.0.0.1:9000"),
            tally_timeout_seconds=int(os.getenv("TALLY_TIMEOUT_SECONDS", "180")),
            backend_url=os.getenv("BACKEND_URL", "http://127.0.0.1:8000"),
            backend_timeout_seconds=int(os.getenv("BACKEND_TIMEOUT_SECONDS", "60")),
            agent_id=os.getenv("AGENT_ID"),
            agent_key=os.getenv("AGENT_KEY"),
            organization_id=os.getenv("ORGANIZATION_ID"),
            batch_size=int(os.getenv("BATCH_SIZE", "100")),
            sync_interval_seconds=int(os.getenv("SYNC_INTERVAL_SECONDS", "300")),
            heartbeat_interval_seconds=int(os.getenv("HEARTBEAT_INTERVAL_SECONDS", "60")),
            sync_from_date=os.getenv("SYNC_FROM_DATE", "2026-04-01"),
            balance_interval_minutes=int(os.getenv("BALANCE_INTERVAL_MINUTES", "60")),
            reconcile_hourly_minutes=int(os.getenv("RECONCILE_HOURLY_MINUTES", "60")),
            reconcile_hourly_days=int(os.getenv("RECONCILE_HOURLY_DAYS", "31")),
            reconcile_nightly_hour=int(os.getenv("RECONCILE_NIGHTLY_HOUR", "1")),
            day_request_pause_seconds=float(os.getenv("DAY_REQUEST_PAUSE_SECONDS", "0.5")),
            snapshot_chunk_size=int(os.getenv("SNAPSHOT_CHUNK_SIZE", "500")),
            manifest_scan_mode="day" if os.getenv("MANIFEST_SCAN_MODE", "month").strip().lower() == "day" else "month",
            agent_instance_name=(os.getenv("AGENT_INSTANCE_NAME") or "").strip().upper(),
            allow_named_instance_on_production=os.getenv("ALLOW_NAMED_INSTANCE_ON_PRODUCTION", "false").strip().lower() in ("1", "true", "yes", "on"),
            expected_company_guid=os.getenv("EXPECTED_COMPANY_GUID") or None,
            financial_years=os.getenv("FINANCIAL_YEARS", "2024-25,2025-26,2026-27"),
            history_upload=os.getenv("HISTORY_UPLOAD", ""),
            history_days_per_cycle=int(os.getenv("HISTORY_DAYS_PER_CYCLE", "31")),
            history_incremental_minutes=int(os.getenv("HISTORY_INCREMENTAL_MINUTES", "60")),
            history_manifest_hours=int(os.getenv("HISTORY_MANIFEST_HOURS", "168")),
            tally_duty_factor=float(os.getenv("TALLY_DUTY_FACTOR", "1.0")),
            tally_min_pause_seconds=float(os.getenv("TALLY_MIN_PAUSE_SECONDS", "2.0")),
            tally_lock_wait_seconds=float(os.getenv("TALLY_LOCK_WAIT_SECONDS", "300")),
            tally_cooldown_seconds=float(os.getenv("TALLY_COOLDOWN_SECONDS", "180")),
            tally_cooldown_max_seconds=float(os.getenv("TALLY_COOLDOWN_MAX_SECONDS", "1800")),
            log_level=os.getenv("LOG_LEVEL", "INFO"),
        )

class InstanceConfigError(ValueError):
    """The configured instance name / backend combination is not allowed; the agent must not start."""


def instance_config(cfg: "SyncAgentSettings") -> dict:
    """-> {"instance": "default"|NAME, "mutex": <mutex name>, "named": bool}. Raises InstanceConfigError.

    The default instance keeps the historical mutex name, so a production 2.x agent and Agent 1.2.1
    (same name, verified in its exe) can never run at the same time. A named instance gets its own
    mutex, so it can run beside them, and refuses the production backend unless explicitly allowed."""
    import re
    name = (cfg.agent_instance_name or "").strip().upper()
    if not name:
        return {"instance": "default", "mutex": DEFAULT_MUTEX_NAME, "named": False}
    if name == "DEFAULT" or not re.match(INSTANCE_NAME_RE, name):
        raise InstanceConfigError(f"AGENT_INSTANCE_NAME '{name}' is not allowed: use 1-20 of A-Z, 0-9, _ (not DEFAULT)")
    if cfg.backend_url.rstrip("/").lower() == PRODUCTION_BACKEND_URL.lower() and not cfg.allow_named_instance_on_production:
        raise InstanceConfigError(f"Named instance '{name}' refuses the production backend {PRODUCTION_BACKEND_URL}")
    return {"instance": name, "mutex": f"{DEFAULT_MUTEX_NAME}_{name}", "named": True}


# Global settings instance
settings = SyncAgentSettings.load()
