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


settings = Settings()
