from typing import List

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


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

    # CORS
    cors_allowed_origins: List[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "https://fieldtrack-pro-rosy.vercel.app",
        "https://fieldtrack-pro-imharshofficial322-gmailcoms-projects.vercel.app",
        "https://fieldtrack-pro-git-main-imharshofficial322-gmailcoms-projects.vercel.app",
    ]

    # Background jobs
    # Disabled in tests so a scheduled sweep cannot mutate fixture data while
    # an assertion is running (FT-021).
    enable_scheduler: bool = True

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

    # SMS Configuration
    sms_provider: str = "mock"  # "mock" | "msg91" | "twilio" | "fast2sms"
    sms_api_key: str | None = None
    sms_sender_id: str | None = None
    sms_template_id: str | None = None
    twilio_account_sid: str | None = None
    twilio_auth_token: str | None = None
    allow_mock_communications: bool = False
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
        if isinstance(v, str) and not v.strip().startswith("["):
            return [o.strip() for o in v.split(",") if o.strip()]
        return v

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

