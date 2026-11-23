import tempfile
from pathlib import Path
from tally_sync_agent.core.checkpoint_manager import CheckpointManager


def test_checkpoint_manager():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_file = Path(tmpdir) / "test_cp.db"
        cm = CheckpointManager(db_path=db_file)

        # Initial state should be empty
        init_cp = cm.get_checkpoint("customers")
        assert init_cp["last_alter_id"] == 0
        assert init_cp["total_synced_records"] == 0

        # Update checkpoint
        cm.update_checkpoint("customers", alter_id=150, records_count=50)

        updated_cp = cm.get_checkpoint("customers")
        assert updated_cp["last_alter_id"] == 150
        assert updated_cp["total_synced_records"] == 50
        assert updated_cp["last_successful_sync_at"] is not None

        # Cumulative records
        cm.update_checkpoint("customers", alter_id=200, records_count=30)
        final_cp = cm.get_checkpoint("customers")
        assert final_cp["last_alter_id"] == 200
        assert final_cp["total_synced_records"] == 80
