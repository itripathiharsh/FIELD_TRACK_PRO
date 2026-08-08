# FieldTrack Pro — Folder Structure
### Phase 2.3 — System Design
### Revision 2 — Backend section rewritten for Python/FastAPI (Android and Web sections unchanged)

Three separate repos (or a monorepo with three top-level dirs — either works; assuming separate repos below since backend/Android/web have completely different build tooling and release cycles). Structure is deliberately conventional per stack so agents follow well-trodden patterns instead of inventing structure mid-build.

---

## 1. Backend — `fieldtrackpro-backend` (Python / FastAPI / Poetry)

```
fieldtrackpro-backend/
├── app/
│   ├── main.py                         ← FastAPI app instance, router registration, startup/shutdown hooks
│   ├── config.py                        ← pydantic-settings: env-driven config (DB URL, JWT secret, MinIO, CORS)
│   ├── database.py                       ← Async SQLAlchemy engine + session factory + get_db() dependency
│   ├── api/
│   │   ├── deps.py                        ← Shared FastAPI dependencies (get_current_user, require_role, etc.)
│   │   └── v1/
│   │       ├── auth.py                      ← /auth/* routes
│   │       ├── employees.py                  ← /employees/* routes
│   │       ├── customers.py                   ← /customers/* routes
│   │       ├── visits.py                       ← /visits/* routes (check-in/check-out live here)
│   │       ├── requirement_forms.py              ← /requirement-categories, /visits/{id}/requirement-form
│   │       ├── media.py                           ← /visits/{id}/media, /visits/{id}/signatures
│   │       ├── reports.py                          ← /reports/* routes
│   │       ├── notifications.py                     ← /notifications/* routes
│   │       └── dashboard.py                          ← /dashboard/* routes
│   ├── services/
│   │   ├── auth_service.py
│   │   ├── employee_service.py
│   │   ├── customer_service.py
│   │   ├── visit_service.py
│   │   ├── geo_verification_service.py
│   │   ├── requirement_form_service.py
│   │   ├── media_storage_service.py
│   │   ├── report_service.py
│   │   └── notification_service.py
│   ├── models/                             ← SQLAlchemy ORM models (one file per entity, or grouped)
│   │   ├── user.py
│   │   ├── employee.py
│   │   ├── territory.py
│   │   ├── customer.py
│   │   ├── visit.py
│   │   ├── requirement_form.py
│   │   ├── visit_media.py
│   │   ├── visit_signature.py
│   │   ├── geo_verification_log.py
│   │   └── notification.py
│   ├── schemas/                             ← Pydantic request/response models
│   │   ├── auth.py
│   │   ├── employee.py
│   │   ├── customer.py
│   │   ├── visit.py
│   │   └── ...                                ← one per resource, mirrors models/
│   ├── security/
│   │   ├── jwt.py                              ← token creation/verification (python-jose)
│   │   ├── password.py                          ← hashing/verification (passlib)
│   │   ├── rate_limiter.py                       ← login attempt tracking
│   │   └── permissions.py                         ← role-check dependencies
│   ├── geo/
│   │   └── verification.py                         ← ST_DWithin / ST_Distance queries via GeoAlchemy2
│   ├── storage/
│   │   ├── minio_client.py                          ← MinIO client wrapper
│   │   ├── image_upload.py                           ← compression via Pillow + upload
│   │   ├── document_upload.py
│   │   └── file_validation.py                         ← python-magic magic-byte checks
│   ├── notification/
│   │   └── fcm_service.py                              ← firebase-admin push integration
│   ├── jobs/
│   │   └── missed_visit_scheduler.py                    ← APScheduler cron job
│   └── exceptions/
│       ├── handlers.py                                    ← global exception handlers registered on the app
│       └── custom.py                                       ← ResourceNotFoundException, GeoVerificationFailedException, etc.
├── alembic/
│   ├── env.py
│   └── versions/                                            ← one file per migration (auto-generated, human-reviewed)
├── tests/
│   ├── unit/                                                  ← service-layer unit tests (pytest)
│   └── integration/                                            ← API tests (pytest + httpx + testcontainers-python)
├── Dockerfile
├── docker-compose.yml
├── pyproject.toml                                                ← Poetry: dependencies + tool config (replaces pom.xml)
├── poetry.lock
├── alembic.ini
└── README.md
```

---

## 2. Android — `fieldtrackpro-android` (Kotlin / Jetpack Compose)

*(Unchanged — the Android app is a REST client and has no dependency on backend language.)*

```
fieldtrackpro-android/
├── app/
│   └── src/main/
│       ├── java/com/fieldtrackpro/android/
│       │   ├── FieldTrackApp.kt
│       │   ├── di/                        ← Hilt/Dagger modules
│       │   ├── data/
│       │   │   ├── local/
│       │   │   │   ├── db/                ← Room database, DAOs, entities
│       │   │   │   └── datastore/         ← encrypted token storage
│       │   │   ├── remote/
│       │   │   │   ├── api/               ← Retrofit service interfaces
│       │   │   │   └── dto/
│       │   │   └── repository/            ← Repository implementations (single source of truth)
│       │   ├── domain/
│       │   │   ├── model/                 ← domain models (not DTOs, not entities)
│       │   │   └── usecase/               ← e.g. CheckInUseCase, SyncVisitsUseCase
│       │   ├── ui/
│       │   │   ├── login/
│       │   │   ├── dashboard/
│       │   │   ├── visitdetail/
│       │   │   ├── requirementform/
│       │   │   ├── signature/
│       │   │   ├── components/            ← shared Compose components
│       │   │   └── theme/
│       │   ├── location/
│       │   │   ├── GeofenceManager.kt
│       │   │   └── LocationService.kt
│       │   ├── sync/
│       │   │   └── SyncWorker.kt          ← WorkManager background sync
│       │   └── notification/
│       │       └── FcmService.kt
│       ├── res/
│       └── AndroidManifest.xml
├── build.gradle.kts
└── README.md
```

---

## 3. Admin Web Dashboard — `fieldtrackpro-web` (React + Vite + TypeScript)

*(Unchanged — the dashboard is a REST client and has no dependency on backend language.)*

```
fieldtrackpro-web/
├── src/
│   ├── main.tsx
│   ├── App.tsx
│   ├── api/
│   │   ├── client.ts                  ← Axios/fetch instance, interceptors for JWT
│   │   ├── employees.ts
│   │   ├── customers.ts
│   │   ├── visits.ts
│   │   ├── reports.ts
│   │   └── notifications.ts
│   ├── pages/
│   │   ├── LoginPage.tsx
│   │   ├── DashboardOverviewPage.tsx
│   │   ├── EmployeesPage.tsx
│   │   ├── CustomersPage.tsx
│   │   ├── VisitsPage.tsx
│   │   ├── ReportsPage.tsx
│   │   └── SettingsPage.tsx
│   ├── components/
│   │   ├── layout/                    ← Sidebar, Header, shell
│   │   ├── map/                       ← LiveMap, MarkerCluster
│   │   ├── visits/                    ← VisitStatusBoard, VisitCard
│   │   ├── reports/                   ← ReportTable, ExportButton, charts
│   │   └── ui/                        ← shadcn/ui wrapped components
│   ├── hooks/
│   │   ├── useAuth.ts
│   │   └── useVisits.ts               ← React Query hooks
│   ├── store/
│   │   └── authStore.ts               ← lightweight auth state (Zustand or Context)
│   ├── types/
│   │   └── index.ts                   ← shared TypeScript types matching backend Pydantic schemas
│   └── utils/
├── public/
├── index.html
├── vite.config.ts
├── tailwind.config.ts
├── tsconfig.json
└── README.md
```

---

## 4. Shared Conventions Across All Three Repos

- **`.env.example`** committed in each repo, real `.env` gitignored — API base URLs, Maps API keys, FCM config.
- **README per repo** documents local setup steps — feeds directly into Phase 10 Documentation with minimal extra work if written as you go rather than backfilled.
- **Naming consistency**: field names in backend Pydantic schemas, TypeScript types in web, and Kotlin data classes in Android should mirror each other exactly (e.g., `geofenceRadiusM` everywhere at the API boundary — FastAPI's `alias_generator` on Pydantic schemas converts Python's `geofence_radius_m` to camelCase `geofenceRadiusM` in JSON automatically, so internal Python style stays snake_case while the wire format stays camelCase for the clients). Reduces agent confusion when a single feature spans all three repos.
- **Git branch convention**: `main` (production), `develop` (integration), `feature/phase-X-description` per unit of work — keeps each Antigravity session's changes isolated and reviewable before merge.

---

**Next up:** Security Design (Phase 2.4) — the last technical piece before ER Diagrams close out Phase 2.
