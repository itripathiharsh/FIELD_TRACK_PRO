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
    # 1. Delete demo payments, invoices, visits, form submissions.
    # IMPORTANT: match ONLY the literal demo-data UUID markers below. The original
    # version of this migration also matched `source = 'MANUAL'` and
    # `customer_id NOT IN (... outlet_code IS NOT NULL)` - those are NOT demo
    # markers, they are the normal shape of every real field-collected payment/
    # invoice/visit (PaymentSource.MANUAL is the default for live field
    # collections; a customer can legitimately have no outlet_code yet, e.g.
    # mid-onboarding). On a database that hadn't already run this migration,
    # those two clauses would have deleted every genuine payment/invoice/visit
    # in the system. Fixed to use only the exact demo-data markers from AGENTS.md.
    op.execute("""
        DELETE FROM payments
        WHERE id::text LIKE '77777777-%';
    """)
    op.execute("""
        DELETE FROM invoices
        WHERE id::text LIKE '66666666-%';
    """)
    op.execute("""
        DELETE FROM form_submissions
        WHERE visit_id IN (SELECT id FROM visits WHERE id::text LIKE '44444444-%');
    """)
    op.execute("""
        DELETE FROM visits
        WHERE id::text LIKE '44444444-%';
    """)
    op.execute("""
        DELETE FROM form_submissions
        WHERE form_id IN (SELECT id FROM form_templates WHERE name IN ('Debug Publish 2', 'Safety Inspection', 'E2E Safety Inspection', 'Sales guy', 'xyz', 'new'));
    """)
    op.execute("""
        DELETE FROM form_templates
        WHERE name IN ('Debug Publish 2', 'Safety Inspection', 'E2E Safety Inspection', 'Sales guy', 'xyz', 'new');
    """)

    # 2. Delete demo customers by their literal demo-data markers only (dropped
    # the blanket `outlet_code IS NULL`, which also matches real customers that
    # legitimately have no outlet_code yet).
    op.execute("""
        DELETE FROM customers
        WHERE id::text LIKE '33333333-%'
           OR id IN (
               '0f68a82d-45e7-4c21-b6bd-ac585d41e32b',
               'd40006dc-cd30-4d56-878a-f0860dd1bb0e',
               '81e3ca3a-6ba8-4cdf-ba44-df474b19378f',
               '2ee14e5c-ea2c-4a10-93bd-25f4e1ec1a5b',
               'e3bc5d7b-9c81-438b-bf81-02739ea13a6f'
           );
    """)

    # 3. Delete non-SGRG employees and users. employee_code range 11001-11030
    # is AGENTS.md's own definition of the 30 real SGRG staff members, so
    # "outside that range" is a legitimate marker here (unlike the payments/
    # invoices/customers rules above, which used ad-hoc heuristics instead of
    # an actual documented real-vs-test signal).
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
    # Fixed: the original condition only ever protected the single hardcoded
    # seed admin@fieldtrack.test - any OTHER real admin account (role=ADMIN,
    # which has no employees row and typically isn't @sgrgservices.com) would
    # have been deleted along with the automated writeback/test users. Protect
    # every admin account, not just the one seed email.
    op.execute("""
        DELETE FROM users
        WHERE email NOT LIKE '%@sgrgservices.com'
          AND email != 'admin@fieldtrack.test'
          AND role != 'ADMIN'
          AND id NOT IN (SELECT user_id FROM employees WHERE user_id IS NOT NULL);
    """)

    # 4. Clean unused demo territories
    op.execute("""
        DELETE FROM territories
        WHERE id::text LIKE '11111111-%'
           OR name IN ('Bengaluru Central', 'Mumbai Western Suburbs', 'Pune IT Corridor', 'North Delhi Corridor', 'North Region QA');
    """)


def downgrade() -> None:
    pass
