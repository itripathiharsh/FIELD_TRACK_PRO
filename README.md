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
│   ├── scripts/                # Utility and database seed scripts
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
5. *(Optional)* Seed demo data:
   ```bash
   poetry run python scripts/seed_demo_data.py
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
| `JWT_SECRET` | 256-bit cryptographically secure key for JWT tokens | `<random-32-char-string>` |
| `MEDIA_SIGNING_SECRET` | Secret key for generating presigned media URLs | `<random-32-char-string>` |
| `CORS_ALLOWED_ORIGINS` | JSON array of permitted origins | `["http://localhost:5173"]` |
| `STORAGE_PROVIDER` | Media storage provider (`LOCAL` or `MINIO`) | `LOCAL` |

### Web Frontend (`fieldtrackpro-web/.env`)
| Variable | Description | Default / Example |
| :--- | :--- | :--- |
| `VITE_API_BASE_URL` | Base URL for FastAPI REST endpoints | `http://localhost:8000/api/v1` |
| `VITE_APP_ENV` | Application mode | `development` |

---

## 8. Production Deployment Overview

- **Web Frontend**: Pre-configured for deployment to static edge platforms (e.g., Vercel, Cloudflare Pages, AWS S3 + CloudFront). Builds to optimized static assets via `npm run build`.
- **Backend API**: Containerizable via standard ASGI servers (e.g., Uvicorn / Gunicorn) on platforms like Render, AWS ECS, or Kubernetes with managed PostgreSQL + PostGIS.
- **Android App**: Produces signed release AAB/APK bundles via Gradle release build tasks (`./gradlew bundleRelease`).

---

## 9. License

This repository is maintained for internal enterprise operations and authorized client engagements.
