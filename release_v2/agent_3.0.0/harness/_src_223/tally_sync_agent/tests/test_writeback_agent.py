import unittest
from unittest.mock import MagicMock, patch

from tally_sync_agent.core.tally_client import TallyClient, TallyImportResult, TallyConnectionError
from tally_sync_agent.engine.sync_engine import SyncEngine


class TestTallyWritebackAgent(unittest.TestCase):

    def setUp(self):
        self.client = TallyClient(base_url="http://127.0.0.1:9000", timeout=5)

    def test_build_receipt_xml_cash(self):
        job_data = {
            "payment_id": "d1234567-89ab-cdef-0123-456789abcdef",
            "customer_name": "Baba Mobiles (OPPO)",
            "employee_name": "Sahil Verma",
            "amount": 500.00,
            "payment_date": "2026-09-06",
            "payment_method": "CASH",
            "notes": "Cash on visit",
        }
        xml = self.client.build_receipt_xml(job_data)
        self.assertIn("<VOUCHERTYPENAME>Receipt</VOUCHERTYPENAME>", xml)
        self.assertIn("<PARTYLEDGERNAME>Baba Mobiles (OPPO)</PARTYLEDGERNAME>", xml)
        self.assertIn("<LEDGERNAME>Cash</LEDGERNAME>", xml)
        self.assertIn("<AMOUNT>500.00</AMOUNT>", xml)
        self.assertIn("<AMOUNT>-500.00</AMOUNT>", xml)
        self.assertIn("Being Cash Rec. By Sahil Verma | FT:d1234567-89ab-cdef-0123-456789abcdef | Cash on visit", xml)
        self.assertIn('REMOTEID="ft_pmt_d1234567-89ab-cdef-0123-456789abcdef"', xml)
        self.assertIn("<BILLTYPE>On Account</BILLTYPE>", xml)

    def test_build_receipt_xml_bank_with_invoice(self):
        job_data = {
            "payment_id": "a9876543-21ba-fedc-ba98-76543210fedc",
            "customer_name": "Ahuja Electronics",
            "employee_name": "Sahil Verma",
            "amount": 1250.75,
            "payment_date": "2026-09-06",
            "payment_method": "ONLINE",
            "cheque_bank_name": "HDFC Bank",
            "invoice_number": "INV-2026-0042",
            "utr_reference": "UTR99887766",
            "notes": "UPI settlement",
        }
        xml = self.client.build_receipt_xml(job_data)
        self.assertIn("<LEDGERNAME>HDFC BANK A/c No. 50200093755673</LEDGERNAME>", xml)
        self.assertIn("<NAME>INV-2026-0042</NAME>", xml)
        self.assertIn("<BILLTYPE>Agst Ref</BILLTYPE>", xml)
        self.assertIn("Being Rec. By Sahil Verma | UTR:UTR99887766 | FT:a9876543-21ba-fedc-ba98-76543210fedc | UPI settlement", xml)

    def test_build_receipt_xml_cheque(self):
        job_data = {
            "payment_id": "b1112223-3344-5566-7788-99aabbccddeeff",
            "customer_name": "Satyam Electronics",
            "employee_name": "Sahil Verma",
            "amount": 10000.00,
            "payment_date": "2026-09-06",
            "payment_method": "CHEQUE",
            "cheque_number": "450123",
            "notes": "HDFC Cheque clearing",
        }
        xml = self.client.build_receipt_xml(job_data)
        self.assertIn("Being Rec. By Sahil Verma | CHQ:450123 | FT:b1112223-3344-5566-7788-99aabbccddeeff | HDFC Cheque clearing", xml)

    def test_parse_import_response_success(self):
        response_xml = """<RESPONSE>
 <CREATED>1</CREATED>
 <ALTERED>0</ALTERED>
 <DELETED>0</DELETED>
 <LASTVCHID>28445</LASTVCHID>
 <ERRORS>0</ERRORS>
 <EXCEPTIONS>0</EXCEPTIONS>
</RESPONSE>"""
        res = self.client.parse_import_response(response_xml)
        self.assertTrue(res.success)
        self.assertEqual(res.created_count, 1)
        self.assertEqual(res.last_vch_id, "28445")
        self.assertIsNone(res.error_message)

    def test_parse_import_response_missing_ledger_error(self):
        response_xml = """<RESPONSE>
 <LINEERROR>Ledger 'Unknown Store' does not exist!</LINEERROR>
 <CREATED>0</CREATED>
 <ALTERED>0</ALTERED>
 <LASTVCHID>0</LASTVCHID>
 <ERRORS>0</ERRORS>
 <EXCEPTIONS>1</EXCEPTIONS>
</RESPONSE>"""
        res = self.client.parse_import_response(response_xml)
        self.assertFalse(res.success)
        self.assertIn("does not exist", res.error_message)
        self.assertFalse(res.is_retryable)

    def test_sync_engine_process_writeback_success(self):
        mock_backend = MagicMock()
        mock_tally = MagicMock()

        engine = SyncEngine(tally_client=mock_tally, backend_client=mock_backend)

        mock_backend.get_pending_writeback_jobs.return_value = [
            {
                "id": "job-111",
                "payload": {
                    "payment_id": "pay-111",
                    "customer_name": "Test Customer",
                    "amount": 100.0,
                },
            }
        ]
        mock_tally.import_receipt.return_value = TallyImportResult(
            success=True,
            guid="guid-test-111",
            master_id="29000",
            voucher_number="123",
        )

        stats = engine.process_writeback_jobs()
        self.assertEqual(stats["polled"], 1)
        self.assertEqual(stats["succeeded"], 1)
        self.assertEqual(stats["failed"], 0)

        mock_backend.ack_writeback_job.assert_called_once_with(
            job_id="job-111",
            tally_guid="guid-test-111",
            tally_master_id="29000",
            tally_voucher_number="123",
        )

    def test_sync_engine_process_writeback_failure(self):
        mock_backend = MagicMock()
        mock_tally = MagicMock()

        engine = SyncEngine(tally_client=mock_tally, backend_client=mock_backend)

        mock_backend.get_pending_writeback_jobs.return_value = [
            {
                "id": "job-222",
                "payload": {
                    "payment_id": "pay-222",
                    "customer_name": "Bad Customer",
                    "amount": 200.0,
                },
            }
        ]
        mock_tally.import_receipt.return_value = TallyImportResult(
            success=False,
            error_message="Ledger 'Bad Customer' does not exist!",
            is_retryable=False,
        )

        stats = engine.process_writeback_jobs()
        self.assertEqual(stats["polled"], 1)
        self.assertEqual(stats["succeeded"], 0)
        self.assertEqual(stats["failed"], 1)

        mock_backend.fail_writeback_job.assert_called_once_with(
            job_id="job-222",
            error_message="Ledger 'Bad Customer' does not exist!",
            is_retryable=False,
        )

    def test_sync_engine_process_sales_order_writeback_success(self):
        mock_backend = MagicMock()
        mock_tally = MagicMock()

        engine = SyncEngine(tally_client=mock_tally, backend_client=mock_backend)

        mock_backend.get_pending_writeback_jobs.return_value = [
            {
                "id": "job-so-333",
                "entity_type": "SALES_ORDER",
                "payload": {
                    "order_id": "ord-333",
                    "order_number": "ORD-20260921-0001",
                    "customer_name": "ABC Electronics",
                    "total_amount": 100000.0,
                    "items": [
                        {"stock_item_name": "Samsung S25", "brand_name": "Samsung", "quantity": 2, "approved_rate": 30000.0, "line_amount": 60000.0}
                    ]
                },
            }
        ]
        mock_tally.import_sales_order.return_value = TallyImportResult(
            success=True,
            guid="guid-so-333",
            master_id="35000",
            voucher_number="SO-101",
        )

        stats = engine.process_writeback_jobs()
        self.assertEqual(stats["polled"], 1)
        self.assertEqual(stats["succeeded"], 1)
        self.assertEqual(stats["failed"], 0)

        mock_tally.import_sales_order.assert_called_once()
        mock_backend.ack_writeback_job.assert_called_once_with(
            job_id="job-so-333",
            tally_guid="guid-so-333",
            tally_master_id="35000",
            tally_voucher_number="SO-101",
        )

    def test_sync_engine_ack_failure_after_successful_post_does_not_report_tally_failure(self):
        """
        A duplicate-post guard: if the voucher reached Tally but the backend ACK
        itself fails (Render cold start, timeout), that must NOT be reported via
        fail_writeback_job - doing so would mark the job retryable and repost an
        already-successful receipt next cycle.
        """
        mock_backend = MagicMock()
        mock_tally = MagicMock()

        engine = SyncEngine(tally_client=mock_tally, backend_client=mock_backend)

        mock_backend.get_pending_writeback_jobs.return_value = [
            {
                "id": "job-444",
                "payload": {"payment_id": "pay-444", "customer_name": "Test Customer", "amount": 10.0},
            }
        ]
        mock_tally.import_receipt.return_value = TallyImportResult(
            success=True, guid="guid-444", master_id="1", voucher_number="1"
        )
        mock_backend.ack_writeback_job.side_effect = Exception("Render cold start timeout")

        stats = engine.process_writeback_jobs()

        self.assertEqual(stats["succeeded"], 0)
        self.assertEqual(stats["failed"], 1)
        mock_backend.fail_writeback_job.assert_not_called()


class TestTallyClientDuplicatePostPrevention(unittest.TestCase):
    """
    A re-claimed writeback job (ack failure after success, lease expiry, or a manual
    admin retry) must not blindly re-post to Tally - import_receipt/import_sales_order
    must look for an existing FT:{id} voucher first and, if found, ack it instead of
    creating a duplicate.
    """

    def setUp(self):
        self.client = TallyClient(base_url="http://127.0.0.1:9000", timeout=5)

    def test_import_receipt_skips_post_when_voucher_already_exists(self):
        job_data = {
            "payment_id": "existing-pay-1",
            "customer_name": "Test Customer",
            "amount": 500.0,
            "payment_date": "2026-10-01",
            "payment_method": "CASH",
        }
        with patch.object(
            self.client,
            "find_voucher_by_narration_marker",
            return_value={"guid": "guid-existing", "voucher_number": "77", "master_id": "900", "alter_id": 3},
        ) as mock_find, patch.object(self.client, "send_xml") as mock_send:
            result = self.client.import_receipt(job_data)

        mock_find.assert_called_once_with(payment_id="existing-pay-1", date_str="20261001")
        mock_send.assert_not_called()
        self.assertTrue(result.success)
        self.assertEqual(result.created_count, 0)
        self.assertEqual(result.guid, "guid-existing")
        self.assertEqual(result.voucher_number, "77")
        self.assertEqual(result.master_id, "900")

    def test_import_receipt_posts_when_no_existing_voucher(self):
        job_data = {
            "payment_id": "new-pay-1",
            "customer_name": "Test Customer",
            "employee_name": "Rep",
            "amount": 500.0,
            "payment_date": "2026-10-01",
            "payment_method": "CASH",
        }
        success_response = """<RESPONSE>
 <CREATED>1</CREATED>
 <ALTERED>0</ALTERED>
 <LASTVCHID>5</LASTVCHID>
 <ERRORS>0</ERRORS>
 <EXCEPTIONS>0</EXCEPTIONS>
</RESPONSE>"""
        with patch.object(
            self.client,
            "find_voucher_by_narration_marker",
            side_effect=[None, {"guid": "guid-new", "voucher_number": "88", "master_id": "901", "alter_id": 1}],
        ) as mock_find, patch.object(self.client, "send_xml", return_value=success_response) as mock_send:
            result = self.client.import_receipt(job_data)

        self.assertEqual(mock_find.call_count, 2)
        mock_send.assert_called_once()
        self.assertTrue(result.success)
        self.assertEqual(result.guid, "guid-new")
        self.assertEqual(result.voucher_number, "88")

    def test_import_sales_order_skips_post_when_voucher_already_exists(self):
        job_data = {
            "order_id": "existing-order-1",
            "order_number": "ORD-1",
            "customer_name": "Test Customer",
            "order_date": "2026-10-01",
            "total_amount": 1000.0,
            "items": [],
        }
        with patch.object(
            self.client,
            "find_order_by_marker",
            return_value={"guid": "guid-order-existing", "voucher_number": "SO-9", "master_id": "700", "alter_id": 2},
        ) as mock_find, patch.object(self.client, "send_xml") as mock_send:
            result = self.client.import_sales_order(job_data)

        mock_find.assert_called_once_with(order_id="existing-order-1", date_str="20261001")
        mock_send.assert_not_called()
        self.assertTrue(result.success)
        self.assertEqual(result.created_count, 0)
        self.assertEqual(result.guid, "guid-order-existing")
        self.assertEqual(result.voucher_number, "SO-9")


if __name__ == "__main__":
    unittest.main()

