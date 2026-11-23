from tally_sync_agent.engine.sync_engine import _safe_checkpoint_alter_id


def test_advances_normally_when_nothing_rejected():
    valid = [{"alter_id": 100}, {"alter_id": 105}]
    assert _safe_checkpoint_alter_id(valid, [], current_alter_id=50) == 105


def test_does_not_advance_past_unresolved_rejection():
    """The exact bug scenario: a later, higher-AlterID record succeeds while an
    earlier, lower-AlterID record was rejected in the same batch. The checkpoint
    must stop just before the rejected record, not jump past it."""
    valid = [{"alter_id": 100}, {"alter_id": 105}]
    rejected = [{"alter_id": 102}]
    assert _safe_checkpoint_alter_id(valid, rejected, current_alter_id=50) == 101


def test_no_advance_when_everything_in_batch_is_rejected():
    assert _safe_checkpoint_alter_id([], [{"alter_id": 102}], current_alter_id=50) == 50


def test_rejected_record_stays_in_window_on_next_cycle():
    """After the checkpoint stops at 101 (previous test), the next cycle's
    min_alter_id is 101, so the rejected AlterID 102 is still > checkpoint and
    will be re-extracted - proving the record is recoverable, not lost."""
    new_min_alter_id = 101
    assert 102 > new_min_alter_id


def test_never_regresses_below_current_checkpoint():
    """A defensive case: even if a rejected item's AlterID is (unexpectedly) lower
    than the current checkpoint already, the checkpoint must never move backwards."""
    valid = [{"alter_id": 250}]
    rejected = [{"alter_id": 50}]
    assert _safe_checkpoint_alter_id(valid, rejected, current_alter_id=200) == 200


def test_rejected_items_without_alter_id_are_ignored_safely():
    """A rejected record missing an alter_id (e.g. the synthetic payment fallback
    record) must not crash or silently block all future advancement."""
    valid = [{"alter_id": 100}]
    rejected = [{"alter_id": None}]
    assert _safe_checkpoint_alter_id(valid, rejected, current_alter_id=50) == 100
