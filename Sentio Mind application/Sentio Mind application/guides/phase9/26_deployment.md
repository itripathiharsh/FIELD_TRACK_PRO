# FieldTrack Pro — Deployment
### Phase 9 — Getting the on-prem topology from Architecture doc actually running
### Revision 2 — Backend deployment rewritten for Python; Android/Web/Nginx sections unchanged except the proxy target

Implements the deployment diagram from the Architecture doc (Nginx → FastAPI / Postgres / MinIO, all Dockerized, single on-prem server).

---

## 1. Backend Deployment

```dockerfile
# Dockerfile
FROM python:3.12-slim AS base

# libmagic1 is required at runtime by python-magic (file-type validation, per Security Design Section 5)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libmagic1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

RUN pip install --no-cache-dir poetry==1.8.3
COPY pyproject.toml poetry.lock ./
RUN poetry config virtualenvs.create false \
    && poetry install --no-interaction --no-ansi --only main

COPY . .

EXPOSE 8000
ENTRYPOINT ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
```

**`--workers 4`**: tune to the on-prem server's actual CPU core count — this is the Python-world equivalent of the JVM thread pool the original Spring Boot container managed implicitly; unlike the JVM, Uvicorn needs this set explicitly or it defaults to a single worker process, under-utilizing multi-core hardware. Flagged in the Testing & QA doc's performance section too — restated here since this is where it's actually configured.

```yaml
# docker-compose.prod.yml
services:
  backend:
    build: .
    env_file: .env.prod   # gitignored, lives only on the server
    depends_on:
      postgres:
        condition: service_healthy
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/actuator/health"]
      interval: 30s

  nginx:
    image: nginx:alpine
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf
      - ./certs:/etc/nginx/certs
    ports:
      - "443:443"
      - "80:80"
    depends_on:
      - backend
```

The `/actuator/health` path is kept as-is (deliberately not renamed to something more Python-idiomatic like `/health`) specifically so this Docker healthcheck and Nginx config below need zero changes from the original — see the Python Backend Setup doc's note on this.

### Nginx Config (TLS Termination + Reverse Proxy + Static Web Dashboard)

**Unchanged except the upstream port** (Uvicorn listens on 8000 instead of the JVM's 8080 — an arbitrary port choice either way, updated here for consistency with the Dockerfile above):

```nginx
server {
    listen 443 ssl;
    server_name fieldtrackpro.internal;

    ssl_certificate /etc/nginx/certs/fullchain.pem;
    ssl_certificate_key /etc/nginx/certs/privkey.pem;

    add_header Strict-Transport-Security "max-age=31536000" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-Frame-Options "DENY" always;

    location /api/ {
        proxy_pass http://backend:8000/api/;
        proxy_set_header Authorization $http_authorization;
    }

    location / {
        root /usr/share/nginx/html;   # built React dashboard, per Architecture doc
        try_files $uri /index.html;
    }
}
```

**Note, unchanged from the original**: `proxy_set_header Authorization $http_authorization;` is easy to forget — Nginx doesn't forward the Authorization header by default in some configurations, and a missing header here would silently break every authenticated API call after deployment despite everything working fine in local dev (where there's no reverse proxy in between). This risk is identical regardless of backend language.

---

## 2. Database Deployment

```bash
# One-time production DB init
docker exec -it postgres_container psql -U fieldtrackpro -d fieldtrackpro_prod \
  -c "CREATE EXTENSION IF NOT EXISTS postgis;"

# Alembic migrations run automatically on backend container startup
# (add `alembic upgrade head &&` to the Dockerfile's ENTRYPOINT, or run as a one-shot init
# container ahead of `backend` in docker-compose.prod.yml — either pattern is fine;
# the key requirement, carried over from the original Flyway rule, is that migrations
# always run before the app starts serving traffic, never as a manual afterthought)
```

**Migration-on-startup wiring** — the one genuine process change from the original doc, since Alembic (unlike Flyway) isn't wired into the framework's own startup lifecycle by default:

```dockerfile
ENTRYPOINT ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4"]
```

### Backup Strategy

*(Unchanged — backup mechanics operate at the Postgres/MinIO level and have no dependency on backend language.)*

```bash
# Daily automated backup — cron job on the on-prem server
0 2 * * * docker exec postgres_container pg_dump -U fieldtrackpro fieldtrackpro_prod \
  | gzip > /backups/fieldtrackpro_$(date +\%Y\%m\%d).sql.gz

# Retain 30 days, delete older
find /backups -name "*.sql.gz" -mtime +30 -delete
```

Daily automated backups with 30-day retention, same reasoning as the original: for a system whose entire value proposition is being the trustworthy record of what happened in the field, having zero backup strategy would be a genuine liability. MinIO data (photos/signatures) should get equivalent backup treatment via `mc mirror` to a secondary location if the on-prem infra has one available.

---

## 3. Android APK Build

*(Unchanged — Android build/signing/distribution has no dependency on backend language.)*

```bash
# Release build, signed
./gradlew assembleRelease

# Signing config (build.gradle.kts)
android {
    signingConfigs {
        create("release") {
            storeFile = file(System.getenv("KEYSTORE_PATH"))
            storePassword = System.getenv("KEYSTORE_PASSWORD")
            keyAlias = System.getenv("KEY_ALIAS")
            keyPassword = System.getenv("KEY_PASSWORD")
        }
    }
    buildTypes {
        release {
            signingConfig = signingConfigs.getByName("release")
            isMinifyEnabled = true
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
        }
    }
}
```

### Distribution — A Real Decision to Make, Not Assumed
Since this is an internal business tool (not a consumer app), it will **not** go through the Google Play Store — that adds review delay and public visibility for a tool that should stay internal. Instead:
- Direct APK distribution via a private link (MDM tool, internal file share, or Firebase App Distribution for easier install/update tracking).
- **Flag for you specifically**: does your org have an MDM (Mobile Device Management) solution already, or will employees sideload the APK manually? This changes both the distribution mechanism and how app updates get pushed later — worth deciding now since it affects whether `enableUnknownSources` guidance needs to go in the User Manual (Phase 10).

### Environment-Specific Build Variants
```kotlin
android {
    flavorDimensions += "environment"
    productFlavors {
        create("staging") { buildConfigField("String", "API_BASE_URL", "\"https://staging.fieldtrackpro.internal/api/v1\"") }
        create("production") { buildConfigField("String", "API_BASE_URL", "\"https://fieldtrackpro.internal/api/v1\"") }
    }
}
```

---

## 4. Web Dashboard Deployment

*(Unchanged — the React build has no dependency on backend language.)*

```bash
npm run build   # outputs to dist/
```

```dockerfile
# Multi-stage — build then copy static files into nginx's serve directory
FROM node:20-alpine AS build
WORKDIR /app
COPY . .
RUN npm ci && npm run build

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
```

Served as static files through the same Nginx instance as the backend reverse proxy (per Architecture doc — one Nginx, dual purpose), not a separate container/server. Environment variables (`VITE_API_BASE_URL`, `VITE_MAPS_API_KEY`) are baked in at build time, so a production build script needs the right `.env.production` file present before `npm run build` runs.

---

## 5. Production Configuration

### Environment Variables Checklist (Must Be Set Before First Production Start)
```
DATABASE_URL                   # postgresql+asyncpg://user:pass@postgres:5432/fieldtrackpro_prod
JWT_SECRET                     # min 256-bit, generated fresh — never reused from dev
MINIO_ACCESS_KEY, MINIO_SECRET_KEY
MAPS_API_KEY_BACKEND            # server-restricted key, per Maps & Location Services doc
FIREBASE_CREDENTIALS_PATH        # path to the mounted Firebase service-account JSON
CORS_ALLOWED_ORIGINS               # comma-separated list, never "*" in production
```

### Startup Safety Net (Restated From Python Backend Setup, Now Actually Matters)
The `Settings` design decision from Phase 3.1 — no default values on required fields, fails loudly (`pydantic.ValidationError`) if any required env var is missing — is what prevents a production deployment from silently starting with a dev-grade JWT secret or missing Maps key. Confirm this actually holds at first production deploy, since it's the kind of thing that's easy to accidentally "fix" with a fallback value under deployment time pressure, defeating the whole point. Same discipline, same risk, as the original Spring `application-prod.yml` design.

### VPN / Network Access — The Question Flagged Back in the Architecture Doc, Still Unanswered
This genuinely needs your input before go-live, not another product-owner assumption, and the backend migration doesn't change it either way: **do field employees' Android devices reach the on-prem server over the open internet, or does your organization require VPN access?** If VPN-gated, add a VPN client requirement + setup steps to the User Manual (Phase 10) and confirm the on-prem firewall allows the VPN subnet through to port 443. If open internet, confirm the on-prem server has a stable public IP or DNS name and that opening port 443 externally is acceptable per your org's security posture.

---

## Phase 9 — Complete

Backend (now Python/Uvicorn, with Alembic migrations wired into container startup and worker count tuned for the host), database (with the same backup strategy as before), Android APK, and Web Dashboard are all deployable against the Architecture doc's on-prem topology.

**Next up:** Phase 10 — Documentation (API Documentation, User Manual, Admin Manual, Deployment Guide, Technical Documentation) — the last phase before MVP is considered complete.
