"""purge demo and test data to enforce clean SGRG production baseline

Revision ID: k4l5m6n7o8p9
Revises: j3k4l5m6n7o8
Create Date: 2026-08-22 22:25:00.000000

Purges all legacy demo visits, demo payments, demo invoices, non-SGRG demo customers,
and non-SGRG demo employees to ensure the production database contains strictly
genuine SGRG enterprise data.
"""
from typing import Sequence, Union

from alembic import op


revision: str = "k4l5m6n7o8p9"
down_revision: Union[str, Sequence[str], None] = "j3k4l5m6n7o8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Delete all demo payments, invoices, visits, form submissions
    op.execute("""
        DELETE FROM payments 
        WHERE id::text LIKE '77777777-%' 
           OR source = 'MANUAL' 
           OR customer_id NOT IN (SELECT id FROM customers WHERE outlet_code IS NOT NULL);
    """)
    op.execute("""
        DELETE FROM invoices 
        WHERE id::text LIKE '66666666-%' 
           OR source = 'MANUAL' 
           OR customer_id NOT IN (SELECT id FROM customers WHERE outlet_code IS NOT NULL);
    """)
    op.execute("""
        DELETE FROM form_submissions 
        WHERE visit_id IN (SELECT id FROM visits WHERE id::text LIKE '44444444-%' OR customer_id NOT IN (SELECT id FROM customers WHERE outlet_code IS NOT NULL));
    """)
    op.execute("""
        DELETE FROM visits 
        WHERE id::text LIKE '44444444-%' 
           OR customer_id NOT IN (SELECT id FROM customers WHERE outlet_code IS NOT NULL);
    """)
    op.execute("""
        DELETE FROM form_submissions 
        WHERE form_id IN (SELECT id FROM form_templates WHERE name IN ('Debug Publish 2', 'Safety Inspection', 'E2E Safety Inspection', 'Sales guy', 'xyz', 'new'));
    """)
    op.execute("""
        DELETE FROM form_templates 
        WHERE name IN ('Debug Publish 2', 'Safety Inspection', 'E2E Safety Inspection', 'Sales guy', 'xyz', 'new');
    """)

    # 2. Delete non-SGRG demo customers (keep only legitimate SGRG outlets with DMS codes)
    op.execute("""
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
    """)

    # 3. Delete non-SGRG employees and users
    op.execute("""
        DELETE FROM employee_customer_assignments 
        WHERE employee_id IN (SELECT id FROM employees WHERE employee_code NOT BETWEEN '11001' AND '11030');
    """)
    op.execute("""
        DELETE FROM employee_territory_assignments 
        WHERE employee_id IN (SELECT id FROM employees WHERE employee_code NOT BETWEEN '11001' AND '11030');
    """)
    op.execute("""
        DELETE FROM employees 
        WHERE employee_code NOT BETWEEN '11001' AND '11030';
    """)
    op.execute("""
        DELETE FROM users 
        WHERE email NOT LIKE '%@sgrgservices.com' 
          AND email != 'admin@fieldtrack.test';
    """)

    # 4. Clean unused demo territories
    op.execute("""
        DELETE FROM territories 
        WHERE id::text LIKE '11111111-%' 
           OR name IN ('Bengaluru Central', 'Mumbai Western Suburbs', 'Pune IT Corridor', 'North Delhi Corridor', 'North Region QA');
    """)


def downgrade() -> None:
    pass
