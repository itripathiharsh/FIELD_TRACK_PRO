"""
Server-side evaluation of one check-in fix: PostGIS distance + pin accuracy + the shared decision function.
Used by the check-in endpoint and by the admin-verification request, so both apply identical rules.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.customer import Customer
from app.models.outlet_proof import OutletProof, OutletProofStatus
from app.services import geo_decision
from app.services.customer_service import measure_distance_to_customer

MAX_FIX_AGE_S = 24 * 3600.0  # offline-queued check-ins may be this old (and are flagged for review)


@dataclass
class CheckinEvaluation:
    distance_m: float
    accuracy_m: float
    pin_accuracy_m: float | None
    age_s: float
    is_offline: bool
    decision: geo_decision.Decision | None   # None when a rule before the decision function rejected the fix
    label: str                               # stored in geo_verification_logs.decision
    accepted: bool                           # may be checked in (INSIDE, or UNCERTAIN with the point estimate inside)
    confidence: str | None                   # HIGH | LOW | OFFLINE when accepted
    needs_verification: bool                 # UNCERTAIN with the point estimate outside the radius
    error_code: str | None
    reason: str | None


async def get_pin_accuracy(session: AsyncSession, customer_id: uuid.UUID) -> float | None:
    """Accuracy of the GPS fix the outlet's current pin was registered with (primary approved proof)."""
    value = (
        await session.execute(
            select(OutletProof.accuracy_m).where(
                OutletProof.customer_id == customer_id,
                OutletProof.is_primary.is_(True),
                OutletProof.status == OutletProofStatus.APPROVED.value,
            ).limit(1)
        )
    ).scalar_one_or_none()
    return float(value) if value is not None else None


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


async def evaluate_checkin_fix(
    session: AsyncSession,
    customer: Customer,
    *,
    latitude: float,
    longitude: float,
    accuracy_m: float,
    is_mock: bool,
    captured_at: datetime,
    allow_offline: bool = True,
    now: datetime | None = None,
) -> CheckinEvaluation:
    received = now or datetime.now(timezone.utc)
    age_s = (received - _aware(captured_at)).total_seconds()
    is_offline = allow_offline and geo_decision.LIVE_MAX_AGE_S < age_s <= MAX_FIX_AGE_S
    distance = await measure_distance_to_customer(customer, latitude, longitude, session)
    pin_acc = await get_pin_accuracy(session, customer.id)
    radius = float(customer.geofence_radius_m)

    def rejected(label: str, code: str, reason: str, decision: geo_decision.Decision | None = None) -> CheckinEvaluation:
        return CheckinEvaluation(distance, accuracy_m, pin_acc, age_s, is_offline, decision, label, False, None, False, code, reason)

    if is_mock:
        return rejected("MOCK", "GEO_VERIFICATION_FAILED", "Mock location provider detected on device")
    if age_s > MAX_FIX_AGE_S:
        return rejected("POOR_FIX", "GEO_VERIFICATION_FAILED",
                        f"GPS fix is too old ({age_s / 3600:.1f}h) - maximum age is 24h")

    decision = geo_decision.decide(
        distance, accuracy_m, pin_acc, radius, age_s=age_s,
        max_age_s=None if is_offline else geo_decision.LIVE_MAX_AGE_S,
    )
    label = decision.outcome.value
    if decision.outcome is geo_decision.Outcome.POOR_FIX:
        reasons = {
            "ACCURACY_UNKNOWN": "GPS accuracy is unknown - capture a fresh location fix",
            "ACCURACY_TOO_LOW": f"GPS accuracy ({accuracy_m:.1f}m) exceeds maximum threshold ({geo_decision.MAX_ACCURACY_M:.1f}m)",
            "STALE": f"GPS fix is too old ({age_s:.0f}s) - a live check-in needs a fix from the last {geo_decision.LIVE_MAX_AGE_S:.0f}s"
            if age_s >= 0 else "GPS capture timestamp is in the future",
            "INVALID_COORDINATES": "Invalid device coordinates",
        }
        return rejected(label, "GEO_VERIFICATION_FAILED", reasons.get(decision.reason or "", "GPS fix is not usable"), decision)
    if decision.outcome is geo_decision.Outcome.OUTSIDE:
        return rejected(label, "GEO_VERIFICATION_FAILED",
                        f"Distance ({distance:.1f}m) exceeds allowed radius ({radius:.1f}m)", decision)
    if decision.outcome is geo_decision.Outcome.UNCERTAIN and not decision.point_inside:
        ev = rejected(label, "GEO_UNCERTAIN",
                      f"Location is uncertain: about {distance:.0f}m from the outlet with GPS accuracy of +-{accuracy_m:.0f}m. "
                      "Wait for a better GPS fix or request admin verification", decision)
        ev.needs_verification = True
        return ev

    confidence = "OFFLINE" if is_offline else ("HIGH" if decision.outcome is geo_decision.Outcome.INSIDE else "LOW")
    return CheckinEvaluation(distance, accuracy_m, pin_acc, age_s, is_offline, decision, label, True, confidence, False, None, None)
