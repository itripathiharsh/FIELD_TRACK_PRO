# FieldTrack Pro — Repair Baseline (Phase 0)

**Captured:** 2026-08-08
**Purpose:** Frozen, verified record of system state immediately before any defect repair begins.
**Authority:** The forensic audit report is the repair specification. This document records the
*verified* environmental state, including where the audit's environmental claims needed correction.

> No application defect was fixed during Phase 0. Changes were limited to safety,
> reproducibility, secret rotation, test infrastructure, and documentation.

---

## 1. Version control state

### As discovered in Phase 0

| Item | Value |
|---|---|
| Repository | **NONE — the project was not under version control** |
| `git rev-parse` at project root | `fatal: not a git repository` |
| `.git` / `.hg` / `.svn` anywhere under project root | none found |
| `.gitignore` files present | 3 (backend, web, android) — present but **inert** |

### RESOLVED at the start of Phase 1 (FT-063)

| Item | Value |
|---|---|
| Repository root | `F:\sentio wala\field track pro` |
| Initialised | yes (`git init`, git 2.55.0.windows.2) |
| **Baseline commit** | **`18e90881c6fb0f9f772ea86c00f3167cdb516948`** |
| Baseline tag | `phase0-baseline` |
| Files tracked | 426 |
| Working tree at commit | clean |
| `core.autocrlf` | `false` (preserve line endings exactly) |

#### Secret / artefact exclusion verified before committing

A root `.gitignore` was added on top of the three sub-project files. Staged
content was audited; every one of these matched **0** staged files:

`.env` · `node_modules` · `*.dump` · `*.zip` · `__pycache__` · `.pytest_cache`
· `.gradle/` · `/build/` · `*.log` · `pytest_full_output.txt`

* `fieldtrackpro-backend/.env` confirmed ignored via `git check-ignore`
  (`fieldtrackpro-backend/.gitignore:32`).
* The three `.env.example` files **are** tracked, by design.
* Byte-level scan of all 426 staged files for the real DB password and the real
  JWT secret: **0 occurrences**.
* Only `media_storage/.gitkeep` is tracked from the storage tree; runtime media
  is ignored.

**Rollback:** `git reset --hard phase0-baseline` restores the code baseline;
the verified `pg_dump` in §5 restores the database.

---

## 2. Backend baseline

| Item | Value |
|---|---|
| Language | Python 3.11.9 |
| Package manager | Poetry 2.4.1 |
| `poetry check --lock` | `All set!` |
| Application import | OK |
| Endpoints registered (OpenAPI) | **40** |
| Framework | FastAPI 0.141.1 |
| ORM | SQLAlchemy 2.0.51 (async) |
| DB driver | asyncpg 0.31.0 |
| Spatial | GeoAlchemy2 0.20.0 |
| Migrations | Alembic 1.19.0 |
| Auth | python-jose 3.5.0, bcrypt 5.0.0 |

### Canonical commands (verified working)

```bash
cd fieldtrackpro-backend
poetry install --extras dev          # NOTE: --extras dev is REQUIRED for tests
poetry run python -m pytest -q                     # unit suite
poetry run python -m pytest tests/integration -q   # integration suite
poetry run alembic current
poetry run uvicorn app.main:app --reload --port 8000
```

### Environment corrections made during Phase 0

Two reproducibility defects were found and fixed. Neither is an application defect;
both silently invalidated the previously reported test evidence.

| Problem | Impact | Resolution |
|---|---|---|
| Poetry's active virtualenv (`…-3NkDn5oa-…`) was **empty**; all dependencies lived in a second, stale venv (`…-yn6cSvRk-…`). `poetry run pytest` failed with `No module named pytest`. | The documented command did not work. The "88 passed" evidence was only reproducible by invoking the stale venv's interpreter directly. | Ran `poetry install --extras dev` to populate the canonical environment. |
| `psycopg2` was **not declared** in `pyproject.toml`, but `tests/conftest.py` imports it to decide whether the DB is reachable. Its absence made `IS_DB_MIGRATED = False`. | **17 database tests silently SKIPPED** in a clean environment while still reporting success. A fresh clone would show `71 passed, 17 skipped` — not 88 passed. | Added `psycopg2-binary` to the `dev` extra; re-locked. |

---

## 3. Test baseline

### Before Phase 0 corrections (clean, reproducible environment)

```
71 passed, 17 skipped in 2.88s
```

The 17 skips were all `@requires_db`, reported as
`"Requires PostGIS PostgreSQL database migration (external prerequisite)"` —
misleading, because the database **was** present and migrated. The real cause was the
missing `psycopg2` dependency.

### After Phase 0 corrections (authoritative baseline)

```
88 passed in 4.37s     (0 skipped, 0 failed)
```

### Existing suite composition

| File | Tests |
|---|---|
| `tests/test_state_machine.py` | 21 |
| `tests/test_auth.py` | 15 |
| `tests/test_security.py` | 15 |
| `tests/test_geo_verification.py` | 11 |
| `tests/test_validation.py` | 11 |
| `tests/test_media.py` | 10 |
| `tests/test_health.py` | 3 |
| `tests/test_routes.py` | 2 |
| **Total** | **88** |

### Categorisation (per Phase 0.5)

| Category | Count | Assessment |
|---|---|---|
| Genuine unit tests (pure functions: bcrypt, JWT, Haversine, state machine) | ~36 | **Sound.** Real value. |
| File-validation / local-storage unit tests | ~12 | **Sound.** Real value. |
| Authentication tests | 15 | Failure paths only. **No successful-login test existed.** |
| Authorization tests | ~6 | Negative only ("employee gets 403"). **No positive admin path.** |
| DB integration tests | 17 | Assert only status membership, e.g. `in (200, 404)`. |
| API success-path tests | **0** | **Every 2xx business path was untested.** |
| API failure-path tests | ~30 | 401/403/422 assertions. |
| Frontend tests | **0** | None exist. |
| E2E / browser tests | **0** | None exist. |

**Conclusion:** the 88 tests are real and now genuinely pass, but they characterise
almost no business behaviour. None of the 6 CRITICAL defects is detectable by them.

---

## 4. Database baseline

| Item | Value |
|---|---|
| Server | PostgreSQL **17.10** (x86_64-windows) |
| Spatial | PostGIS **3.5** (`USE_GEOS=1 USE_PROJ=1 USE_STATS=1`) |
| Database | `fieldtrackpro_dev` |
| Host/port | `127.0.0.1:5432` |
| Alembic current | `02bc15442e20` |
| Alembic heads | `02bc15442e20` |
| Drift | none (current == head) |
| Migration chain | `<base> → 74454433b4c6 (empty) → 02bc15442e20 (create_all_tables)` |
| Tables | 14 (incl. `alembic_version`, `spatial_ref_sys`) |

### Seed row counts (frozen reference)

| Table | Rows |
|---|---|
| users | 2 |
| employees | 1 |
| territories | 1 |
| customers | 2 |
| visits | 1 |
| visit_media | 1 |
| geo_verification_logs | 1 |
| refresh_tokens | 8 *(all revoked during rotation)* |
| notifications | 0 |
| requirement_categories | 0 |
| requirement_forms | 0 |
| visit_signatures | 0 |

`media_storage/`: **0 files** — confirming FT-047 (the single `visit_media` row is a
dangling reference with no bytes on disk).

**Verified after all Phase 0 work: counts unchanged, zero test residue.**

---

## 5. Database backup

| Item | Value |
|---|---|
| File | `C:\Users\Admin\FieldTrackPro_Backups\fieldtrackpro_dev_PHASE0_20260808_180214.dump` |
| Format | PostgreSQL custom (`pg_dump -Fc`) |
| Size | 36,920 bytes |
| SHA-256 | `DD4281A6B9BE1C4E7D337A6D41901F45B55F028BFD1D9570102656F36BA0C492` |
| Outside source tree | **yes** (`C:\Users\Admin\…`, not under `F:\sentio wala`) |
| Committed to repo | no (and no repo exists) |

### Restore verification (not merely created — proven restorable)

1. `pg_restore --list` → 14 `TABLE DATA` entries readable.
2. Restored in full into a scratch database `ftp_backup_verify` → exit code 0.
3. Row counts in the restored copy matched the live database exactly.
4. `alembic_version` = `02bc15442e20`.
5. PostGIS geometry intact: `ST_AsText(location)` = `POINT(77.5946 12.9716)`.
6. Scratch database dropped; live database untouched.

**Restore command (if rollback is needed):**
```bash
pg_restore -h 127.0.0.1 -U postgres -d fieldtrackpro_dev --clean --if-exists \
  "C:\Users\Admin\FieldTrackPro_Backups\fieldtrackpro_dev_PHASE0_20260808_180214.dump"
```

---

## 6. Frontend baseline

| Item | Value |
|---|---|
| Node / npm | v20.19.4 / 10.8.2 |
| React / Vite / TS | 18.3.1 / 5.4.21 / 5.6 |
| `tsc --noEmit` | **exit 0** (no type errors) |
| `npm run build` | **success** — 1612 modules, 276.05 kB JS, 29.62 kB CSS |
| `npm run lint` | **FAILS — `eslint` is not installed** (script declared, dependency absent) |
| Tests | none configured |

Build artifacts (`dist/`) were removed after verification.

---

## 7. Android baseline

| Item | Value |
|---|---|
| Gradle wrapper (`gradlew.bat`) | **absent** |
| `gradle/wrapper/gradle-wrapper.properties` | **absent** |
| `JAVA_HOME` | not set; no `java` on PATH |
| Build status | **CANNOT BE BUILT** |
| Test status | **NOT TESTED** |

Confirms the audit: Android is static source only, not part of the running system.
Physical-device testing remains **NOT TESTED**.

---

## 8. Secret exposure remediation (FT-043)

Full detail in `docs/SECRET_ROTATION.md`. Summary — **no secret values are recorded anywhere**:

* `fieldtrackpro-backend/.env` contained a live DB password and JWT signing key.
* Scanned every source file (`.py .ts .tsx .js .json .kt .md .toml .ini .yml .html .bru`)
  for the secret values: **the only file containing them was `.env` itself.**
* `.env` is correctly matched by the backend `.gitignore`.
* No VCS exists → **no history purge required or possible**.
* Database password **rotated**; a dedicated least-privilege role `fieldtrack_app`
  now replaces superuser `postgres` in the connection string.
* JWT signing secret **rotated**; the previous secret is verified rejected.
* All 8 pre-rotation refresh tokens **revoked**.
* `.env.example` rewritten with placeholders only, and completed with the storage/MinIO
  keys it was previously missing (closes FT-056).

---

## 9. Blockers and risks carried into Phase 1

| # | Blocker | Severity | Impact |
|---|---|---|---|
| B-1 | **No version control.** | **HIGH** | No commit rollback, no diff review, no branch isolation. Strongly recommend initialising a repo and making a baseline commit before Phase 1. |
| B-2 | `npm run lint` is broken (eslint not a dependency). | MEDIUM | Frontend repairs cannot be lint-verified. |
| B-3 | No frontend test runner. | MEDIUM | FT-001 (the auth bypass) cannot get an automated regression test until Vitest is added. |
| B-4 | Android cannot be built. | LOW | FT-024…FT-027 cannot be verified beyond static review. |
| B-5 | `verify_geo_proximity` (correct PostGIS impl) vs the broken WKT helper. | INFO | Phase 5 must consolidate onto one implementation, not add a third. |

---

## 10. Definition of "verified" for this program

A defect may be marked **VERIFIED** in `REPAIR_LEDGER.md` only when all hold:

1. A named regression test exercises the **success** path (not just failure codes).
2. The test **failed before** the fix and **passes after** it.
3. Where the defect involves persistence, committed DB state is asserted through the
   **independent** synchronous connection — never inferred from an HTTP status code.
4. Tolerant assertions (`status in (200, 404)`) are not used for business-success tests.
5. The full unit suite (88) still passes.
6. Seed data and `media_storage/` are unchanged after the run.
