# FieldTrack Pro — Tech Stack
### Phase 1.4 — Product Discovery & Planning
### Revision 2 — Backend migrated from Java/Spring Boot to Python/FastAPI (supersedes Revision 1)

Locked choices, decided as product owner against the proposal's constraints (backend, Android app, on-prem hosting). Each choice is deliberately boring/mainstream — this is a business tool built by agents, not a place to experiment with bleeding-edge frameworks that'll fight you mid-build.

**Revision note**: the original proposal named "Spring Boot" as a suggestion, not a hard constraint — the actual constraints are REST/JSON API, PostgreSQL+PostGIS, on-prem hosting, and zero frontend changes. The team has since decided to build the backend in Python instead. Every choice below reflects that decision; nothing else in this document changed as a result.

---

## 1. Backend

| Layer | Choice | Why |
|---|---|---|
| Language/Framework | **Python 3.12 + FastAPI** | Async-first, automatic OpenAPI docs (matches the springdoc-openapi goal with zero extra work), strong agent familiarity — low risk of hallucinated APIs. |
| ASGI Server | **Uvicorn** (with `uvicorn[standard]` for production — includes `httptools`/`uvloop`) | Standard FastAPI production server. |
| Dependency Management | **Poetry** | Deterministic lockfile (`poetry.lock`), same role Maven played — one prescriptive way to declare and resolve dependencies so agents don't improvise `pip install` one package at a time. |
| Auth | **python-jose (JWT) + passlib (bcrypt) + FastAPI `Depends()`** | Matches FR-3/FR-4/A3/A5. Stateless auth suits mobile + web dashboard both hitting the same API. |
| API Style | **REST (JSON)** | Unchanged — matches Android + web dashboard needs. No GraphQL. |
| ORM | **SQLAlchemy 2.0 (async) + GeoAlchemy2** | Async ORM pairs naturally with FastAPI's async request handling; GeoAlchemy2 gives first-class `Geography(Point, 4326)` column support and PostGIS function wrappers (`ST_DWithin`, `ST_Distance`) without hand-written raw SQL. |
| DB Driver | **asyncpg** | Fastest async PostgreSQL driver for Python, standard SQLAlchemy 2.0 async pairing. |
| Validation | **Pydantic v2** | Server-side validation on every request/response schema — required given E5 (server-side GPS verification is non-negotiable). Built into FastAPI, no extra wiring. |
| API Docs | **FastAPI's built-in OpenAPI generation** (`/docs`, `/redoc`) | Auto-generates from the same Pydantic schemas used for validation — feeds directly into Phase 10 Documentation with zero extra work, same benefit the original springdoc-openapi choice was after. |
| Config | **pydantic-settings** | 12-factor config from environment variables / `.env` files — same "no silent prod fallback" discipline as before (see Section 7, and Deployment doc). |
| Background Jobs | **APScheduler** | Runs the missed-visit-detection cron job (Business Logic doc) in-process — no separate job runner needed at this scale. |

---

## 2. Database

| Layer | Choice | Why |
|---|---|---|
| Primary DB | **PostgreSQL 15+** | Unchanged — specified in proposal, handles geo-queries well via PostGIS. |
| Geo Support | **PostGIS extension** | Unchanged — native support for geo-fence radius checks (`ST_DWithin`), accessed through GeoAlchemy2 instead of Hibernate Spatial. |
| Migrations | **Alembic** | Python's standard migration tool, same role Flyway played — version-controlled, sequential, one-way-forward schema migrations so multiple agent sessions never produce conflicting schema states. |
| Connection Pooling | **SQLAlchemy's built-in async connection pool** | No reason to override the default at this scale — same rationale as the original HikariCP default choice. |

---

## 3. File & Media Storage

| Layer | Choice | Why |
|---|---|---|
| Object Storage | **MinIO** (self-hosted, S3-compatible) | Unchanged — matches the "on-prem" constraint, accessed via the official `minio` Python SDK. |
| Image Handling | **Pillow** (server-side compression on upload) | Python-native equivalent of Thumbnailator — resize + JPEG quality reduction before storing, same reasoning: mobile uploads on poor field networks need this. |
| File-type Validation | **python-magic** | Magic-byte detection (reads actual file content, not client-declared `Content-Type`) — Python equivalent of Apache Tika, same non-negotiable rule from Security Design Section 5. |

---

## 4. Android App

*(Unchanged — the Android app talks to a REST/JSON API and has no dependency on backend language.)*

| Layer | Choice | Why |
|---|---|---|
| Language | **Kotlin** | Industry standard for Android. |
| UI Toolkit | **Jetpack Compose** | Modern, less boilerplate, better agent-generation success rate than the legacy View system. |
| Architecture | **MVVM (ViewModel + Repository pattern)** | Keeps GPS/geofencing/sync logic testable and separate from UI. |
| Local DB | **Room (SQLite)** | Offline visit queueing (I6). |
| Networking | **Retrofit + OkHttp** | Standard REST client pairing — API contract is identical regardless of backend language, so this needed zero changes when the backend moved to Python. |
| Background Sync | **WorkManager** | Reliable background sync jobs (I7), survives app kill/reboot. |
| Location | **Google Play Services — Fused Location Provider + Geofencing API** | Purpose-built for E3/E4. |
| Maps | **Google Maps SDK for Android** | Matches F1/F2. |
| Push Notifications | **Firebase Cloud Messaging (FCM)** | Backend now triggers pushes via the Python `firebase-admin` SDK instead of the Java one — same FCM service, same client-side integration, no Android change. |
| Signature Capture | **Custom Compose Canvas component** | Unchanged. |

---

## 5. Admin Web Dashboard

*(Unchanged — same reasoning as Android: the React app consumes a REST/JSON contract, not a language.)*

| Layer | Choice | Why |
|---|---|---|
| Framework | **React (Vite) + TypeScript** | Fast dev/build cycle, catches API-contract mismatches early. |
| UI Library | **shadcn/ui + Tailwind CSS** | Professional-looking defaults out of the box. |
| State/Data Fetching | **TanStack Query (React Query)** | Server-state caching/refetching for the live status board (D5). |
| Maps | **Google Maps JavaScript API** (`@react-google-maps/api`) | Matches F3/F4. |
| Charts | **Recharts** | Productivity Dashboard (K3). |
| Auth | **JWT stored in memory + httpOnly refresh cookie** | The Python backend sets the same `Set-Cookie` header shape the Java backend did — no frontend change required. |

---

## 6. Infrastructure & DevOps

| Layer | Choice | Why |
|---|---|---|
| Hosting | **On-prem server** (per proposal) | Unchanged. |
| Containerization | **Docker + Docker Compose** | Unchanged — the backend container now builds from a Python base image instead of a JDK one (see Deployment doc). |
| CI/CD | **GitHub Actions** (build/test on push; manual deploy trigger for on-prem) | Unchanged tool; pipeline steps swap `mvn test` for `poetry run pytest`. |
| Version Control | **Git + GitHub** | Standard, unchanged. |
| Environment Config | **`.env` files (pydantic-settings) for backend + `.env` for frontend/Android build variants** | Same "keep secrets out of source" principle as before — `application-*.yml` profiles are replaced by `.env.dev` / `.env.prod` loaded through pydantic-settings. |

---

## 7. Explicitly NOT Used (and why)

- **No microservices** — still correct at this scale; a single FastAPI application is the direct Python-world equivalent of the original "single Spring Boot monolith" decision, for the same reasons (shared DB, shared deployment lifecycle, no distributed-systems problem to solve).
- **No Kubernetes** — Docker Compose remains sufficient for on-prem single-server deployment.
- **No NoSQL database** — all data is relational with real reporting query needs; unchanged.
- **No cross-platform mobile (Flutter/React Native)** — unaffected by the backend language change; native Kotlin remains the Android choice.
- **No Django / Django REST Framework** — considered and rejected in favor of FastAPI: Django's synchronous-by-default ORM and heavier "batteries-included" structure (admin site, template engine) add weight this project doesn't need, while FastAPI's async-first design and automatic OpenAPI generation directly replace what springdoc-openapi and Spring's request pipeline were providing, with less ceremony.
- **No synchronous SQLAlchemy (`psycopg2`)** — async SQLAlchemy with `asyncpg` was chosen over sync, since FastAPI's core value (handling many concurrent field-app requests without blocking) depends on the ORM layer also being async; mixing sync DB calls into async request handlers would silently block the event loop under load.

---

**Next up:** Architecture (Phase 1.5) — putting all of this together into a system architecture diagram/description, updated for the Python backend.
