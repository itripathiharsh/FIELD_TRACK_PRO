"""
Accuracy-aware geofence decision for check-in. Pure and deterministic.

The specification lives in fieldtrackpro-android/design-review/gps-checkin-decision-spec.md. Android has an equivalent
implementation (utils/GeoDecision.kt); both are tested against the same vector file
(fieldtrackpro-android/app/src/test/resources/gps_decision_vectors.json).
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum

K = 0.5                  # weight of the uncertainty on the "inside" test
MAX_ACCURACY_M = 100.0   # above this (or unknown) there is no decision
LIVE_MAX_AGE_S = 120.0   # a live fix may be at most this old when it reaches the server
FUTURE_TOLERANCE_S = 300.0
EPS = 1e-9


class Outcome(str, Enum):
    INSIDE = "INSIDE"
    OUTSIDE = "OUTSIDE"
    UNCERTAIN = "UNCERTAIN"
    POOR_FIX = "POOR_FIX"


@dataclass(frozen=True)
class Decision:
    outcome: Outcome
    reason: str | None          # only for POOR_FIX
    uncertainty_m: float | None
    point_inside: bool          # point estimate d <= R


def _known(value: float | None) -> bool:
    return value is not None and not math.isnan(value) and value > 0.0


def combined_uncertainty(accuracy_m: float, pin_accuracy_m: float | None) -> float:
    if _known(pin_accuracy_m):
        return math.sqrt(accuracy_m * accuracy_m + pin_accuracy_m * pin_accuracy_m)
    return accuracy_m


def decide(
    distance_m: float,
    accuracy_m: float | None,
    pin_accuracy_m: float | None,
    radius_m: float,
    *,
    age_s: float | None = None,
    coords_valid: bool = True,
    max_age_s: float | None = LIVE_MAX_AGE_S,
) -> Decision:
    """``max_age_s=None`` disables the freshness test (offline-queued check-ins, which are flagged instead)."""
    point_inside = distance_m <= radius_m
    if not coords_valid:
        return Decision(Outcome.POOR_FIX, "INVALID_COORDINATES", None, point_inside)
    if not _known(accuracy_m):
        return Decision(Outcome.POOR_FIX, "ACCURACY_UNKNOWN", None, point_inside)
    assert accuracy_m is not None
    if accuracy_m > MAX_ACCURACY_M:
        return Decision(Outcome.POOR_FIX, "ACCURACY_TOO_LOW", None, point_inside)
    if max_age_s is not None and age_s is not None and (age_s > max_age_s or age_s < -FUTURE_TOLERANCE_S):
        return Decision(Outcome.POOR_FIX, "STALE", None, point_inside)

    u = combined_uncertainty(accuracy_m, pin_accuracy_m)
    if distance_m + K * u <= radius_m + EPS:
        return Decision(Outcome.INSIDE, None, u, point_inside)
    if distance_m - u > radius_m + EPS:
        return Decision(Outcome.OUTSIDE, None, u, point_inside)
    return Decision(Outcome.UNCERTAIN, None, u, point_inside)
