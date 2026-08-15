"""
P2-5 / P2-6 — schema/migration consistency checks.

P2-5: verifies the new indexes (visits.status, payments.status,
visits.customer_id, visits.employee_id) actually exist in the migrated
database, not just in the model definitions.

P2-6: verifies `updated_at` on Customer/Employee genuinely advances when the
row is edited through the real API (not just present as a column).
"""
from __future__ import annotations

import time

import pytest
from httpx import AsyncClient

from tests.integration.conftest import db_cursor, requires_db

pytestmark = [requires_db, pytest.mark.integration, pytest.mark.asyncio]


def _index_exists(index_name: str) -> bool:
    with db_cursor() as cur:
        cur.execute("SELECT 1 FROM pg_indexes WHERE indexname = %s", (index_name,))
        return cur.fetchone() is not None


@pytest.mark.parametrize(
    "index_name",
    [
        "ix_payments_status",
        "ix_visits_status",
        "ix_visits_customer_id",
        "ix_visits_employee_id",
    ],
)
def test_p2_5_index_exists(index_name: str):
    assert _index_exists(index_name), f"expected index {index_name} to exist after migration"


async def test_customer_updated_at_advances_on_edit(client: AsyncClient, admin_headers, seeded_world):
    # seeded_world is session-scoped and shared with every other integration
    # test file, so this must restore the original value afterwards rather
    # than permanently renaming the shared fixture row (renaming it away
    # from the __itest__ prefix breaks _purge_test_artifacts' cleanup match
    # for the rest of the session).
    customer_id = seeded_world["customer_id"]
    with db_cursor() as cur:
        cur.execute("SELECT name, contact_number, updated_at FROM customers WHERE id = %s", (customer_id,))
        before = cur.fetchone()
    original_contact_number = before["contact_number"]
    updated_at_before = before["updated_at"]

    # Ensure the clock has visibly moved even on a very fast test run.
    time.sleep(1.1)
    try:
        resp = await client.patch(
            f"/api/v1/customers/{customer_id}",
            json={"name": before["name"], "contact_number": "+919999900099"},
            headers=admin_headers,
        )
        assert resp.status_code == 200, resp.text

        with db_cursor() as cur:
            cur.execute("SELECT updated_at FROM customers WHERE id = %s", (customer_id,))
            updated_at_after = cur.fetchone()["updated_at"]

        assert updated_at_after > updated_at_before
    finally:
        with db_cursor() as cur:
            cur.execute(
                "UPDATE customers SET contact_number = %s WHERE id = %s",
                (original_contact_number, customer_id),
            )


async def test_employee_updated_at_advances_on_edit(client: AsyncClient, admin_headers, seeded_world):
    # Same restore-afterwards rationale as the customer test above.
    employee_id = seeded_world["employee_id"]
    with db_cursor() as cur:
        cur.execute("SELECT full_name, updated_at FROM employees WHERE id = %s", (employee_id,))
        before = cur.fetchone()
    original_full_name = before["full_name"]
    updated_at_before = before["updated_at"]

    time.sleep(1.1)
    try:
        resp = await client.patch(
            f"/api/v1/employees/{employee_id}",
            json={"full_name": f"{original_full_name} Edited"},
            headers=admin_headers,
        )
        assert resp.status_code == 200, resp.text

        with db_cursor() as cur:
            cur.execute("SELECT updated_at FROM employees WHERE id = %s", (employee_id,))
            updated_at_after = cur.fetchone()["updated_at"]

        assert updated_at_after > updated_at_before
    finally:
        with db_cursor() as cur:
            cur.execute(
                "UPDATE employees SET full_name = %s WHERE id = %s",
                (original_full_name, employee_id),
            )
