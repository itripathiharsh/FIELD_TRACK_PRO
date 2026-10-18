"""Pure-logic tests for scripts/preflight_db_revision.py (the read-only pre-migration inspector). No database needed."""
from __future__ import annotations

import pytest

from scripts import preflight_db_revision as chk


@pytest.fixture(scope="module")
def chain():
    order, downs = chk.load_chain()
    return order, downs


def test_repository_has_a_single_linear_head(chain):
    order, downs = chain
    assert len(order) == len(set(order)) >= 50
    assert downs[order[0]] is None
    assert all(downs[order[i]] == order[i - 1] for i in range(1, len(order)))   # strictly linear, no branches


def test_purge_migration_is_in_the_chain_and_before_the_security_migration(chain):
    order, _ = chain
    assert chk.PURGE_REVISION in order
    assert order.index(chk.PURGE_REVISION) < order.index("b9c0d1e2f3a4") == len(order) - 1


def test_pending_after_orders_the_remaining_migrations(chain):
    order, _ = chain
    assert chk.pending_after(order, order[-1]) == []
    assert chk.pending_after(order, None) == order
    mid = order[10]
    assert chk.pending_after(order, mid) == order[11:]
    with pytest.raises(ValueError):
        chk.pending_after(order, "not-a-revision")


def test_classify_purge_applied_vs_pending(chain):
    order, _ = chain
    i = order.index(chk.PURGE_REVISION)
    assert chk.classify_purge(order, order[i - 1]) == "pending"
    assert chk.classify_purge(order, chk.PURGE_REVISION) == "applied"
    assert chk.classify_purge(order, order[-1]) == "applied"
    assert chk.classify_purge(order, None) == "pending"
    assert chk.classify_purge(order, "unknown") == "pending"


def test_script_is_select_only():
    import inspect
    import re

    body = inspect.getsource(chk).split("def main()", 1)[1]
    writes = re.compile(r"(INSERT\s+INTO|UPDATE\s+\w+\s+SET|DELETE\s+FROM|DROP\s+(TABLE|DATABASE)|ALTER\s+TABLE|TRUNCATE|CREATE\s+(TABLE|INDEX))", re.I)
    assert not writes.search(body)
    assert "SET TRANSACTION READ ONLY" in body and "default_transaction_read_only=on" in body
