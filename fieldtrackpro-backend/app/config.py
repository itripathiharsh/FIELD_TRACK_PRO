from typing import List
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

    # Firebase
    firebase_credentials_path: str = ""


settings = Settings()
