"""
Production baseline setup & client data initialization.
Ensures standard administrative baseline exists and triggers legitimate SGRG data import.
Does NOT delete user-created visits or employees.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Ensure root backend directory is on sys.path for direct script execution
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import create_engine, text
from app.config import settings
from app.core.security import hash_password

ADMIN_PASSWORD = "AdminPass123!"
HARSH_PASSWORD = "Imharsh@1"


def run() -> None:
    url = settings.database_url.replace("postgresql+asyncpg://", "postgresql://")
    engine = create_engine(url)

    with engine.begin() as conn:
        # 1. Ensure super-admin account exists
        admin_id = "d97a16ca-ebd7-4f83-a0a0-8649a872e8a2"
        pw_hash = hash_password(ADMIN_PASSWORD)
        conn.execute(
            text("""
                INSERT INTO users (id, email, password_hash, role, is_active, created_at, updated_at)
                VALUES (:id, 'admin@fieldtrack.test', :pw, 'ADMIN', true, now(), now())
                ON CONFLICT (email) DO UPDATE SET password_hash = EXCLUDED.password_hash, is_active = true, updated_at = now()
            """),
            {"id": admin_id, "pw": pw_hash},
        )

    print("Super-admin account verified.")


if __name__ == "__main__":
    run()

