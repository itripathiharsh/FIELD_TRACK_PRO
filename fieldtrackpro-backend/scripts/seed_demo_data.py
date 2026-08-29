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

        # 2. Ensure Harsh Tripathi user & employee profile exists
        harsh_user_id = "ac2abf41-e62c-4147-a42b-e507232aac38"
        harsh_pw_hash = hash_password(HARSH_PASSWORD)
        conn.execute(
            text("""
                INSERT INTO users (id, email, mobile_number, password_hash, role, is_active, created_at, updated_at)
                VALUES (:id, 'imharshofficial322@gmail.com', '9565249244', :pw, 'EMPLOYEE', true, now(), now())
                ON CONFLICT (email) DO UPDATE SET 
                    mobile_number = EXCLUDED.mobile_number,
                    password_hash = EXCLUDED.password_hash,
                    role = 'EMPLOYEE',
                    is_active = true,
                    updated_at = now();
            """),
            {"id": harsh_user_id, "pw": harsh_pw_hash}
        )

        # Fetch the actual user id for Harsh
        actual_user = conn.execute(text("SELECT id FROM users WHERE email = 'imharshofficial322@gmail.com'")).first()
        if actual_user:
            uid = actual_user[0]
            harsh_emp = conn.execute(text("SELECT id FROM employees WHERE user_id = :uid"), {"uid": uid}).first()
            if not harsh_emp:
                conn.execute(text("""
                    INSERT INTO employees (
                        id, user_id, full_name, employee_code, working_profile, cug, date_of_birth, address, must_change_password
                    ) VALUES (
                        :id, :uid, 'Harsh Tripathi', 'HARSH01', 'Sales Specialist', '9565249244', '1995-08-15', 'Lucknow, Uttar Pradesh', false
                    )
                    ON CONFLICT (employee_code) DO NOTHING;
                """), {"id": uid, "uid": uid})

    # 3. Trigger standard idempotent import
    try:
        try:
            from scripts.import_real_client_data import run_import
        except ModuleNotFoundError:
            from import_real_client_data import run_import
        run_import()
    except Exception as e:
        print(f"Data import note (non-fatal): {e}")


if __name__ == "__main__":
    run()
