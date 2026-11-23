import tempfile
from pathlib import Path
from tally_sync_agent.core.retry_queue import RetryQueue


def test_retry_queue():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_file = Path(tmpdir) / "test_retry.db"
        rq = RetryQueue(db_path=db_file)

        assert rq.count_pending() == 0

        # Enqueue a batch with 0 delay so it's immediately ready
        q_id = rq.enqueue(
            batch_type="customers",
            batch_id="batch-001",
            company_guid="GUID-XYZ",
            records=[{"name": "Outlet A"}],
            initial_delay_seconds=0,
        )

        assert rq.count_pending() == 1

        ready = rq.get_pending_ready()
        assert len(ready) == 1
        assert ready[0]["batch_id"] == "batch-001"
        assert ready[0]["records"][0]["name"] == "Outlet A"

        # Mark failure to test exponential backoff
        rq.mark_failure(q_id, "HTTP 503 Service Unavailable")
        # Since backoff is at least 60s, it won't be ready immediately
        ready_after_fail = rq.get_pending_ready()
        assert len(ready_after_fail) == 0

        # Mark success removes it
        rq.mark_success(q_id)
        assert rq.count_pending() == 0
