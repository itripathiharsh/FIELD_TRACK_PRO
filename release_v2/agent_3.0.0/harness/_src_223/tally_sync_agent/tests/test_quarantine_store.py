import tempfile
from pathlib import Path

from tally_sync_agent.core.quarantine_store import QuarantineStore


def test_quarantine_add_and_list():
    with tempfile.TemporaryDirectory() as tmpdir:
        qs = QuarantineStore(db_path=Path(tmpdir) / "q.db")

        qs.add("invoices", "GUID-1", 100, "Missing customer_name", {"invoice_number": "INV-1"})

        rows = qs.list_unresolved("invoices")
        assert len(rows) == 1
        assert rows[0]["source_reference"] == "GUID-1"
        assert rows[0]["alter_id"] == 100
        assert rows[0]["error"] == "Missing customer_name"
        assert rows[0]["occurrences"] == 1
        assert qs.count_unresolved() == 1


def test_quarantine_does_not_duplicate_on_repeated_processing():
    """The same record failing validation again in a later cycle must update the
    existing row, not create a second one."""
    with tempfile.TemporaryDirectory() as tmpdir:
        qs = QuarantineStore(db_path=Path(tmpdir) / "q.db")

        qs.add("invoices", "GUID-1", 100, "Missing customer_name", {"invoice_number": "INV-1"})
        qs.add("invoices", "GUID-1", 100, "Missing customer_name", {"invoice_number": "INV-1"})
        qs.add("invoices", "GUID-1", 100, "Missing customer_name", {"invoice_number": "INV-1"})

        assert qs.count_unresolved() == 1
        rows = qs.list_unresolved("invoices")
        assert rows[0]["occurrences"] == 3


def test_quarantine_separate_entities_do_not_collide():
    with tempfile.TemporaryDirectory() as tmpdir:
        qs = QuarantineStore(db_path=Path(tmpdir) / "q.db")

        qs.add("invoices", "SAME-REF", 1, "Missing customer_name", {})
        qs.add("payments", "SAME-REF", 2, "Missing customer_name", {})

        assert qs.count_unresolved() == 2
        assert qs.count_unresolved("invoices") == 1
        assert qs.count_unresolved("payments") == 1


def test_quarantine_mark_resolved_excludes_from_unresolved_list():
    with tempfile.TemporaryDirectory() as tmpdir:
        qs = QuarantineStore(db_path=Path(tmpdir) / "q.db")

        qs.add("invoices", "GUID-1", 100, "Missing customer_name", {})
        assert qs.count_unresolved() == 1

        qs.mark_resolved("invoices", "GUID-1")
        assert qs.count_unresolved() == 0

        # If it fails validation again later, it reappears as unresolved
        qs.add("invoices", "GUID-1", 105, "Missing customer_name", {})
        assert qs.count_unresolved() == 1
