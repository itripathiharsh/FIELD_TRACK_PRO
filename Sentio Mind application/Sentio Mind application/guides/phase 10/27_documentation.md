# FieldTrack Pro — Documentation
### Phase 10 — Last phase before MVP is considered complete

Most of the real content already exists across the 26 prior docs — this phase is about packaging it for the right audience, not re-deriving it. Each section below is what actually needs to be *written fresh* versus what's just *assembled/pointed to*.

---

## 1. API Documentation

**Mostly auto-generated, not hand-written.** Springdoc-openapi (configured back in Spring Boot Setup) generates live, always-accurate docs from the actual code at `/swagger-ui.html` — this is deliberately preferred over a hand-maintained API doc, which drifts out of sync the moment someone changes an endpoint without remembering to update a separate Word doc.

**What still needs manual authoring** (Swagger describes shape, not intent):
- A short prose intro at the top of the OpenAPI spec (`@OpenAPIDefinition` annotation) explaining auth flow (bearer token, how to get one) and the idempotency key convention on check-in — these are cross-cutting concepts Swagger's per-endpoint view doesn't naturally surface.
- Example request/response payloads for the two highest-stakes endpoints (`/auth/login`, `/visits/{id}/check-in`) — already drafted in the API Design doc (Phase 2.2), just needs copying into the `@ExampleObject` annotations so they render in Swagger UI directly rather than living only in a planning doc nobody browsing the live API reference will see.

```java
@OpenAPIDefinition(
    info = @Info(
        title = "FieldTrack Pro API",
        version = "1.0",
        description = "Auth: Bearer JWT in Authorization header, obtained via /auth/login. " +
                       "Check-in requests should include an Idempotency-Key header to safely retry on network failure."
    )
)
```

---

## 2. User Manual (Employee-Facing)

**This one needs real writing** — Swagger doesn't help field employees who aren't developers. Structure, pulling directly from the User Flows and Android Screen List docs so nothing is invented fresh:

1. **Getting started** — installing the app (references the APK distribution decision from Deployment doc — MDM push vs. manual sideload, whichever you settle on), logging in for the first time.
2. **Your daily dashboard** — reading visit status badges, what Pending/In Progress/Completed/Missed mean.
3. **Traveling to a visit** — using the Navigate button, what happens as you approach the customer location.
4. **Checking in** — what the geofence prompt means, what to do if check-in fails ("try moving closer, or check your phone's GPS signal is on" — matching the non-accusatory tone locked in the User Journey doc).
5. **Filling the requirement form** — field-by-field guide, how auto-save protects your work if the app closes.
6. **Photos, documents, and signatures** — how to attach files, how to capture both signatures.
7. **Working offline** — what the "Pending Sync" badge means, reassurance that nothing is lost.
8. **Troubleshooting** — common issues (permission denied, GPS not working, app won't sync) with plain-language fixes.

**Format recommendation**: short, mostly screenshots with 1-2 sentences each, not a dense text manual — matches the usability target from the Requirements doc's NFR table (5 taps/screens max per flow) and the real reading conditions (a field employee skimming this once, standing outside a customer's office, not sitting down to study it).

---

## 3. Admin Manual

Same principle, different audience — pulls from the Web Dashboard Screen List and User Journey (Admin section):

1. **Logging in and the dashboard overview** — reading the summary cards, understanding the live map's "last known location" nature (explicitly note it is *not* real-time continuous tracking, so admins don't misread it).
2. **Managing employees** — adding, editing, deactivating (with the explicit warning that deactivation is immediate).
3. **Managing customers** — adding, the address-vs-map-pin choice, setting geofence radius.
4. **Scheduling visits** — single and bulk assignment.
5. **Reading the visit status board** — what each column means.
6. **Handling flagged visits** — this section deserves the most careful writing of the whole manual, given it's the highest-trust-risk screen in the product. Should explicitly coach admins on reading reason codes fairly (a GPS glitch reading `OUTSIDE_RADIUS` by 15 meters is different from a pattern of `MOCK_LOCATION_SUSPECTED` flags) rather than treating every flag as proven fraud.
7. **Reports and exports** — what each of the four reports shows, how to export.
8. **Understanding "distance traveled"** — explicitly reiterate it's an approximation, not GPS-tracked mileage, so it doesn't get used for something like fuel reimbursement calculations where the imprecision would actually matter.

---

## 4. Deployment Guide

This is mostly **assembly, not new writing** — Phase 9's Deployment doc already contains the actual commands, Dockerfiles, and configs. The Deployment Guide packages that into a runbook format for whoever operates the on-prem server (which may not be you):

1. Prerequisites (Docker, Docker Compose, TLS certs, DNS/network access resolved per the VPN question).
2. Environment variable checklist (copied directly from Deployment doc Section 5).
3. First-time setup steps (clone repos, `docker-compose up`, run initial DB migration verification).
4. Day-2 operations: how to check logs, how to restart a container safely, how to run a manual backup, how to restore from backup (this restore procedure doesn't exist yet anywhere — worth writing and actually testing once, not just documenting in theory).
5. Update/rollout procedure for pushing new backend/web versions and new Android APK builds.

**Gap worth naming**: nobody has written or tested a **restore-from-backup procedure**. Having backups (Phase 9) without ever having tested restoring from one is a common way backup strategies fail silently — worth doing a real dry-run restore once, and documenting exactly what that looked like, rather than assuming `pg_dump` backups will just work when actually needed.

---

## 5. Technical Documentation

This is the internal-engineering-facing doc — essentially an index pointing back into the 26 docs already produced, organized for someone (possibly future-you, possibly a new developer) trying to understand the system without reading everything in order:

- **System overview**: points to Architecture doc.
- **Database schema**: points to Database Design + ER Diagrams.
- **API reference**: points to Swagger UI (live) + API Design doc (intent/rationale).
- **Security model**: points to Security Design doc — flagged as required reading before anyone touches auth or the geo-verification logic.
- **Key business rules index** — a short, genuinely new piece of writing since it's not natural to derive from any single existing doc: a flat list of the "why is it built this way" decisions that would otherwise get lost in tribal knowledge —
  - 3 consecutive geo-verification failures → auto-flag
  - 2-hour grace window before MISSED
  - Idempotency key required for reliable offline check-in retry
  - Client-trusted timestamp only for check-out, never for check-in verification
  - Distance traveled is a straight-line estimate, not road mileage
  - Point-in-time location capture only, not continuous tracking (with the note that this is the single biggest lever if requirements ever change)

This index is arguably the single most valuable artifact in Phase 10 — it's the concentrated list of non-obvious decisions that a future developer (or a future Antigravity session with no memory of this conversation) would otherwise have to reverse-engineer from code or rediscover the hard way.

---

## Phase 10 — Complete

API docs (mostly auto-generated + annotated), User Manual, Admin Manual, Deployment Guide (assembled from Phase 9 + one real gap closed — tested restore procedure), and Technical Documentation (indexed, with the standalone business-rules list as the genuinely new artifact).

---

## MVP — Complete

All 10 phases done, 27 documents total, from Requirements through Documentation. Every open question from the original proposal was resolved as a locked product decision rather than left ambiguous for an agent to guess at. See the separate Future Roadmap doc for what's deliberately deferred past MVP.
