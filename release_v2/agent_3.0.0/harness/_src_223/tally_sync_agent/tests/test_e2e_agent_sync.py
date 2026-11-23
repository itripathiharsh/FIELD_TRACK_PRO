import tempfile
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from tally_sync_agent.config.settings import SyncAgentSettings
from tally_sync_agent.core.checkpoint_manager import CheckpointManager
from tally_sync_agent.core.quarantine_store import QuarantineStore
from tally_sync_agent.core.retry_queue import RetryQueue
from tally_sync_agent.engine.sync_engine import SyncEngine
from tally_sync_agent.extractors.invoice_extractor import InvoiceExtractor


def test_sync_engine_flow_with_mocks():
    """
    Tests full SyncEngine flow:
    1. Extract customer, invoice, payment
    2. Upload to backend
    3. Verify checkpoint advanced
    4. Verify durable retry queue handled on failure
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_engine.db"
        cm = CheckpointManager(db_path=db_path)
        rq = RetryQueue(db_path=db_path)
        qs = QuarantineStore(db_path=db_path)

        # Mock TallyClient
        mock_tally = MagicMock()
        mock_tally.get_company_info.return_value = {
            "name": "SGRG SERVICES (OPC) PRIVATE LIMITED",
            "guid": "19a03e17-e1ab-44f2-8e7f-1bff56f20ebe",
            "starting_date": "2026-04-01",
            "ending_date": "2026-08-18",
        }

        # Mock BackendClient
        mock_backend = MagicMock()
        mock_backend.heartbeat.return_value = {"status": "OK"}
        mock_backend.sync_customers.return_value = {"created_count": 1, "updated_count": 0}
        mock_backend.sync_invoices.return_value = {"created_count": 1, "updated_count": 0}
        mock_backend.sync_payments.return_value = {"created_count": 1, "updated_count": 0}

        engine = SyncEngine(
            tally_client=mock_tally,
            backend_client=mock_backend,
            checkpoint_manager=cm,
            retry_queue=rq,
            quarantine_store=qs,
        )

        # Mock extractors returning sample data
        engine.cust_extractor.extract_customers = MagicMock(return_value=[
            {
                "source_reference": "TALLY_GUID_C_1",
                "name": "Aashi Mobile World (Philips)",
                "parent_group": "Sundry Debtors- PH.",
                "brand": "Philips",
                "outlet_code": "UPDD00678399",
                "address": "Kanpur",
                "alter_id": 500,
            }
        ])

        engine.inv_extractor.extract_invoices = MagicMock(return_value=[
            {
                "source_reference": "TALLY_INV_GUID_1",
                "invoice_number": "INV-001",
                "customer_name": "Aashi Mobile World",
                "outlet_code": "UPDD00678399",
                "invoice_date": "2026-08-18",
                "due_date": "2026-09-08",
                "amount": 1080.00,
                "brand": "Philips",
                "voucher_type": "Sales",
                "alter_id": 600,
            }
        ])

        engine.pmt_extractor.extract_payments = MagicMock(return_value=[
            {
                "source_reference": "TALLY_RCPT_GUID_1",
                "receipt_number": "RCPT-001",
                "customer_name": "Aashi Mobile World",
                "outlet_code": "UPDD00678399",
                "payment_date": "2026-08-18",
                "amount": 1080.00,
                "payment_method": "ONLINE",
                "utr_reference": "UTR991823",
                "brand_allocations": [{"brand": "Philips", "allocated_amount": 1080.00}],
                "alter_id": 700,
            }
        ])

        # Run sync cycle
        results = engine.run_sync(is_initial=True)

        assert results["status"] == "COMPLETED"
        assert results["customers"]["uploaded"] == 1
        assert results["invoices"]["uploaded"] == 1
        assert results["payments"]["uploaded"] == 1

        # Verify checkpoints advanced
        cust_cp = cm.get_checkpoint("customers")
        assert cust_cp["last_alter_id"] == 500
        assert cust_cp["total_synced_records"] == 1

        inv_cp = cm.get_checkpoint("invoices")
        assert inv_cp["last_alter_id"] == 600
        assert inv_cp["total_synced_records"] == 1

        pmt_cp = cm.get_checkpoint("payments")
        assert pmt_cp["last_alter_id"] == 700
        assert pmt_cp["total_synced_records"] == 1

        # Verify no items in retry queue
        assert rq.count_pending() == 0
        # Verify nothing was quarantined (all records were valid)
        assert qs.count_unresolved() == 0


def test_sync_engine_network_failure_queuing():
    """
    Simulates backend network failure:
    1. Backend raises exception
    2. Batch is placed in local durable retry queue
    3. Checkpoint does NOT advance
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_engine_fail.db"
        cm = CheckpointManager(db_path=db_path)
        rq = RetryQueue(db_path=db_path)
        qs = QuarantineStore(db_path=db_path)

        mock_tally = MagicMock()
        mock_tally.get_company_info.return_value = {
            "name": "SGRG SERVICES (OPC) PRIVATE LIMITED",
            "guid": "19a03e17-e1ab-44f2-8e7f-1bff56f20ebe",
        }

        # Mock BackendClient that fails with network error
        mock_backend = MagicMock()
        mock_backend.heartbeat.return_value = {"status": "OK"}
        mock_backend.sync_customers.side_effect = Exception("Connection Refused / Network Down")
        mock_backend.sync_invoices.side_effect = Exception("Connection Refused / Network Down")
        mock_backend.sync_payments.side_effect = Exception("Connection Refused / Network Down")

        engine = SyncEngine(
            tally_client=mock_tally,
            backend_client=mock_backend,
            checkpoint_manager=cm,
            retry_queue=rq,
            quarantine_store=qs,
        )

        engine.cust_extractor.extract_customers = MagicMock(return_value=[
            {
                "source_reference": "TALLY_GUID_C_1",
                "name": "Aashi Mobile World",
                "alter_id": 500,
            }
        ])
        engine.inv_extractor.extract_invoices = MagicMock(return_value=[])
        engine.pmt_extractor.extract_payments = MagicMock(return_value=[])

        results = engine.run_sync(is_initial=True)

        assert results["customers"]["uploaded"] == 0
        assert results["customers"]["failed"] == 1

        # Checkpoint MUST NOT advance!
        cust_cp = cm.get_checkpoint("customers")
        assert cust_cp["last_alter_id"] == 0
        assert cust_cp["total_synced_records"] == 0

        # Durable retry queue MUST contain the failed customer batch
        assert rq.count_pending() == 1


def test_sync_engine_mixed_batch_checkpoint_protected_and_quarantined():
    """
    The exact bug scenario end-to-end: one invoice fails validation (lower AlterID),
    one invoice is valid and uploads successfully (higher AlterID), in the same cycle.
    The checkpoint must not advance past the rejected one, and the rejected one must
    be durably quarantined (not just logged).
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_mixed.db"
        cm = CheckpointManager(db_path=db_path)
        rq = RetryQueue(db_path=db_path)
        qs = QuarantineStore(db_path=db_path)

        mock_tally = MagicMock()
        mock_tally.get_company_info.return_value = {
            "name": "SGRG SERVICES (OPC) PRIVATE LIMITED",
            "guid": "19a03e17-e1ab-44f2-8e7f-1bff56f20ebe",
        }

        mock_backend = MagicMock()
        mock_backend.heartbeat.return_value = {"status": "OK"}
        mock_backend.sync_invoices.return_value = {"created_count": 1, "updated_count": 0}

        engine = SyncEngine(
            tally_client=mock_tally,
            backend_client=mock_backend,
            checkpoint_manager=cm,
            retry_queue=rq,
            quarantine_store=qs,
        )

        engine.cust_extractor.extract_customers = MagicMock(return_value=[])
        engine.pmt_extractor.extract_payments = MagicMock(return_value=[])
        engine.inv_extractor.extract_invoices = MagicMock(return_value=[
            {
                # Rejected: missing customer_name, LOWER alter_id
                "source_reference": "GUID-REJECTED",
                "invoice_number": "SGRG/UNO/11",
                "customer_name": "",
                "invoice_date": "2026-11-13",
                "amount": 0.0,
                "alter_id": 102,
            },
            {
                # Valid: HIGHER alter_id, uploads successfully
                "source_reference": "GUID-VALID",
                "invoice_number": "SGRG/KNP/3624",
                "customer_name": "Aashi Mobile World",
                "invoice_date": "2026-11-13",
                "amount": 91340.00,
                "alter_id": 105,
            },
        ])

        results = engine.run_sync(is_initial=True)

        assert results["invoices"]["uploaded"] == 1
        assert results["invoices"]["failed"] == 1

        # Checkpoint must stop at 101 (102 - 1), NOT jump to 105
        inv_cp = cm.get_checkpoint("invoices")
        assert inv_cp["last_alter_id"] == 101

        # The rejected record must be durably quarantined, not just logged
        assert qs.count_unresolved("invoices") == 1
        quarantined = qs.list_unresolved("invoices")[0]
        assert quarantined["source_reference"] == "GUID-REJECTED"
        assert quarantined["error"] == "Missing customer_name"


def test_sync_engine_recovery_is_idempotent_and_resolves_quarantine():
    """
    Simulates the real recovery path across two sync cycles:
    cycle 1 - the record is rejected and quarantined, checkpoint stops before it.
    cycle 2 - the SAME source_reference now extracts cleanly (e.g. the client fixed
    the voucher / it's no longer blank) and uploads successfully. The checkpoint
    advances past it, it's removed from the unresolved quarantine list, and nothing
    about this is a duplicate (same source_reference both times -> one upsert key).
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_recovery.db"
        cm = CheckpointManager(db_path=db_path)
        rq = RetryQueue(db_path=db_path)
        qs = QuarantineStore(db_path=db_path)

        mock_tally = MagicMock()
        mock_tally.get_company_info.return_value = {
            "name": "SGRG SERVICES (OPC) PRIVATE LIMITED",
            "guid": "19a03e17-e1ab-44f2-8e7f-1bff56f20ebe",
        }
        mock_backend = MagicMock()
        mock_backend.heartbeat.return_value = {"status": "OK"}
        mock_backend.sync_invoices.return_value = {"created_count": 1, "updated_count": 0}

        engine = SyncEngine(
            tally_client=mock_tally,
            backend_client=mock_backend,
            checkpoint_manager=cm,
            retry_queue=rq,
            quarantine_store=qs,
        )
        engine.cust_extractor.extract_customers = MagicMock(return_value=[])
        engine.pmt_extractor.extract_payments = MagicMock(return_value=[])

        # Cycle 1: rejected, nothing else in this batch
        engine.inv_extractor.extract_invoices = MagicMock(return_value=[
            {
                "source_reference": "GUID-RECOVERABLE",
                "invoice_number": "SGRG/UNO/11",
                "customer_name": "",
                "invoice_date": "2026-11-13",
                "amount": 0.0,
                "alter_id": 102,
            },
        ])
        engine.run_sync(is_initial=True)

        assert cm.get_checkpoint("invoices")["last_alter_id"] == 0  # did not advance at all
        assert qs.count_unresolved("invoices") == 1

        # Cycle 2: same source_reference, now has a real customer_name
        engine.inv_extractor.extract_invoices = MagicMock(return_value=[
            {
                "source_reference": "GUID-RECOVERABLE",
                "invoice_number": "SGRG/UNO/11",
                "customer_name": "Aashi Mobile World",
                "invoice_date": "2026-11-13",
                "amount": 1000.00,
                "alter_id": 102,
            },
        ])
        results = engine.run_sync(is_initial=False)

        assert results["invoices"]["uploaded"] == 1
        assert cm.get_checkpoint("invoices")["last_alter_id"] == 102
        # No longer unresolved - the recovery was detected and recorded
        assert qs.count_unresolved("invoices") == 0
        # sync_invoices was called twice total, each time with exactly one record
        # for this reference - confirms no duplicate accumulation across cycles
        assert mock_backend.sync_invoices.call_count == 1


def test_sync_engine_quarantine_blocks_checkpoint_across_cycles_even_if_record_absent_later():
    """
    Exact scenario: cycle 1 rejects AlterID 102 and succeeds on AlterID 105 (checkpoint
    stops at 101). Cycle 2 succeeds on AlterID 110, but AlterID 102 is NOT returned by
    Tally at all this time (simulating any reason it's temporarily absent from the
    extraction). The checkpoint must still not advance past 101, because AlterID 102
    is still unresolved in the durable quarantine - even though it's invisible to this
    cycle's own batch.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_cross_cycle.db"
        cm = CheckpointManager(db_path=db_path)
        rq = RetryQueue(db_path=db_path)
        qs = QuarantineStore(db_path=db_path)

        mock_tally = MagicMock()
        mock_tally.get_company_info.return_value = {
            "name": "SGRG SERVICES (OPC) PRIVATE LIMITED",
            "guid": "19a03e17-e1ab-44f2-8e7f-1bff56f20ebe",
        }
        mock_backend = MagicMock()
        mock_backend.heartbeat.return_value = {"status": "OK"}
        mock_backend.sync_invoices.side_effect = (
            lambda batch_id, guid, batch: {"created_count": len(batch), "updated_count": 0}
        )

        engine = SyncEngine(
            tally_client=mock_tally,
            backend_client=mock_backend,
            checkpoint_manager=cm,
            retry_queue=rq,
            quarantine_store=qs,
        )
        engine.cust_extractor.extract_customers = MagicMock(return_value=[])
        engine.pmt_extractor.extract_payments = MagicMock(return_value=[])

        # Cycle 1: AlterID 102 rejected, AlterID 105 succeeds
        engine.inv_extractor.extract_invoices = MagicMock(return_value=[
            {
                "source_reference": "GUID-102",
                "invoice_number": "SGRG/UNO/11",
                "customer_name": "",
                "invoice_date": "2026-11-13",
                "amount": 0.0,
                "alter_id": 102,
            },
            {
                "source_reference": "GUID-105",
                "invoice_number": "SGRG/KNP/3624",
                "customer_name": "Aashi Mobile World",
                "invoice_date": "2026-11-13",
                "amount": 91340.00,
                "alter_id": 105,
            },
        ])
        engine.run_sync(is_initial=True)

        assert cm.get_checkpoint("invoices")["last_alter_id"] == 101
        assert qs.count_unresolved("invoices") == 1

        # Cycle 2: AlterID 110 succeeds; AlterID 102 is NOT returned by Tally this time
        engine.inv_extractor.extract_invoices = MagicMock(return_value=[
            {
                "source_reference": "GUID-110",
                "invoice_number": "SGRG/KNP/3625",
                "customer_name": "Aashi Mobile World",
                "invoice_date": "2026-11-13",
                "amount": 1000.00,
                "alter_id": 110,
            },
        ])
        results = engine.run_sync(is_initial=False)

        # GUID-110 itself still uploads successfully...
        assert results["invoices"]["uploaded"] == 1
        # ...but the checkpoint must NOT silently jump to 110 past the unresolved GUID-102
        assert cm.get_checkpoint("invoices")["last_alter_id"] == 101
        # GUID-102's quarantine entry must still be unresolved - untouched by cycle 2
        assert qs.count_unresolved("invoices") == 1
        assert qs.list_unresolved("invoices")[0]["source_reference"] == "GUID-102"

        # Cycle 3: GUID-102 finally comes back fixed, and GUID-110 is re-sent again
        # (expected and safe: checkpoint was held back, so it's back in the window)
        engine.inv_extractor.extract_invoices = MagicMock(return_value=[
            {
                "source_reference": "GUID-102",
                "invoice_number": "SGRG/UNO/11",
                "customer_name": "Aashi Mobile World",
                "invoice_date": "2026-11-13",
                "amount": 500.00,
                "alter_id": 102,
            },
            {
                "source_reference": "GUID-110",
                "invoice_number": "SGRG/KNP/3625",
                "customer_name": "Aashi Mobile World",
                "invoice_date": "2026-11-13",
                "amount": 1000.00,
                "alter_id": 110,
            },
        ])
        results = engine.run_sync(is_initial=False)

        assert results["invoices"]["uploaded"] == 2
        # Now that GUID-102 is resolved in this same cycle, checkpoint can advance to 110
        assert cm.get_checkpoint("invoices")["last_alter_id"] == 110
        assert qs.count_unresolved("invoices") == 0


def test_invoice_extractor_cannot_recover_a_record_already_below_checkpoint():
    """
    Documents a hard limitation (not a bug to fix): once the checkpoint has already
    advanced past a given AlterID in a PAST cycle (before this fix existed, or for any
    other reason), that record can never be recovered by this fix. Both Tally's own
    server-side filter and the extractor's own client-side guard
    (`alter_id <= min_alter_id: continue`) exclude it before validation or quarantine
    ever sees it - there is nothing for the checkpoint-safety logic to protect, because
    the record never reaches it in the first place.
    """
    mock_tally = MagicMock()
    mock_tally.execute_tdl.return_value = ET.fromstring(
        """<ENVELOPE><BODY><DATA><COLLECTION>
        <VOUCHER>
          <VOUCHERNUMBER>SGRG/OLD/1</VOUCHERNUMBER>
          <GUID>GUID-ALREADY-PASSED</GUID>
          <DATE>20260601</DATE>
          <PARTYLEDGERNAME></PARTYLEDGERNAME>
          <BASICBUYERNAME></BASICBUYERNAME>
          <VOUCHERTYPENAME>Sales</VOUCHERTYPENAME>
          <ALTERID>118000</ALTERID>
          <AMOUNT>-1000.00</AMOUNT>
          <ISCANCELLED>No</ISCANCELLED>
        </VOUCHER>
        </COLLECTION></DATA></BODY></ENVELOPE>"""
    )

    extractor = InvoiceExtractor(mock_tally)
    # The production checkpoint is already at 120213, well above this record's AlterID
    results = extractor.extract_invoices(from_date="2026-04-01", to_date="2026-11-13", min_alter_id=120213)

    assert results == []  # never extracted, never reaches validation/quarantine at all
