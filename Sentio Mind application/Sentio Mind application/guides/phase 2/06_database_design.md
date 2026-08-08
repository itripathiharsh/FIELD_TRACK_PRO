# FieldTrack Pro — Database Design
### Phase 2.1 — System Design
### Revision 2 — wording updated for Python/SQLAlchemy backend (schema itself is unchanged)

PostgreSQL 15+ with PostGIS extension. Schema below covers every module from the Features doc. Naming convention: snake_case tables/columns, singular table names avoided in favor of plural (`employees`, `visits`) — standard REST/ORM convention, matched by SQLAlchemy model names (`Employee` class → `employees` table) the same way it previously matched Spring Data JPA's convention. **The schema, table names, column names, and types below are identical to the original design** — the backend language change has zero effect on the database shape.

---

## 1. Entity Overview

| Table | Purpose |
|---|---|
| `users` | Shared login table for both employees and admins (role-differentiated) |
| `employees` | Employee-specific profile data, linked to `users` |
| `territories` | Optional grouping for employee assignment |
| `customers` | Customer records with geocoded location |
| `visits` | Core entity — one row per scheduled/completed visit |
| `requirement_forms` | Captured requirement data, one-to-one with a visit |
| `visit_media` | Photos/documents attached to a visit |
| `visit_signatures` | Employee + customer signatures per visit |
| `geo_verification_logs` | Every check-in/check-out attempt, valid or flagged |
| `notifications` | Notification records sent to users |
| `requirement_categories` | Admin-editable taxonomy for requirement capture dropdown |

---

## 2. Table Definitions

### `users`
| Column | Type | Notes |
|---|---|---|
| id | UUID (PK) | |
| email | VARCHAR(255) UNIQUE | nullable if mobile-only login used |
| mobile_number | VARCHAR(20) UNIQUE | nullable if email-only |
| password_hash | VARCHAR(255) | bcrypt (via `passlib`) |
| role | ENUM('EMPLOYEE','ADMIN') | |
| is_active | BOOLEAN | default true — deactivation instead of delete |
| created_at | TIMESTAMPTZ | |
| updated_at | TIMESTAMPTZ | |

### `territories`
| Column | Type | Notes |
|---|---|---|
| id | UUID (PK) | |
| name | VARCHAR(100) | |
| created_at | TIMESTAMPTZ | |

### `employees`
| Column | Type | Notes |
|---|---|---|
| id | UUID (PK) | |
| user_id | UUID (FK → users.id) UNIQUE | one-to-one with users |
| full_name | VARCHAR(150) | |
| territory_id | UUID (FK → territories.id) | nullable |
| created_at | TIMESTAMPTZ | |

### `customers`
| Column | Type | Notes |
|---|---|---|
| id | UUID (PK) | |
| name | VARCHAR(150) | |
| contact_number | VARCHAR(20) | |
| address | TEXT | |
| location | GEOGRAPHY(POINT, 4326) | PostGIS point — lat/long, indexed with GIST, mapped via GeoAlchemy2's `Geography` column type |
| geofence_radius_m | INTEGER | default 75, admin-overridable per C3 |
| created_by | UUID (FK → users.id) | admin who created it |
| created_at | TIMESTAMPTZ | |

### `visits`
| Column | Type | Notes |
|---|---|---|
| id | UUID (PK) | |
| customer_id | UUID (FK → customers.id) | |
| employee_id | UUID (FK → employees.id) | |
| scheduled_at | TIMESTAMPTZ | |
| status | ENUM('PENDING','IN_PROGRESS','COMPLETED','MISSED','FLAGGED') | matches D3 state machine |
| check_in_at | TIMESTAMPTZ | nullable until check-in |
| check_in_location | GEOGRAPHY(POINT, 4326) | nullable, actual device coords at check-in |
| check_out_at | TIMESTAMPTZ | nullable |
| created_by | UUID (FK → users.id) | admin who scheduled it |
| created_at | TIMESTAMPTZ | |
| updated_at | TIMESTAMPTZ | |

### `requirement_categories`
| Column | Type | Notes |
|---|---|---|
| id | UUID (PK) | |
| name | VARCHAR(100) | admin-editable, per H2 |
| is_active | BOOLEAN | default true |

### `requirement_forms`
| Column | Type | Notes |
|---|---|---|
| id | UUID (PK) | |
| visit_id | UUID (FK → visits.id) UNIQUE | one-to-one with visit |
| category_id | UUID (FK → requirement_categories.id) | |
| description | TEXT | |
| priority | ENUM('LOW','MEDIUM','HIGH') | |
| expected_timeline | VARCHAR(100) | free text, e.g. "2 weeks" |
| budget_range | VARCHAR(100) | nullable, optional per locked decision |
| notes | TEXT | nullable |
| submitted_at | TIMESTAMPTZ | |

### `visit_media`
| Column | Type | Notes |
|---|---|---|
| id | UUID (PK) | |
| visit_id | UUID (FK → visits.id) | one visit can have many media items |
| media_type | ENUM('PHOTO','DOCUMENT') | |
| storage_key | VARCHAR(500) | MinIO object key, not the file itself |
| file_size_bytes | BIGINT | |
| uploaded_at | TIMESTAMPTZ | |

### `visit_signatures`
| Column | Type | Notes |
|---|---|---|
| id | UUID (PK) | |
| visit_id | UUID (FK → visits.id) | |
| signature_type | ENUM('EMPLOYEE','CUSTOMER') | |
| storage_key | VARCHAR(500) | signature stored as image in MinIO |
| signed_at | TIMESTAMPTZ | |

### `geo_verification_logs`
| Column | Type | Notes |
|---|---|---|
| id | UUID (PK) | |
| visit_id | UUID (FK → visits.id) | |
| attempted_at | TIMESTAMPTZ | |
| device_location | GEOGRAPHY(POINT, 4326) | raw coordinates sent by device |
| distance_from_customer_m | NUMERIC | computed server-side |
| is_valid | BOOLEAN | result of server-side PostGIS check |
| failure_reason | VARCHAR(255) | nullable, e.g. "outside radius", "GPS accuracy too low" |
| idempotency_key | VARCHAR(255) | nullable, dedupes retried check-in requests (see Business Logic doc) |

### `notifications`
| Column | Type | Notes |
|---|---|---|
| id | UUID (PK) | |
| user_id | UUID (FK → users.id) | recipient |
| visit_id | UUID (FK → visits.id) | nullable, contextual |
| type | ENUM('NEW_VISIT','REMINDER','OVERDUE','COMPLETED','GEO_FAILURE_ALERT') | |
| message | TEXT | |
| is_read | BOOLEAN | default false |
| sent_at | TIMESTAMPTZ | |

---

## 3. Relationships Summary

- `users` 1—1 `employees` (only for EMPLOYEE-role users)
- `territories` 1—N `employees`
- `customers` 1—N `visits`
- `employees` 1—N `visits`
- `visits` 1—1 `requirement_forms`
- `visits` 1—N `visit_media`
- `visits` 1—N `visit_signatures` (max 2 rows in practice — EMPLOYEE + CUSTOMER, enforced via a unique constraint on `(visit_id, signature_type)`)
- `visits` 1—N `geo_verification_logs` (every attempt logged, not just the successful one — this is what makes the Geo-verification Report possible)
- `requirement_categories` 1—N `requirement_forms`
- `users` 1—N `notifications`

---

## 4. Indexes

- `customers.location` → GIST index (PostGIS spatial queries for geo-fence checks)
- `visits.check_in_location` → GIST index (for admin's live map / distance analytics)
- `visits (employee_id, status)` → composite index — powers the Employee dashboard's "today's visits" query
- `visits (scheduled_at)` → for date-range report filtering
- `geo_verification_logs (visit_id, attempted_at)` → composite index for report queries
- `geo_verification_logs (visit_id, idempotency_key)` → unique composite index, backs the idempotent check-in mechanism
- `users.email`, `users.mobile_number` → unique indexes (already implied by UNIQUE constraint)

---

## 5. Design Decisions Worth Flagging

- **`geo_verification_logs` logs every attempt, not just the final successful one.** This is deliberate — it's the audit trail that proves the product's core value proposition. Without it, the Geo-verification Report (K4) has nothing to report on.
- **`users` is shared between employees and admins** rather than two separate tables, to keep auth logic (login, JWT, password reset) in one place. Role differentiates behavior, not schema duplication.
- **Soft deactivation (`is_active`), not hard deletes**, on `users` and `requirement_categories` — historical visit data must never orphan or break when an employee leaves.
- **UUID primary keys** everywhere instead of auto-increment integers — avoids ID collisions if this ever needs to sync across multiple on-prem instances later, and doesn't leak record counts via sequential IDs in API responses.
- **All migrations are written and applied through Alembic** (replacing Flyway) — same one-way-forward, version-controlled discipline, generated from SQLAlchemy model diffs and reviewed before applying, never hand-edited after being applied anywhere.

---

**Next up:** API Design (Phase 2.2) — defining the actual REST endpoints against this schema.
