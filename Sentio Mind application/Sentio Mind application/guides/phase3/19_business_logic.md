# FieldTrack Pro — Business Logic
### Phase 3.5 — Backend Development
### Revision 2 — rewritten for Python/FastAPI

The logic that ties Core APIs and Database Implementation together into actual product behavior — visit state machine, idempotent check-in, and notification triggers. **Every rule and threshold below is identical to the original** — only the implementation language changed.

---

## 1. Visit State Machine

```
PENDING --[check-in success]--> IN_PROGRESS --[check-out]--> COMPLETED
PENDING --[scheduled time passes, no check-in]--> MISSED
IN_PROGRESS --[repeated geo-verification failures]--> FLAGGED
```

Enforced centrally so no route or service can push an invalid transition:

```python
# app/services/visit_state_machine.py
from app.models.visit import VisitStatus
from app.exceptions.custom import InvalidStateTransitionException

TRANSITIONS: dict[VisitStatus, set[VisitStatus]] = {
    VisitStatus.PENDING: {VisitStatus.IN_PROGRESS, VisitStatus.MISSED},
    VisitStatus.IN_PROGRESS: {VisitStatus.COMPLETED, VisitStatus.FLAGGED},
    VisitStatus.FLAGGED: {VisitStatus.IN_PROGRESS, VisitStatus.COMPLETED},   # admin can un-flag
    VisitStatus.COMPLETED: set(),
    VisitStatus.MISSED: set(),
}


def assert_valid_transition(from_status: VisitStatus, to_status: VisitStatus) -> None:
    if to_status not in TRANSITIONS.get(from_status, set()):
        raise InvalidStateTransitionException(f"Cannot transition visit from {from_status} to {to_status}")
```

---

## 2. Check-In — Idempotent, Server-Verified

Decision, unchanged from the original: **client-supplied idempotency key**, since the Android app already knows when it's retrying a queued offline request — it's the natural owner of "is this a retry."

```python
# app/services/visit_service.py
class VisitService:
    def __init__(self, db, geo_verification_service: GeoVerificationService, notification_service: NotificationService):
        self.db = db
        self.geo_verification_service = geo_verification_service
        self.notification_service = notification_service

    async def check_in(self, visit_id, request: CheckInRequest, idempotency_key: str | None) -> CheckInResponse:
        # Idempotency check first — if this exact request already succeeded, return the prior result
        if idempotency_key:
            existing = await self.db.scalar(
                select(GeoVerificationLog).where(
                    GeoVerificationLog.visit_id == visit_id,
                    GeoVerificationLog.idempotency_key == idempotency_key,
                )
            )
            if existing:
                return CheckInResponse.from_existing_log(existing)

        visit = await self.db.get(Visit, visit_id)
        if visit is None:
            raise ResourceNotFoundException("Visit not found")
        assert_valid_transition(visit.status, VisitStatus.IN_PROGRESS)

        # Mock-location check — per Security Design Section 7
        if request.is_mock_location:
            log = GeoVerificationLog(
                visit_id=visit_id, result="FAILED", reason="MOCK_LOCATION_SUSPECTED",
                idempotency_key=idempotency_key,
            )
            self.db.add(log)
            await self.db.commit()
            return CheckInResponse.failed("MOCK_LOCATION_SUSPECTED")

        outcome = await self.geo_verification_service.verify(
            visit_id, visit.customer_id, request.latitude, request.longitude
        )

        if not outcome.is_valid:
            await self._check_repeated_failures(visit)   # may trigger FLAGGED status + admin alert (FR-28)
            return CheckInResponse.failed(outcome.reason)

        visit.status = VisitStatus.IN_PROGRESS
        visit.check_in_at = datetime.now(timezone.utc)
        visit.check_in_location = from_shape(Point(request.longitude, request.latitude), srid=4326)
        await self.db.commit()

        return CheckInResponse.success(outcome.distance_meters)

    async def _check_repeated_failures(self, visit: Visit) -> None:
        failure_count = await count_failed_attempts(self.db, visit.id)
        if failure_count >= 3:
            visit.status = VisitStatus.FLAGGED
            await self.db.commit()
            await self.notification_service.notify_admins_of_flagged_visit(visit)   # FR-28
```

**Idempotency key column**: `geo_verification_logs.idempotency_key` — already included directly in the Database Design/schema doc for this Python build (unlike the original Java build, where it was identified as a gap and patched in via a follow-up migration). Building it into the initial schema from the start is one of the few genuine improvements that came out of doing this rewrite carefully rather than a mechanical translation.

---

## 3. Offline Sync — Server-Side Handling

The Android side queues and replays (per Architecture doc Section 3, step 7 — unchanged). Server-side, the only special handling needed is trusting the client-supplied timestamp for check-out ordering rather than server-receipt time, since a sync could arrive hours after the actual event:

```python
async def check_out(self, visit_id, request: CheckOutRequest) -> VisitResponse:
    visit = await self.db.get(Visit, visit_id)
    if visit is None:
        raise ResourceNotFoundException("Visit not found")
    assert_valid_transition(visit.status, VisitStatus.COMPLETED)

    visit.check_out_at = request.client_timestamp or datetime.now(timezone.utc)   # trust device time for offline-completed visits
    visit.check_out_location = from_shape(Point(request.longitude, request.latitude), srid=4326)
    visit.status = VisitStatus.COMPLETED
    visit.synced = True
    await self.db.commit()

    await self.notification_service.notify_visit_completed(visit)   # FR-27
    return VisitResponse.from_orm(visit)
```

**Flag, unchanged from the original**: trusting client timestamps is a small integrity tradeoff — a device with a wrong clock could log a slightly inaccurate `checkOutAt`. Acceptable for MVP since it's not the security-critical field (location is), but worth knowing it's a deliberate looseness, not an oversight.

---

## 4. Scheduled Job — Missed Visit Detection

Spring's `@Scheduled(cron = ...)` annotation is replaced by APScheduler, registered at app startup (see Python Backend Setup doc, Section 5):

```python
# app/jobs/missed_visit_scheduler.py
from datetime import datetime, timedelta, timezone
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from app.database import AsyncSessionLocal
from app.models.visit import Visit, VisitStatus
from app.services.notification_service import NotificationService

scheduler = AsyncIOScheduler()


async def mark_overdue_visits_as_missed():
    cutoff = datetime.now(timezone.utc) - timedelta(hours=2)   # grace window, admin-configurable later
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Visit).where(Visit.status == VisitStatus.PENDING, Visit.scheduled_at < cutoff)
        )
        overdue = result.scalars().all()

        notification_service = NotificationService(db)
        for visit in overdue:
            visit.status = VisitStatus.MISSED
            await notification_service.notify_visit_overdue(visit)   # FR-27

        await db.commit()


def start_scheduler():
    scheduler.add_job(mark_overdue_visits_as_missed, "cron", minute="*/15")   # every 15 minutes, same cadence as original
    scheduler.start()
```

**Decision, unchanged, restated as product owner**: 2-hour grace window past scheduled time before marking MISSED, not marking immediately at the scheduled minute. Field visits realistically run late; an immediate MISSED flag would generate constant false alarms and erode trust in the flagging system generally (same principle as the User Journey doc's "design for trust and explainability" throughline).

---

## 5. Notification Triggers — Centralized

```python
# app/services/notification_service.py
class NotificationService:
    def __init__(self, db, fcm_service: FcmService | None = None):
        self.db = db
        self.fcm_service = fcm_service or FcmService()

    async def notify_new_visit_assigned(self, visit: Visit) -> None:
        await self._send(
            visit.employee.user_id, "NEW_VISIT",
            "New visit assigned", f"You have a new visit: {visit.customer.name}", visit.id,
        )

    async def notify_visit_overdue(self, visit: Visit) -> None:
        await self._send(
            visit.employee.user_id, "OVERDUE",
            "Visit overdue", f"Your visit to {visit.customer.name} is overdue", visit.id,
        )

    async def notify_admins_of_flagged_visit(self, visit: Visit) -> None:
        result = await self.db.execute(select(User).where(User.role == Role.ADMIN))
        for admin in result.scalars().all():
            await self._send(
                admin.id, "GEO_ALERT", "Visit flagged",
                f"Repeated check-in failures for {visit.employee.full_name}", visit.id,
            )

    async def _send(self, user_id, type_: str, title: str, body: str, visit_id) -> None:
        notification = Notification(
            user_id=user_id, type=type_, title=title, body=body, related_visit_id=visit_id,
        )
        self.db.add(notification)
        await self.db.commit()
        await self.fcm_service.push(user_id, title, body)   # fire-and-forget; DB record is source of truth
```

`FcmService` wraps the `firebase-admin` Python SDK (`firebase_admin.messaging.send()`), initialized once at app startup from the service-account JSON referenced in `settings.firebase_credentials_path` — same push mechanism, same "DB record is the source of truth, push is best-effort" philosophy as the original.

---

**Next up:** Smoke test of these APIs (Postman/manual/pytest) before moving to Phase 4 (Maps & Location Services).
