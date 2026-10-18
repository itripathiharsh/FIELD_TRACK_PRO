# FieldTrack Pro

Enterprise Field Force Automation, Visit Management & Geofenced Verification Platform.

---

## 1. Overview

**FieldTrack Pro** is a mission-critical platform designed for distributed field operations, sales force automation, and automated geo-verification. It ensures high-integrity field visits, strict geofence adherence, offline-first execution, requirement collection, and end-to-end ledger/payment tracking.

The system comprises three coordinated tiers:
1. **Web Admin Portal**: React 18 + TypeScript + Vite + Tailwind CSS dashboard for live territory management, scheduling, audit logs, reports, and collections overview.
2. **FastAPI Backend Service**: High-performance asynchronous Python REST API powered by PostgreSQL 17 + PostGIS, SQLAlchemy (Async), Alembic, and Pydantic v2.
3. **Android Field Companion**: Modern Kotlin + Jetpack Compose application with offline queueing, background notification synchronization, hardware camera capture, digital signature collection, and geodesic location verification.

---

## 2. System Architecture

```
                               ┌────────────────────────────────────────┐
                               │       React 18 Admin Dashboard        │
                               │  (Vite + Tailwind CSS + MapLibre GL)  │
                               └───────────────────┬────────────────────┘
                                                   │
                                            HTTPS / REST JSON
                                                   │
                                                   ▼
┌───────────────────────────┐          ┌───────────────────────────────┐
│   Android Field App       │  REST    │      FastAPI Backend API      │
│ (Kotlin + Jetpack Compose │◄────────►│   (Python 3.11+ / Asyncpg)   │
│   Room + WorkManager)     │          └───────────────┬───────────────┘
└───────────────────────────┘                          │
                                                       │ SQLAlchemy (Async)
                                                       ▼
                                       ┌───────────────────────────────┐
                                       │     PostgreSQL 17 + PostGIS   │
                                       │ (Spatial Indices + Relations) │
                                       └───────────────────────────────┘
```

---

## 3. Major Features

### 📍 Spatial Geo-Verification & Geofencing
- Automated geofence boundary verification (100m accuracy threshold) calculating geodesic distance using PostGIS and Haversine math.
- Anti-fraud detection: Rejects mocked GPS locations, low-accuracy fixes, and stale GPS timestamps.
- Interactive MapLibre GL spatial map interface displaying territory clusters, customer locations, and field representative coordinates.

### 🏢 Hierarchical Territory & Area Management
- Multi-tier spatial hierarchy: **Zone → Area → Customer Outlets**.
- Territory-based field representative assignment with real-time audit logging and automatic unassignment handling.

### 📋 Dynamic Requirement Forms & Workflows
- Admin-defined dynamic form templates (text, numeric, dropdown, multi-select, media attachments).
- Strict state-machine validation across visit lifecycles: `SCHEDULED` → `IN_PROGRESS` → `COMPLETED` / `FLAGGED` / `MISSED`.

### 📴 Offline-First Execution & Sync Engine
- Local Room DB storage on Android allowing offline check-ins, media capture, order note collection, and signatures.
- Background sync scheduler via WorkManager with automatic retry, exponential backoff, and conflict resolution.

### 💳 Collections, Aging & Ledger Tracking
- Outlet accounts and invoicing ledger tracking overdue balances, partial payments, and payment receipts.
- Real-time aggregation of collections metrics, outstanding balances, and territory-level performance.

### 🔔 Notifications & Real-Time Sync
- Periodic background polling & WorkManager notifications alerting field representatives of new assignments, cancellations, and geofence alerts.

---

## 4. Repository Structure

```
.
├── fieldtrackpro-backend/      # FastAPI asynchronous REST backend
│   ├── alembic/                # Database migrations (Alembic)
│   ├── app/                    # Application source (routers, services, models, repos, schemas)
│   ├── scripts/                # Operational scripts (bootstrap_admin, dry-run-by-default cleanups, grant_runtime_role.sql)
│   ├── tests/                  # Integration and unit test suites
│   ├── pyproject.toml          # Poetry dependency configuration
│   └── .env.example            # Environment variable template
├── fieldtrackpro-web/          # React + Vite admin dashboard
│   ├── src/                    # Components, pages, hooks, state, api clients
│   ├── public/                 # Static assets, logos, brand fonts
│   ├── package.json            # Node dependencies and build scripts
│   └── .env.example            # Frontend environment variable template
├── fieldtrackpro-android/      # Native Kotlin Jetpack Compose application
│   ├── app/                    # Android application module (UI, data, services, workers)
│   ├── build.gradle.kts        # Root Gradle build script
│   └── .env.example            # Android configuration template
└── bruno/                      # Bruno API test collection
```

---

## 5. Local Development Setup

### Prerequisites
- **Python**: 3.11 or higher with [Poetry](https://python-poetry.org/)
- **Node.js**: 18.x or 20.x with `npm`
- **Java / Android**: JDK 17+ and Android SDK (API Level 26+)
- **Database**: PostgreSQL 17 with PostGIS extension enabled

---

### Step 1: Database Setup

Ensure PostgreSQL is running and initialize the database with PostGIS:

```sql
CREATE DATABASE fieldtrackpro_dev;
\c fieldtrackpro_dev;
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
```

---

### Step 2: Backend Setup (FastAPI)

1. Navigate to the backend directory:
   ```bash
   cd fieldtrackpro-backend
   ```
2. Configure environment variables:
   ```bash
   cp .env.example .env
   # Edit .env with your local database URL and JWT secret
   ```
3. Install dependencies:
   ```bash
   poetry install
   ```
4. Run database migrations:
   ```bash
   poetry run alembic upgrade head
   ```
5. *(Optional)* Create the first admin (never resets an existing admin; refuses production without a flag):
   ```bash
   ADMIN_BOOTSTRAP_EMAIL=you@example.com ADMIN_BOOTSTRAP_PASSWORD='<12+ chars>' poetry run python scripts/bootstrap_admin.py
   ```
6. Start the development server:
   ```bash
   poetry run uvicorn app.main:app --reload --port 8000
   ```
   - API Endpoint: `http://localhost:8000`
   - Interactive Swagger Docs: `http://localhost:8000/docs`
   - ReDoc: `http://localhost:8000/redoc`

---

### Step 3: Frontend Setup (React Admin Dashboard)

1. Navigate to the web directory:
   ```bash
   cd ../fieldtrackpro-web
   ```
2. Configure environment variables:
   ```bash
   cp .env.example .env
   ```
3. Install dependencies and start the Vite development server:
   ```bash
   npm install
   npm run dev
   ```
   - Web Dashboard: `http://localhost:5173`

---

### Step 4: Android App Setup (Jetpack Compose)

1. Open `fieldtrackpro-android` in **Android Studio Hedgehog / Iguana / Ladybug**.
2. Sync Gradle dependencies.
3. Build the debug APK or install directly to a connected physical device / emulator:
   ```bash
   cd ../fieldtrackpro-android
   ./gradlew assembleDebug
   ./gradlew installDebug
   ```

---

## 6. Running Tests

### Web Frontend Tests
```bash
cd fieldtrackpro-web
npm run test
npm run build
```

### Backend Integration & Unit Tests
```bash
cd fieldtrackpro-backend
poetry run pytest
```

### Android Unit Tests
```bash
cd fieldtrackpro-android
./gradlew testDebugUnitTest
```

---

## 7. Configuration & Environment Variables

### Backend (`fieldtrackpro-backend/.env`)
| Variable | Description | Default / Example |
| :--- | :--- | :--- |
| `ENVIRONMENT` | Runtime environment (`dev`, `staging`, `production`) | `dev` |
| `DATABASE_URL` | Async PostgreSQL connection string | `postgresql+asyncpg://user:pass@127.0.0.1:5432/fieldtrackpro_dev` |
| `MIGRATION_DATABASE_URL` | Owner-role URL used by Alembic only (falls back to `DATABASE_URL`) | unset |
| `JWT_SECRET` | 256-bit cryptographically secure key for JWT tokens | `<random-32-char-string>` |
| `MEDIA_SIGNING_SECRET` | Secret key for generating presigned media URLs (required in production, must differ from `JWT_SECRET`) | `<random-32-char-string>` |
| `OTP_HMAC_SECRET` | Keyed-hash secret for password-reset OTPs (derived from `JWT_SECRET` when unset) | unset |
| `CORS_ALLOWED_ORIGINS` | Exact permitted origins: comma-separated (`https://a.com,https://b.com`) or a JSON array. No wildcards. | `["http://localhost:5173"]` |
| `ENFORCE_PASSWORD_CHANGE` | When `true`, staff flagged `must_change_password` get `403 PASSWORD_CHANGE_REQUIRED` on every endpoint except `/auth/me`, `/auth/logout`, `/auth/refresh`, `/auth/change-password` (`PATCH /users/me/password` also works) | `false` (`true` in `render.yaml`) |
| `TRUSTED_PROXY_HOPS` | Reverse-proxy hops in front of the API. The per-IP rate-limit key is the `X-Forwarded-For` entry this many hops from the right; `0` ignores the header. Start uvicorn with `--no-proxy-headers`, never `--forwarded-allow-ips='*'` | `1` |
| `REFRESH_COOKIE_SAMESITE` | `lax` / `strict` / `none` for the refresh cookie (auto: `none` in production) | unset |
| `MAX_REQUEST_BODY_BYTES` | Hard cap on any request body (413 `REQUEST_TOO_LARGE` before parsing) | `31457280` |
| (per-endpoint upload caps) | Images 10 MB, documents 20 MB, outlet proof `OUTLET_PROOF_MAX_IMAGE_BYTES`; chunked read, `413 FILE_TOO_LARGE` the moment the cap is crossed | fixed |
| `STORAGE_PROVIDER` | Media storage provider (`LOCAL` or `MINIO` = any S3-compatible bucket) | `LOCAL` |
| `MINIO_ENDPOINT`, `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY`, `MINIO_BUCKET`, `MINIO_SECURE`, `MINIO_REGION` | S3-compatible storage (see `fieldtrackpro-backend/STORAGE_MIGRATION.md`) | dev defaults; rejected in production |
| `OUTLET_PROOF_REQUIRED_FOR_NEW_OUTLET` | Employee-submitted new outlets must carry a live proof (`422 OUTLET_PROOF_REQUIRED`) | `true` |
| `OUTLET_PROOF_MAX_ACCURACY_M`, `OUTLET_PROOF_MAX_AGE_SECONDS`, `OUTLET_PROOF_FUTURE_TOLERANCE_SECONDS` | Live-capture rules: GPS accuracy, freshness of `captured_at`, clock skew | `30`, `180`, `60` |
| `OUTLET_PROOF_CONFIRM_RADIUS_M`, `OUTLET_PROOF_AUTO_VERIFY_MIN_AGREEING`, `OUTLET_PROOF_AUTO_VERIFY_MAX_ACCURACY_M` | Confirmation radius and optional auto-verification by N agreeing employees (`0` = off) | `50`, `0`, `20` |
| `OUTLET_PROOF_MAX_IMAGE_BYTES`, `OUTLET_PROOF_MAX_DIMENSION_PX`, `OUTLET_PROOF_JPEG_QUALITY`, `OUTLET_PROOF_SIGNED_URL_MINUTES`, `OUTLET_PROOF_UNATTACHED_TTL_HOURS` | Stored image rules and link/expiry lifetimes | `10 MB`, `1600`, `82`, `10`, `48` |
| `REFRESH_REUSE_GRACE_SECONDS` | A rotated refresh token replayed within this window is a benign duplicate (new rotation); later replay revokes all sessions | `10` |
| `SMS_PROVIDER` (+ `SMS_API_KEY`, `SMS_SENDER_ID`, `SMS_TEMPLATE_ID`, Twilio vars) | OTP SMS; `mock` is rejected in production | `mock` |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM_EMAIL` | OTP e-mail. Port 465 = implicit TLS, 587/2525 = STARTTLS when offered | `587` |
| `SMTP_ALLOW_INSECURE` | Allow SMTP credentials without TLS (local dev only; ignored in production) | `false` |
| `ENABLE_SCHEDULER` | In-process missed-visit/cleanup jobs. **Single instance only** (no locking) | `true` |

### Web Frontend (`fieldtrackpro-web/.env`)
| Variable | Description | Default / Example |
| :--- | :--- | :--- |
| `VITE_API_BASE_URL` | Base URL for FastAPI REST endpoints | `http://localhost:8000/api/v1` |
| `VITE_APP_ENV` | Application mode | `development` |

---

---

## 7A. Authentication, Roles & Operations Notes

- **Roles:** exactly two, `ADMIN` and `EMPLOYEE` (there is no manager role). Admins have global access; employees are restricted to their own profile, assigned/covered outlets, their own visits and the requirements they submitted. An ad-hoc visit only grants access to its outlet while it is pending/in progress and was created the same IST day.
- **No seeding on boot and no default passwords in the repo.** Create the first administrator once with `scripts/bootstrap_admin.py` (`ADMIN_BOOTSTRAP_EMAIL`, `ADMIN_BOOTSTRAP_PASSWORD` >= 12 chars; refuses production without `--i-understand-production`; never resets an existing user).
- **Forced password change.** `POST /auth/login`, `POST /auth/refresh` and `GET /auth/me` return `must_change_password`. With `ENFORCE_PASSWORD_CHANGE=true` a flagged account gets `403 {"error": {"code": "PASSWORD_CHANGE_REQUIRED"}}` everywhere else until it calls `PATCH /api/v1/users/me/password` (alias `POST /api/v1/auth/change-password`) with `{"old_password", "new_password"}` (8-128 characters, at most 72 bytes - longer is `422 PASSWORD_TOO_LONG` -, different from the current password). Success returns 200 with a fresh token pair (`access_token`, `refresh_token`, `must_change_password=false`), clears the flag and revokes all OLD refresh tokens.
- **Account deletion.** `DELETE /api/v1/auth/me` with JSON body `{"password": "<current password>", "reason": "<optional>"}` for every role (`401 AUTH_INVALID_PASSWORD` when wrong, `429 AUTH_RATE_LIMITED` after 5 wrong attempts per 15 minutes). Admin self-deletions are serialised with a Postgres advisory lock so the last active admin can never be removed.
- **Payment lifecycle.** Collection submitted (`PENDING_VERIFICATION`) -> admin verifies (or rejects with a reason) -> verification queues one Tally write-back job -> the Tally Sync Agent posts the receipt and acknowledges -> the payment is **posted to Tally** and only then settles the invoice (until then it is "awaiting Tally"; failed or 30-minute-stuck jobs are flagged to admins).
- **Outlet proofs.** Employees add new outlets with a live proof (photo + GPS captured together). Admins confirm/reject proofs under the customers module; images are stored via the configured storage provider and served through short-lived signed URLs.
- **Storage migration.** Render's disk is ephemeral; move media to an S3-compatible bucket by following `fieldtrackpro-backend/STORAGE_MIGRATION.md` (`scripts/migrate_storage.py` copies existing files).
- **Database grants.** No migration grants rights to the runtime role. After each migration run apply `fieldtrackpro-backend/scripts/grant_runtime_role.sql` as the schema owner (idempotent; keeps `geo_verification_logs` insert-only). It is never run automatically.
- **Scheduler.** Jobs run inside the API process without locking - deploy one API instance (or move the scheduler to its own single instance).
- **Destructive scripts.** All cleanup/purge scripts are dry-run by default; real execution needs `--execute` plus `CONFIRM_PURGE_DATABASE=<exact database name>` (and `--i-understand-production` in production). Scripts read credentials and URLs from the environment (`SCRIPT_API_URL`, `SCRIPT_ADMIN_PASSWORD`, ...), never from source.
- **Do not commit credentials.** `CREDENTIALS.md` and the `*.xlsx` files under `fieldtrackpro-backend/data/sheet/` must not be committed; rotate any password that ever appeared in them.

## 8. Production Deployment Overview

- **Web Frontend**: Pre-configured for deployment to static edge platforms (e.g., Vercel, Cloudflare Pages, AWS S3 + CloudFront). Builds to optimized static assets via `npm run build`.
- **Backend API**: Containerizable via standard ASGI servers (e.g., Uvicorn / Gunicorn) on platforms like Render, AWS ECS, or Kubernetes with managed PostgreSQL + PostGIS. Run a single API instance (in-process scheduler) with `--no-proxy-headers` and set `TRUSTED_PROXY_HOPS` to the number of proxies in front of it.
- **Android App**: Produces signed release AAB/APK bundles via Gradle release build tasks (`./gradlew bundleRelease`).

---

## 9. License

This repository is maintained for internal enterprise operations and authorized client engagements.
