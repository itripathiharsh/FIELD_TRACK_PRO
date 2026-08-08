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
