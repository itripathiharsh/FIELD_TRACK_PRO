"""
Production baseline setup & client data initialization.
Ensures standard administrative baseline exists and triggers legitimate SGRG data import.
Does NOT seed fake/demo customers, visits, payments, or invoices.
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

DEMO_PASSWORD = "AdminPass123!"


def run() -> None:
    url = settings.database_url.replace("postgresql+asyncpg://", "postgresql://")
    engine = create_engine(url)

    with engine.begin() as conn:
        # 1. Purge any remaining demo visits, payments, invoices, and junk entities
        conn.execute(text("""
            DELETE FROM payments 
            WHERE id::text LIKE '77777777-%' 
               OR source = 'MANUAL' 
               OR customer_id NOT IN (SELECT id FROM customers WHERE outlet_code IS NOT NULL);
        """))
        conn.execute(text("""
            DELETE FROM invoices 
            WHERE id::text LIKE '66666666-%' 
               OR source = 'MANUAL' 
               OR customer_id NOT IN (SELECT id FROM customers WHERE outlet_code IS NOT NULL);
        """))
        conn.execute(text("""
            DELETE FROM form_submissions 
            WHERE visit_id IN (SELECT id FROM visits WHERE id::text LIKE '44444444-%' OR customer_id NOT IN (SELECT id FROM customers WHERE outlet_code IS NOT NULL));
        """))
        conn.execute(text("""
            DELETE FROM visits 
            WHERE id::text LIKE '44444444-%' 
               OR customer_id NOT IN (SELECT id FROM customers WHERE outlet_code IS NOT NULL);
        """))
        conn.execute(text("""
            DELETE FROM form_submissions 
            WHERE form_id IN (SELECT id FROM form_templates WHERE name IN ('Debug Publish 2', 'Safety Inspection', 'E2E Safety Inspection', 'Sales guy', 'xyz', 'new'));
        """))
        conn.execute(text("""
            DELETE FROM form_templates 
            WHERE name IN ('Debug Publish 2', 'Safety Inspection', 'E2E Safety Inspection', 'Sales guy', 'xyz', 'new');
        """))
        conn.execute(text("""
            DELETE FROM customers 
            WHERE outlet_code IS NULL 
               OR id::text LIKE '33333333-%' 
               OR id IN (
                   '0f68a82d-45e7-4c21-b6bd-ac585d41e32b',
                   'd40006dc-cd30-4d56-878a-f0860dd1bb0e',
                   '81e3ca3a-6ba8-4cdf-ba44-df474b19378f',
                   '2ee14e5c-ea2c-4a10-93bd-25f4e1ec1a5b',
                   'e3bc5d7b-9c81-438b-bf81-02739ea13a6f'
               );
        """))
        conn.execute(text("""
            DELETE FROM employee_customer_assignments 
            WHERE employee_id IN (SELECT id FROM employees WHERE employee_code NOT BETWEEN '11001' AND '11030');
        """))
        conn.execute(text("""
            DELETE FROM employee_territory_assignments 
            WHERE employee_id IN (SELECT id FROM employees WHERE employee_code NOT BETWEEN '11001' AND '11030');
        """))
        conn.execute(text("""
            DELETE FROM employees 
            WHERE employee_code NOT BETWEEN '11001' AND '11030';
        """))
        conn.execute(text("""
            DELETE FROM users 
            WHERE email NOT LIKE '%@sgrgservices.com' 
              AND email != 'admin@fieldtrack.test';
        """))
        conn.execute(text("""
            DELETE FROM territories 
            WHERE id::text LIKE '11111111-%' 
               OR name IN ('Bengaluru Central', 'Mumbai Western Suburbs', 'Pune IT Corridor', 'North Delhi Corridor', 'North Region QA');
        """))

        # 2. Ensure super-admin account exists
        admin_id = "d97a16ca-ebd7-4f83-a0a0-8649a872e8a2"
        pw_hash = hash_password(DEMO_PASSWORD)
        conn.execute(
            text(
                "INSERT INTO users (id, email, password_hash, role, is_active, created_at, updated_at) "
                "VALUES (:id, 'admin@fieldtrack.test', :pw, 'ADMIN', true, now(), now()) "
                "ON CONFLICT (id) DO UPDATE SET password_hash = EXCLUDED.password_hash, is_active = true, updated_at = now()"
            ),
            {"id": admin_id, "pw": pw_hash},
        )

    # 3. Execute legitimate client data importer
    try:
        from scripts.import_real_client_data import run_import
        print("\nExecuting SGRG enterprise data import...")
        run_import()
    except Exception as e:
        print(f"SGRG client data import error: {e}")


if __name__ == "__main__":
    run()
