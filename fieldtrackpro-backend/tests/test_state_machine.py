"""
State machine unit tests — validate all visit status transitions.
No database required.
"""
from __future__ import annotations

import pytest

from app.exceptions.custom import InvalidStateTransitionException
from app.models.visit import VisitStatus
from app.services.visit_state_machine import assert_valid_transition, is_terminal


# ---------------------------------------------------------------------------
# Valid transitions
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("source, target", [
    (VisitStatus.PENDING,     VisitStatus.IN_PROGRESS),
    (VisitStatus.PENDING,     VisitStatus.MISSED),
    (VisitStatus.IN_PROGRESS, VisitStatus.COMPLETED),
    (VisitStatus.IN_PROGRESS, VisitStatus.FLAGGED),
    (VisitStatus.FLAGGED,     VisitStatus.IN_PROGRESS),
    (VisitStatus.FLAGGED,     VisitStatus.COMPLETED),
])
def test_valid_transition(source, target):
    # Should not raise
    assert_valid_transition(source, target)


# ---------------------------------------------------------------------------
# Invalid transitions
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("source, target", [
    (VisitStatus.COMPLETED,   VisitStatus.PENDING),
    (VisitStatus.COMPLETED,   VisitStatus.IN_PROGRESS),
    (VisitStatus.COMPLETED,   VisitStatus.MISSED),
    (VisitStatus.MISSED,      VisitStatus.PENDING),
    (VisitStatus.MISSED,      VisitStatus.IN_PROGRESS),
    (VisitStatus.MISSED,      VisitStatus.COMPLETED),
    (VisitStatus.PENDING,     VisitStatus.COMPLETED),
    (VisitStatus.PENDING,     VisitStatus.FLAGGED),
    (VisitStatus.IN_PROGRESS, VisitStatus.MISSED),
    (VisitStatus.FLAGGED,     VisitStatus.MISSED),
])
def test_invalid_transition_raises(source, target):
    with pytest.raises(InvalidStateTransitionException):
        assert_valid_transition(source, target)


# ---------------------------------------------------------------------------
# Terminal states
# ---------------------------------------------------------------------------

def test_completed_is_terminal():
    assert is_terminal(VisitStatus.COMPLETED) is True


def test_missed_is_terminal():
    assert is_terminal(VisitStatus.MISSED) is True


def test_pending_not_terminal():
    assert is_terminal(VisitStatus.PENDING) is False


def test_in_progress_not_terminal():
    assert is_terminal(VisitStatus.IN_PROGRESS) is False


def test_flagged_not_terminal():
    assert is_terminal(VisitStatus.FLAGGED) is False
