"""
Visit state machine — encapsulates valid transitions and guard conditions.
"""
from __future__ import annotations

from app.exceptions.custom import InvalidStateTransitionException
from app.models.visit import VisitStatus

# Valid transitions per source status
_VALID_TRANSITIONS: dict[VisitStatus, set[VisitStatus]] = {
    VisitStatus.PENDING:     {VisitStatus.IN_PROGRESS, VisitStatus.MISSED},
    VisitStatus.IN_PROGRESS: {VisitStatus.COMPLETED, VisitStatus.FLAGGED, VisitStatus.MISSED},
    VisitStatus.FLAGGED:     {VisitStatus.IN_PROGRESS, VisitStatus.COMPLETED, VisitStatus.MISSED},
    VisitStatus.COMPLETED:   set(),
    VisitStatus.MISSED:      set(),
}


def assert_valid_transition(current: VisitStatus, target: VisitStatus) -> None:
    """Raise InvalidStateTransitionException if *target* is not reachable from *current*."""
    if target not in _VALID_TRANSITIONS.get(current, set()):
        raise InvalidStateTransitionException(
            f"Cannot transition visit from '{current.value}' to '{target.value}'"
        )


def is_terminal(status: VisitStatus) -> bool:
    return status in (VisitStatus.COMPLETED, VisitStatus.MISSED)
