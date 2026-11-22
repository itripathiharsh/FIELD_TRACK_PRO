import json
import warnings
from typing import Annotated, List

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Application
    app_name: str = "FieldTrack Pro API"
    environment: str = "dev"
    api_v1_prefix: str = "/api/v1"
    debug: bool = True

    # Database (required — no silent fallback in production)
    # Runtime connection: a least-privilege application role (see
    # docs/SECRET_ROTATION.md). It deliberately cannot alter schema, and cannot
    # UPDATE or DELETE audit rows (FT-032).
    database_url: str

    # Schema migrations need table ownership, which the application role does
    # not have. Alembic uses this URL when set, otherwise falls back to
    # database_url (fine for a developer machine that still owns the schema).
    migration_database_url: str | None = None

    # JWT
    jwt_secret: str
    jwt_access_token_expiry_minutes: int = 15
    jwt_refresh_token_expiry_days: int = 7

    # Reuse of an already-rotated refresh token within this many seconds of
    # its own rotation is treated as a benign duplicate (two browser tabs or
    # a client retry racing the same token) rather than theft: no account-wide
    # revoke, just another valid rotation issued. Reuse older than this is
    # still treated as theft. Kept short - this is about tolerating a race,
    # not widening the window a genuinely stolen token can be replayed in.
    refresh_reuse_grace_seconds: int = 10

    # P1-2: dedicated secret for signing media presigned-URL tokens
    # (app/services/storage/local_provider.py), independent of jwt_secret.
    # Previously reused jwt_secret directly, so rotating either secret
    # unintentionally invalidated the other's trust boundary. No insecure
    # default is used in production - see _require_media_signing_secret below.
    media_signing_secret: str | None = None

    # Storage Provider ("LOCAL" or "MINIO")
    storage_provider: str = "LOCAL"
    media_storage_path: str = "media_storage"

    # MinIO (defaults provided to avoid strict failures in dev/test)
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_bucket: str = "fieldtrackpro-dev"
    minio_secure: bool = False
    minio_region: str | None = None  # e.g. "auto" (Cloudflare R2), "ap-south-1" (AWS S3)

    # Live outlet proof (photo + GPS captured together). All values are overridable via env.
    outlet_proof_max_accuracy_m: float = 30.0          # reject GPS fixes worse than this
    outlet_proof_max_age_seconds: int = 180            # captured_at must be this fresh (live capture)
    outlet_proof_future_tolerance_seconds: int = 60    # device clock skew allowed into the future
    outlet_proof_confirm_radius_m: float = 50.0        # within this of the verified pin = CONFIRMATION
    outlet_proof_max_image_bytes: int = 10 * 1024 * 1024
    outlet_proof_max_dimension_px: int = 1600          # stored longest side
    outlet_proof_jpeg_quality: int = 82
    outlet_proof_signed_url_minutes: int = 10
    outlet_proof_unattached_ttl_hours: int = 48        # unattached (new-outlet) proofs expire after this
    # New-outlet submissions by an EMPLOYEE must carry an outlet_proof_id (422 OUTLET_PROOF_REQUIRED).
    # Set False for backward compatibility with clients that predate live outlet proof.
    outlet_proof_required_for_new_outlet: bool = True
    # >= 2 enables auto-verification: N distinct employees on N distinct IST dates with PENDING
    # INITIAL proofs inside the confirm radius (accuracy <= auto_verify_max_accuracy_m). 0 = off.
    outlet_proof_auto_verify_min_agreeing: int = 0
    outlet_proof_auto_verify_max_accuracy_m: float = 20.0
    # Business rule: the FIRST valid photo+GPS proof of an outlet that has no location at all is accepted at once
    # (employees register the initial pins; almost no outlet has GPS yet). Later proofs never are: a different
    # place is a CHANGE_REQUEST for the admin. Set False to send first proofs to admin review instead.
    outlet_proof_first_location_auto_accept: bool = True

    # CORS
    # Exact-match allow-list only (no wildcard / *.vercel.app regex - any
    # attacker can deploy to *.vercel.app). The default is local development
    # origins; production origins MUST come from CORS_ALLOWED_ORIGINS
    # (render.yaml).
    # Accepts a comma-separated string OR a JSON array in the environment
    # (NoDecode stops pydantic-settings pre-parsing it as JSON; see validator).
    cors_allowed_origins: Annotated[List[str], NoDecode] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
    ]

    # Refresh-token cookie. Web (Vercel) and API (Render) are different sites,
    # so production needs SameSite=None; Secure for the cookie to be sent on
    # cross-site fetch(credentials: include). Dev/test use Lax.
    refresh_cookie_samesite: str | None = None  # "lax" | "strict" | "none"; None = auto

    # Forced password change: when True, an authenticated employee whose
    # Employee.must_change_password flag is set gets 403 PASSWORD_CHANGE_REQUIRED on every
    # endpoint except /auth/me, /auth/logout, /auth/refresh and the change-password endpoints.
    # Default False so deploying this code cannot lock 30 staff out before clients ship the
    # change-password screen; render.yaml turns it on.
    enforce_password_change: bool = False
    # Lifetime of an admin-issued temporary password (admin "Reset Password"). After this the
    # temporary password is rejected at login and on every request; the admin must reset again.
    temp_password_expiry_minutes: int = Field(default=30, ge=5, le=1440)

    # Number of trusted reverse-proxy hops in front of the app (Render edge = 1). The client IP
    # for per-IP rate limits is the X-Forwarded-For entry that many hops from the RIGHT; entries
    # to its left are client-controlled and ignored. 0 = ignore X-Forwarded-For entirely.
    trusted_proxy_hops: int = 1

    # Hard cap on ANY request body (multipart upload or JSON incl. base64 signatures), rejected
    # with 413 before the body is parsed. The per-endpoint caps (10 MB images, 20 MB documents,
    # outlet_proof_max_image_bytes) are tighter and enforced while streaming (app/core/uploads.py).
    max_request_body_bytes: int = 30 * 1024 * 1024

    # Password-reset OTP keyed-hash secret. Falls back to a key derived from
    # JWT_SECRET (domain-separated) when unset.
    otp_hmac_secret: str | None = None

    # Release 2.2.0: first day of the LIVE financial year (= agent SYNC_FROM_DATE). Tally rows dated before it
    # are history: excluded from live screens and reporting periods (app/services/reporting_floor.py).
    tally_reporting_floor: str = "2026-04-01"

    # Twilio sender (was read by sms_service but never declared)
    twilio_from_number: str | None = None

    # Background jobs
    # Disabled in tests so a scheduled sweep cannot mutate fixture data while
    # an assertion is running (FT-021).
    enable_scheduler: bool = True

    # Mirrors the sync agent's own TALLY_WRITEBACK_ENABLED. When False (the
    # accountant keys receipts into Tally by hand), verifying a collection does
    # not enqueue a write-back job that no agent would ever process; the
    # collection is confirmed instead by linking it to the receipt the agent
    # imports from Tally (payment_reconciliation_service).
    tally_writeback_enabled: bool = False

    # Firebase
    firebase_credentials_path: str = ""

    # Geocoding
    # Provider: "nominatim" (free, no API key) or "google" (requires API key)
    geocoding_provider: str = "nominatim"
    geocoding_base_url: str | None = None
    geocoding_user_agent: str = "FieldTrackPro/1.0"
    google_geocoding_api_key: str | None = None

    # Email / SMTP
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None
    smtp_from_email: str = "noreply@fieldtrackpro.com"
    # Never send SMTP credentials over an unencrypted channel unless this is set (dev only;
    # ignored in production, where it is always treated as False).
    smtp_allow_insecure: bool = False

    # SMS Configuration
    sms_provider: str = "mock"  # "mock" | "msg91" | "twilio" | "fast2sms"
    sms_api_key: str | None = None
    sms_sender_id: str | None = None
    sms_template_id: str | None = None
    twilio_account_sid: str | None = None
    twilio_auth_token: str | None = None
    allow_mock_communications: bool = False
    # Explicit local-dev opt-in to print password-reset OTPs to the console
    # (also requires ENVIRONMENT in dev/test and DEBUG=true). Never set in prod.
    dev_print_otp: bool = False
    # Organization Profile & Identity
    organization_name: str = "SGRG Services Private Limited"
    organization_hub: str = "Kanpur Central, Uttar Pradesh"
    organization_divisions: str = "Telecom Distribution (11001–11020) & Consumer Electronics (11021–11030)"
    organization_contact_email: str = "contact@sgrgservices.com"
    organization_contact_phone: str = "+91 98390 11015"
    organization_gstin: str = "09AAECS1234F1Z5"
    organization_timezone: str = "Asia/Kolkata (IST, UTC+5:30)"
    organization_currency: str = "INR (₹)"

    @field_validator("database_url", "migration_database_url", mode="before")
    @classmethod
    def _ensure_asyncpg_driver(cls, v: str | None) -> str | None:
        if not v or not isinstance(v, str):
            return v
        if v.startswith("postgres://"):
            v = v.replace("postgres://", "postgresql+asyncpg://", 1)
        elif v.startswith("postgresql://") and not v.startswith("postgresql+asyncpg://"):
            v = v.replace("postgresql://", "postgresql+asyncpg://", 1)
        if "sslmode=" in v:
            v = v.replace("sslmode=require", "ssl=require").replace("sslmode=prefer", "ssl=prefer")
        return v

    @field_validator("cors_allowed_origins", mode="before")
    @classmethod
    def _ensure_cors_list(cls, v: list | str) -> list:
        """Accept a JSON array string, a comma-separated string, or a real list."""
        if isinstance(v, str):
            raw = v.strip()
            if not raw:
                return []
            if raw.startswith("["):
                try:
                    parsed = json.loads(raw)
                except ValueError as exc:
                    raise ValueError("CORS_ALLOWED_ORIGINS looks like JSON but is not valid JSON") from exc
                return [str(o).strip() for o in parsed if str(o).strip()]
            return [o.strip() for o in raw.split(",") if o.strip()]
        return v

    @model_validator(mode="after")
    def _warn_production_cors(self) -> "Settings":
        """Warn (never fail) on risky production CORS configuration."""
        if self.environment == "production":
            bad = [o for o in self.cors_allowed_origins if o.strip() == "*"]
            local = [o for o in self.cors_allowed_origins if "localhost" in o or "127.0.0.1" in o]
            non_local = [o for o in self.cors_allowed_origins if o not in local]
            if bad:
                warnings.warn("CORS_ALLOWED_ORIGINS contains '*' in production", stacklevel=2)
            if not non_local:
                warnings.warn(
                    "CORS_ALLOWED_ORIGINS has only localhost origins in production; "
                    "the real web origin is probably missing",
                    stacklevel=2,
                )
        return self

    @model_validator(mode="after")
    def _require_media_signing_secret_in_production(self) -> "Settings":
        """
        P1-2: production must fail to start rather than silently sign media
        URLs with an insecure default (or, as before, with jwt_secret).
        Dev/test may fall back to a fixed, non-production placeholder that is
        never derived from jwt_secret, so the two secrets are independent
        even when a developer hasn't bothered to set one explicitly.
        """
        if self.environment == "production" and not self.media_signing_secret:
            raise ValueError(
                "MEDIA_SIGNING_SECRET must be set when ENVIRONMENT=production - "
                "refusing to start rather than fall back to an insecure default."
            )
        if not self.media_signing_secret:
            self.media_signing_secret = "dev-only-media-signing-secret-do-not-use-in-production"
        return self

    @model_validator(mode="after")
    def _validate_production_storage_config(self) -> "Settings":
        """
        Production hardening: reject default, placeholder, or predictable development
        credentials for MinIO when running in production.
        """
        if self.environment == "production" and self.storage_provider.upper() == "MINIO":
            insecure_defaults = {
                "minioadmin",
                "minio",
                "admin",
                "secret",
                "password",
                "default",
                "changeme",
                "test",
                "12345678",
                "accesskey",
                "secretkey",
            }

            access_key = (self.minio_access_key or "").strip()
            secret_key = (self.minio_secret_key or "").strip()
            endpoint = (self.minio_endpoint or "").strip().lower()
            bucket = (self.minio_bucket or "").strip().lower()

            if not access_key or access_key.lower() in insecure_defaults:
                raise ValueError(
                    "MINIO_ACCESS_KEY must be configured with a secure, non-default credential "
                    "when ENVIRONMENT=production and STORAGE_PROVIDER=MINIO."
                )

            if not secret_key or secret_key.lower() in insecure_defaults:
                raise ValueError(
                    "MINIO_SECRET_KEY must be configured with a secure, non-default credential "
                    "when ENVIRONMENT=production and STORAGE_PROVIDER=MINIO."
                )

            if not endpoint or "localhost" in endpoint or "127.0.0.1" in endpoint:
                raise ValueError(
                    "MINIO_ENDPOINT must point to a dedicated production storage host (not localhost) "
                    "when ENVIRONMENT=production and STORAGE_PROVIDER=MINIO."
                )

            if not bucket or bucket == "fieldtrackpro-dev" or "dev" in bucket:
                raise ValueError(
                    "MINIO_BUCKET must be configured with a production bucket name (not development default) "
                    "when ENVIRONMENT=production and STORAGE_PROVIDER=MINIO."
                )

        return self

    @model_validator(mode="after")
    def _validate_production_auth_communication_config(self) -> "Settings":
        """
        Production hardening: In production, mock SMS provider and unconfigured SMTP
        are rejected at startup to prevent silent communication failures or leaks.
        """
        if self.environment == "production" and not self.allow_mock_communications:
            if (self.sms_provider or "").strip().lower() == "mock":
                raise ValueError(
                    "SMS_PROVIDER cannot be 'mock' when ENVIRONMENT=production. "
                    "Configure a valid production SMS provider (msg91, twilio, fast2sms) and credentials."
                )
            if not self.smtp_host:
                raise ValueError(
                    "SMTP_HOST must be configured when ENVIRONMENT=production - "
                    "refusing to start with silent fallback to terminal mock email."
                )
        return self


settings = Settings()

