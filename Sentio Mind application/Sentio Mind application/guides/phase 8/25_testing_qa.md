# FieldTrack Pro — Testing & QA (Final Integration Pass)
### Phase 8 — Regression across everything, not first-time discovery of bugs
### Revision 2 — Sections 1 & 2 (backend tests) rewritten for pytest; Sections 3–5 unchanged (mobile/integration/performance scenarios are language-independent)

Every phase from 3–7 already had its own smoke test or "test against real backend" discipline built in. This phase is the cross-cutting regression sweep — catching issues that only appear when Android, Web, and Backend interact together, not re-testing each piece in isolation from scratch.

---

## 1. Unit Testing (Backend)

Focus areas — not blanket 100% coverage, but the logic where a bug would be genuinely costly. **Same priority list as the original**, expressed in pytest:

```python
# tests/unit/test_visit_service.py
import pytest

@pytest.mark.asyncio
async def test_check_in_within_radius_marks_visit_in_progress(visit_service, sample_visit_inside_radius):
    # Given a visit and a customer with known location/radius
    # When check-in called with coordinates inside radius
    result = await visit_service.check_in(sample_visit_inside_radius.id, valid_check_in_request, None)
    # Then visit status = IN_PROGRESS, geo log written with result=SUCCESS
    assert result.is_valid is True


@pytest.mark.asyncio
async def test_check_in_outside_radius_does_not_change_visit_status(visit_service, sample_visit):
    # Then visit stays PENDING, geo log written with result=FAILED, reason=OUTSIDE_RADIUS
    result = await visit_service.check_in(sample_visit.id, far_away_check_in_request, None)
    assert result.is_valid is False
    assert result.reason == "OUTSIDE_RADIUS"


@pytest.mark.asyncio
async def test_check_in_third_consecutive_failure_flags_visit_and_notifies_admins(visit_service, sample_visit):
    # Verifies the "3 failures = FLAGGED" business rule from Phase 3 Business Logic
    for _ in range(3):
        await visit_service.check_in(sample_visit.id, far_away_check_in_request, None)
    refreshed = await visit_service.get_by_id(sample_visit.id)
    assert refreshed.status == VisitStatus.FLAGGED


@pytest.mark.asyncio
async def test_check_in_same_idempotency_key_twice_returns_existing_result_without_duplicate_log(visit_service, sample_visit):
    # The idempotency mechanism specifically — this is the test most likely to be skipped
    # and most likely to hide a real bug if it is
    key = "test-key-123"
    first = await visit_service.check_in(sample_visit.id, valid_check_in_request, key)
    second = await visit_service.check_in(sample_visit.id, valid_check_in_request, key)
    assert first == second
    log_count = await count_geo_logs_for_key(sample_visit.id, key)
    assert log_count == 1


@pytest.mark.asyncio
async def test_deactivate_employee_revokes_all_refresh_tokens(employee_service, sample_employee):
    # Confirms deactivation actually blocks access, not just flips a DB flag
    await employee_service.deactivate(sample_employee.id)
    active_tokens = await count_active_refresh_tokens(sample_employee.user_id)
    assert active_tokens == 0


def test_visit_state_machine_rejects_invalid_transitions():
    # e.g. COMPLETED -> IN_PROGRESS should raise InvalidStateTransitionException
    with pytest.raises(InvalidStateTransitionException):
        assert_valid_transition(VisitStatus.COMPLETED, VisitStatus.IN_PROGRESS)
```

**Priority order if time is limited, unchanged from the original**: geo-verification logic > state machine > idempotency > auth/deactivation > everything else. The first three are where a silent bug directly undermines the product's core promise.

`pytest-asyncio` is required (declared in `pyproject.toml`'s dev dependencies, see Python Backend Setup doc) since every service method in this codebase is `async def` — the direct equivalent of JUnit's synchronous test style needing no special handling in the original Java build.

---

## 2. API Testing

Extends the Phase 3 smoke test (29 checks) into a proper automated suite — same scenarios, now scripted with `httpx` + `testcontainers-python` instead of MockMvc + Java Testcontainers:

```python
# tests/integration/test_visit_api.py
import pytest
from httpx import AsyncClient, ASGITransport
from testcontainers.postgres import PostgresContainer
from app.main import app

@pytest.fixture(scope="module")
def postgres_container():
    with PostgresContainer("postgis/postgis:15-3.4") as postgres:
        yield postgres


@pytest.mark.asyncio
async def test_check_in_as_wrong_employee_returns_403(postgres_container, other_employee_token, visit_id):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            f"/api/v1/visits/{visit_id}/check-in",
            headers={"Authorization": f"Bearer {other_employee_token}"},
            json=valid_check_in_payload,
        )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_check_in_outside_radius_returns_422_with_reason_code(postgres_container, employee_token, visit_id):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            f"/api/v1/visits/{visit_id}/check-in",
            headers={"Authorization": f"Bearer {employee_token}"},
            json=far_away_coords_payload,
        )
    assert response.status_code == 422
    assert response.json()["verification"]["reason"] == "OUTSIDE_RADIUS"
```

`testcontainers-python`'s `PostgresContainer`, pointed at the real `postgis/postgis` image (not an in-memory/SQLite substitute) — critical here specifically because the geo-verification logic depends on real PostGIS functions that no in-memory database can fake convincingly. This is the same non-negotiable the original doc flagged about H2, carried over: any temptation to swap in SQLite for faster test runs is a shortcut that would give false confidence and must be avoided.

---

## 3. Mobile Testing

*(Unchanged — none of this depends on backend language; it's exercising the Android client against whatever backend is running.)*

| Area | What to Test | Why It's Not Redundant With Phase 6 |
|---|---|---|
| Device fragmentation | Run on at least 2-3 real Android versions/manufacturers (not just the dev's own phone/emulator) | Geofencing and background location behavior genuinely varies by OEM (Samsung/Xiaomi battery optimization is notorious for killing background location silently) |
| Permission denial flows | Deny location permission entirely, deny only "while using app" (not "always") | Phase 6 testing likely used a dev device with permissions already granted — this specifically tests the unhappy path |
| Low-connectivity / airplane mode mid-visit | Start a visit online, lose connection mid-form, regain connection | Confirms the full offline→sync loop survives an interruption mid-task, not just before/after |
| App kill during form fill | Force-stop the app mid-requirement-form | Confirms the local auto-save (H3) actually restores the draft, not just theoretically |
| Storage/battery under real field use | Multi-hour session with multiple visits | Confirms compression (Phase 5) and event-based location (Phase 4, not continuous) actually keep resource usage reasonable in practice |

---

## 4. Integration Testing (Android ↔ Backend ↔ Web Dashboard)

*(Unchanged — these scenarios test system behavior across the API boundary, not backend internals, so the migration has no effect on what's being verified.)*

| # | Scenario | Confirms |
|---|---|---|
| 1 | Admin schedules a visit on Web → appears on Android Dashboard without app restart | Data sync touchpoint from Navigation Flow doc actually works |
| 2 | Employee completes a visit offline on Android → syncs → appears correctly on Web's Visit Status Board | Full offline-to-admin-visibility loop |
| 3 | Employee fails geo-verification 3 times → visit flagged → appears in Web's Flagged Visit Review with correct reason codes | Cross-system consistency of the reason-code data shape |
| 4 | Admin deactivates an employee mid-session → employee's next API call from Android fails auth | Real-time effect of deactivation across systems, not just eventually |
| 5 | Employee uploads a photo → admin views it on Web via pre-signed URL | Confirms MinIO access pattern works end-to-end, not just from Postman |
| 6 | Two admins editing the same customer's geofence radius simultaneously | Basic concurrent-edit sanity check — last-write-wins is acceptable for MVP, but confirm it doesn't corrupt data |
| 7 | Employee's device clock is wrong → check-out timestamp uses client time | Confirms the "trust client timestamp for offline checkout" decision from Business Logic doc behaves as expected, not as a surprise |

---

## 5. Performance Testing

Lightweight for MVP scale — no need for elaborate load-testing infrastructure given the single on-prem server / no-Kubernetes decision from Tech Stack, but worth confirming baseline numbers. **Targets unchanged from the original**:

- **Geo-verification query latency**: `ST_DWithin` call should resolve well under the 3-second target from Requirements doc's NFR table, even with a few thousand customer rows. Async SQLAlchemy + asyncpg should comfortably clear this — worth confirming with a simple load script (`locust` or a hand-rolled `asyncio` batch of requests) rather than assuming.
- **Dashboard overview load time**: with realistic data volume (e.g., 50 employees, 500+ historical visits), confirm the summary queries don't degrade — add indexes if they do (the ones from Database Design should cover this, but verify).
- **Report export time**: a full month's Employee Visit Report CSV export for 50 employees should complete in a few seconds, not tie up a request for a long time — if it's slow, consider generating it in a background task (FastAPI's `BackgroundTasks`, or a dedicated APScheduler job) instead of a synchronous export endpoint (a Phase 9+ concern if this becomes a real bottleneck, not something to over-engineer now).
- **Android app cold start / geofence registration time**: shouldn't noticeably delay an employee opening the Visit Detail screen — unaffected by the backend rewrite.

**One new item worth a quick check specifically because of the migration**: confirm Uvicorn is running with an appropriate worker count for the on-prem server's CPU cores (e.g., `--workers 4` for a 4-core box) rather than the single-process default — this is the Python-world equivalent of the JVM's thread-pool tuning, and skipping it would under-utilize the hardware compared to the original Spring Boot deployment's default thread pool.

**Deliberately not doing**: concurrent-user load testing at a scale beyond what the pilot will actually see (tens of employees). Building elaborate load infrastructure for a single-on-prem-server MVP would be solving a problem that doesn't exist yet — consistent with the "no Kubernetes, no microservices" reasoning from Tech Stack.

---

## Phase 8 — Complete

Unit tests on the highest-risk logic (pytest), automated API tests with real PostGIS via testcontainers-python (not a fake substitute), mobile testing covering the unhappy paths Phase 6 didn't stress, full three-system integration scenarios, and lightweight performance sanity checks including the new worker-count consideration.

**Next up:** Phase 9 — Deployment.
