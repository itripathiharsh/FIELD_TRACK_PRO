from unittest.mock import MagicMock, patch

from tally_sync_agent import main


def test_cmd_health_does_not_crash_when_tally_is_offline(capsys):
    """
    Regression test: cmd_health used to reference `c_info` in the backend-heartbeat
    block even when `tally.get_company_info()` raised before `c_info` was ever
    assigned, causing "cannot access local variable 'c_info'" instead of a clean
    OFFLINE status. `c_info` must now be initialized before the first try block.
    """
    with patch.object(main, "TallyClient") as MockTally, \
         patch.object(main, "BackendClient") as MockBackend, \
         patch.object(main, "CheckpointManager") as MockCheckpoints, \
         patch.object(main, "RetryQueue") as MockRetryQueue:

        MockTally.return_value.get_company_info.side_effect = Exception("Could not connect to Tally")
        MockBackend.return_value.heartbeat.return_value = {"status": "OK"}
        MockCheckpoints.return_value.get_all_checkpoints.return_value = {}
        MockRetryQueue.return_value.count_pending.return_value = 0

        main.cmd_health(None)

    output = capsys.readouterr().out
    assert "cannot access local variable" not in output
    assert "UnboundLocalError" not in output
    assert "Tally Status:     OFFLINE" in output
    # The backend heartbeat call must still succeed and report CONNECTED,
    # proving the fix didn't just swallow the error silently.
    assert "Backend Status:   CONNECTED" in output


def test_cmd_health_reports_connected_when_tally_is_online(capsys):
    """Companion case: confirms the fix didn't change the normal success path."""
    with patch.object(main, "TallyClient") as MockTally, \
         patch.object(main, "BackendClient") as MockBackend, \
         patch.object(main, "CheckpointManager") as MockCheckpoints, \
         patch.object(main, "RetryQueue") as MockRetryQueue:

        MockTally.return_value.get_company_info.return_value = {
            "name": "SGRG SERVICES (OPC) PRIVATE LIMITED",
            "guid": "19a03e17-e1ab-44f2-8e7f-1bff56f20ebe",
        }
        MockBackend.return_value.heartbeat.return_value = {"status": "OK"}
        MockCheckpoints.return_value.get_all_checkpoints.return_value = {}
        MockRetryQueue.return_value.count_pending.return_value = 0

        main.cmd_health(None)

    output = capsys.readouterr().out
    assert "Tally Status:     CONNECTED" in output
    assert "Active Company:   SGRG SERVICES (OPC) PRIVATE LIMITED" in output
    assert "Backend Status:   CONNECTED" in output
