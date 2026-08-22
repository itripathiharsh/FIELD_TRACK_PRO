"""
Tests for production storage configuration hardening.
"""
from __future__ import annotations

import pytest

from app.config import Settings


def test_development_storage_defaults_permitted():
    """In development, convenient defaults are permitted for local work."""
    s = Settings(
        environment="dev",
        database_url="postgresql+asyncpg://user:pass@localhost:5432/db",
        jwt_secret="test_secret_for_jwt_dev_1234567890",
        storage_provider="MINIO",
        minio_access_key="minioadmin",
        minio_secret_key="minioadmin",
        minio_endpoint="localhost:9000",
        minio_bucket="fieldtrackpro-dev",
    )
    assert s.environment == "dev"
    assert s.minio_access_key == "minioadmin"


def test_production_rejects_default_minio_access_key():
    """In production with MinIO, default or insecure access key raises ValueError."""
    with pytest.raises(ValueError, match="MINIO_ACCESS_KEY must be configured with a secure, non-default credential"):
        Settings(
            environment="production",
            database_url="postgresql+asyncpg://user:pass@prod-db.internal:5432/db",
            jwt_secret="a_very_secure_production_jwt_secret_987654321",
            media_signing_secret="secure_media_signing_secret_prod_123456",
            storage_provider="MINIO",
            minio_access_key="minioadmin",  # Insecure default!
            minio_secret_key="ProductionSecureSecretKey1234567890!",
            minio_endpoint="minio.internal.storage:9000",
            minio_bucket="fieldtrackpro-production-media",
        )


def test_production_rejects_default_minio_secret_key():
    """In production with MinIO, default secret key raises ValueError."""
    with pytest.raises(ValueError, match="MINIO_SECRET_KEY must be configured with a secure, non-default credential"):
        Settings(
            environment="production",
            database_url="postgresql+asyncpg://user:pass@prod-db.internal:5432/db",
            jwt_secret="a_very_secure_production_jwt_secret_987654321",
            media_signing_secret="secure_media_signing_secret_prod_123456",
            storage_provider="MINIO",
            minio_access_key="ProductionAccessKey9988",
            minio_secret_key="minioadmin",  # Insecure default!
            minio_endpoint="minio.internal.storage:9000",
            minio_bucket="fieldtrackpro-production-media",
        )


def test_production_rejects_localhost_minio_endpoint():
    """In production with MinIO, localhost/127.0.0.1 endpoint raises ValueError."""
    with pytest.raises(ValueError, match="MINIO_ENDPOINT must point to a dedicated production storage host"):
        Settings(
            environment="production",
            database_url="postgresql+asyncpg://user:pass@prod-db.internal:5432/db",
            jwt_secret="a_very_secure_production_jwt_secret_987654321",
            media_signing_secret="secure_media_signing_secret_prod_123456",
            storage_provider="MINIO",
            minio_access_key="ProductionAccessKey9988",
            minio_secret_key="ProductionSecureSecretKey1234567890!",
            minio_endpoint="localhost:9000",  # Insecure for production!
            minio_bucket="fieldtrackpro-production-media",
        )


def test_production_rejects_dev_minio_bucket():
    """In production with MinIO, default 'fieldtrackpro-dev' bucket raises ValueError."""
    with pytest.raises(ValueError, match="MINIO_BUCKET must be configured with a production bucket name"):
        Settings(
            environment="production",
            database_url="postgresql+asyncpg://user:pass@prod-db.internal:5432/db",
            jwt_secret="a_very_secure_production_jwt_secret_987654321",
            media_signing_secret="secure_media_signing_secret_prod_123456",
            storage_provider="MINIO",
            minio_access_key="ProductionAccessKey9988",
            minio_secret_key="ProductionSecureSecretKey1234567890!",
            minio_endpoint="minio.internal.prod:9000",
            minio_bucket="fieldtrackpro-dev",  # Insecure dev bucket!
        )


def test_production_accepts_valid_minio_configuration():
    """In production with MinIO, valid secure configuration passes validation."""
    s = Settings(
        environment="production",
        database_url="postgresql+asyncpg://user:pass@prod-db.internal:5432/db",
        jwt_secret="a_very_secure_production_jwt_secret_987654321",
        media_signing_secret="secure_media_signing_secret_prod_123456",
        storage_provider="MINIO",
        minio_access_key="ProdAccessKey_771122",
        minio_secret_key="ProdSecretKey_StrongPass#2026!",
        minio_endpoint="minio.storage.fieldtrackpro.internal:9000",
        minio_bucket="fieldtrackpro-prod-media",
        minio_secure=True,
    )
    assert s.environment == "production"
    assert s.minio_bucket == "fieldtrackpro-prod-media"
    assert s.minio_secure is True


def test_production_local_storage_does_not_require_minio():
    """In production with LOCAL storage, MinIO validation does not block startup."""
    s = Settings(
        environment="production",
        database_url="postgresql+asyncpg://user:pass@prod-db.internal:5432/db",
        jwt_secret="a_very_secure_production_jwt_secret_987654321",
        media_signing_secret="secure_media_signing_secret_prod_123456",
        storage_provider="LOCAL",
        media_storage_path="/var/fieldtrackpro/media",
    )
    assert s.environment == "production"
    assert s.storage_provider == "LOCAL"
