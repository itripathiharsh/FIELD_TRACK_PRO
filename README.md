# FieldTrack Pro

Enterprise field force tracking, visit management, and automated geo-verification platform.

## Project Structure

```
fieldtrackpro/
├── fieldtrackpro-backend/    # Python / FastAPI REST API
├── fieldtrackpro-web/        # React / Vite Admin Dashboard
├── fieldtrackpro-android/    # Kotlin / Jetpack Compose Android App
└── bruno/                    # Bruno API test collection
```

See the `README.md` inside each sub-project for full setup instructions.

## Quick Start (Local Development)

### 1. Database

Ensure PostgreSQL 17 is running and create the database:

```sql
CREATE DATABASE fieldtrackpro_dev;
```

### 2. Backend

```bash
cd fieldtrackpro-backend
cp .env.example .env      # edit DATABASE_URL
poetry install
poetry run alembic upgrade head
poetry run uvicorn app.main:app --reload --port 8000
```

Backend: `http://localhost:8000`
API Docs: `http://localhost:8000/docs`

### 3. Admin Dashboard

```bash
cd fieldtrackpro-web
cp .env.example .env
npm install
npm run dev
```

Admin UI: `http://localhost:5173`

### 4. Android App

Open `fieldtrackpro-android/` in Android Studio and run on a device or emulator (API 26+).


### 5. Seeded Data (Login Credentials)

| Email | Password | Role | Notes |
|---|---|---|---|
| `admin@fieldtrack.test` | `AdminPass123!` | ADMIN | Main admin login |
| `rep@fieldtrack.test` | `AdminPass123!` | EMPLOYEE | Vikram Nair — Bengaluru Central |
| `priya.nataraj@fieldtrack.test` | `AdminPass123!` | EMPLOYEE | Bengaluru Central |
| `arjun.mehta@fieldtrack.test` | `AdminPass123!` | EMPLOYEE | Mumbai Western Suburbs |
| `sneha.kulkarni@fieldtrack.test` | `AdminPass123!` | EMPLOYEE | Pune IT Corridor |

Demo data (territories, outlets, employees, visits, forms, invoices/payments)
is seeded by `fieldtrackpro-backend/scripts/seed_demo_data.py` — safe to
re-run, it only inserts new rows and never touches unrelated data.



1. Backend (Python with Poetry):

cd "F:\sentio wala\field track pro\fieldtrackpro-backend"
poetry install
poetry run alembic upgrade head
poetry run uvicorn app.main:app --reload --port 8000

2. Frontend (React with Vite and npm):

cd "F:\\sentio wala\\field track pro\\fieldtrackpro-web"
npm install
npm run dev

3. Android App (Gradle):

cd "F:\\sentio wala\\field track pro\\fieldtrackpro-android"
./gradlew build
./gradlew installDebug
# To run on an emulator or connected device:
# ./gradlew runDebug