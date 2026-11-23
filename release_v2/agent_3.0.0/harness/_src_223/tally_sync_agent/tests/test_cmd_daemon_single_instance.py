from unittest.mock import MagicMock, patch

from tally_sync_agent import main
from tally_sync_agent.config.settings import DEFAULT_MUTEX_NAME


def test_cmd_daemon_exits_without_starting_sync_engine_when_lock_already_held(capsys):
    """
    Integration-level check (not just the lock class in isolation): when another
    instance already holds the mutex, cmd_daemon must return immediately WITHOUT ever
    constructing the sync engine or the heartbeat thread.
    """
    with patch.object(main, "SingleInstanceLock") as MockLock, \
         patch.object(main, "MultiFySync") as MockEngine, \
         patch.object(main, "_new_heartbeat") as MockHb:

        MockLock.return_value.acquire.return_value = False

        main.cmd_daemon(None)

        MockEngine.assert_not_called()
        MockHb.assert_not_called()
        MockLock.return_value.release.assert_not_called()  # nothing to release - never acquired
        assert MockLock.call_args.args[0] == DEFAULT_MUTEX_NAME, "default instance keeps the 1.2.1 mutex name"

    output = capsys.readouterr().out
    assert "Another daemon instance is already running" in output


def test_cmd_daemon_releases_lock_and_stops_heartbeat_on_keyboard_interrupt():
    """When the lock IS acquired and the loop is interrupted, the lock must be released and the
    heartbeat thread stopped on the way out (so a subsequent launch isn't permanently blocked)."""
    with patch.object(main, "SingleInstanceLock") as MockLock, \
         patch.object(main, "MultiFySync") as MockEngine, \
         patch.object(main, "_new_heartbeat") as MockHb, \
         patch.object(main, "time") as MockTime:

        MockLock.return_value.acquire.return_value = True
        MockHb.return_value.is_alive.return_value = True
        MockEngine.return_value.run_cycle.side_effect = KeyboardInterrupt()
        MockTime.time.return_value = 10_000_000.0

        main.cmd_daemon(None)

        MockLock.return_value.release.assert_called_once()
        MockHb.return_value.start.assert_called_once()
        MockHb.return_value.stop.assert_called_once()
