"""Read-only guarantee: the sync cycle must not touch the write-back outbox unless TALLY_WRITEBACK_ENABLED is set."""
import unittest
from unittest.mock import MagicMock, patch

from tally_sync_agent.engine.sync_engine import SyncEngine


def _engine():
    tally, backend = MagicMock(), MagicMock()
    tally.get_company_info.return_value = {"name": "Test Co", "guid": "g-1"}
    backend.get_pending_writeback_jobs.return_value = []
    engine = SyncEngine(tally_client=tally, backend_client=backend)
    engine.cust_extractor = MagicMock(extract_customers=MagicMock(return_value=[]))
    engine.inv_extractor = MagicMock(extract_invoices=MagicMock(return_value=[]))
    engine.pmt_extractor = MagicMock(extract_payments=MagicMock(return_value=[]))
    return engine, tally, backend


class TestWritebackGate(unittest.TestCase):
    def test_default_is_disabled(self):
        from tally_sync_agent.config.settings import SyncAgentSettings

        with patch.dict("os.environ", {}, clear=False) as env:
            env.pop("TALLY_WRITEBACK_ENABLED", None)
            self.assertFalse(SyncAgentSettings.load().writeback_enabled)

    def test_disabled_never_polls_or_posts(self):
        engine, tally, backend = _engine()
        with patch("tally_sync_agent.engine.sync_engine.settings") as s:
            s.writeback_enabled = False
            s.batch_size = 100
            res = engine.run_sync()
        backend.get_pending_writeback_jobs.assert_not_called()
        tally.import_receipt.assert_not_called()
        self.assertTrue(res["writeback"].get("disabled"))

    def test_enabled_polls_outbox(self):
        engine, tally, backend = _engine()
        with patch("tally_sync_agent.engine.sync_engine.settings") as s:
            s.writeback_enabled = True
            s.batch_size = 100
            engine.run_sync()
        backend.get_pending_writeback_jobs.assert_called_once()


if __name__ == "__main__":
    unittest.main()
