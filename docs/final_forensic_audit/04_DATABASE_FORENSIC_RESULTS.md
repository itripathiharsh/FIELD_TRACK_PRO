# Final Forensic Audit — Database Forensic Results

**Date:** 2026-08-09

---

## 1. Schema Verification

### Tables

| Table | Exists | Columns Match | Constraints | Indexes | Status |
|-------|--------|---------------|-------------|---------|--------|
| users | YES | YES | PK, unique email | idx_users_email | VERIFIED |
| employees | YES | YES | FK users.id, unique employee_code | - | VERIFIED |
| customers | YES | YES | FK users.id (created_by), FK territories.id | idx_customers_location (GIST) | VERIFIED |
| territories | YES | YES | PK | - | VERIFIED |
| visits | YES | YES | FK customers.id, FK employees.id, FK users.id (created_by) | idx_visits_check_in_location (GIST) | VERIFIED |
| visit_media | YES | YES | FK visits.id, unique storage_key, unique (visit_id, checksum_sha256) | ix_visit_media_checksum | VERIFIED |
| visit_signatures | YES | YES | FK visits.id, unique (visit_id, signature_type) | - | VERIFIED |
| geo_verification_logs | YES | YES | FK visits.id, FK users.id | - | VERIFIED |
| refresh_tokens | YES | YES | FK users.id | - | VERIFIED |

### PostGIS Columns

| Table | Column | Type | SRID | Status |
|-------|--------|------|------|--------|
| customers | location | geography(POINT) | 4326 | VERIFIED |
| visits | check_in_location | geography(POINT) | 4326 | VERIFIED |
| visits | check_out_location | geography(POINT) | 4326 | VERIFIED |

---

## 2. Migration Verification

| Check | Result |
|-------|--------|
| Alembic current | c3d81b6f4a52 |
| Alembic heads | c3d81b6f4a52 |
| Drift | NONE (current = head) |
| Migration chain | Linear, single head |

---

## 3. Persistence Verification

| Operation | Result | Evidence |
|-----------|--------|----------|
| Create customer | PASS | Customer persisted with correct location |
| Create visit | PASS | Visit persisted with PENDING status |
| Check-in | PASS | Status changed to IN_PROGRESS, location persisted |
| Check-out | PASS | Status changed to COMPLETED, location persisted |
| Media upload | PASS | Media record + file persisted |
| Signature upload | PASS | Signature record persisted |
| Geo logs | PASS | 2 logs persisted (check-in + check-out) |

---

## 4. Constraint Verification

| Constraint | Test | Result |
|------------|------|--------|
| uq_visit_media_content | Same file twice on same visit | PASS (rejected with 409) |
| uq_visit_signature | Same signature type twice | PASS (rejected with 409) |
| customers_created_by_fkey | Delete user with customers | PASS (rejected - FK constraint) |
| geo_verification_logs insert-only | Delete audit row | PASS (rejected - app role cannot delete) |

---

## 5. Foreign Key Relationships

| Relationship | ON DELETE | Status |
|--------------|-----------|--------|
| employees.user_id → users.id | CASCADE | VERIFIED |
| customers.created_by → users.id | SET NULL | VERIFIED |
| visits.customer_id → customers.id | CASCADE | VERIFIED |
| visits.employee_id → employees.id | CASCADE | VERIFIED |
| visit_media.visit_id → visits.id | CASCADE | VERIFIED |
| visit_signatures.visit_id → visits.id | CASCADE | VERIFIED |
| geo_verification_logs.visit_id → visits.id | CASCADE | VERIFIED |
| refresh_tokens.user_id → users.id | CASCADE | VERIFIED |

---

## 6. No Orphan Records

All foreign key relationships have proper constraints. No orphan records found in testing.

---

## 7. PostGIS Verification

| Function | Test | Result |
|----------|------|--------|
| ST_Distance | Distance between same point | Returns 0.0m |
| ST_DWithin | Point within radius | Returns true |
| ST_GeogFromText | WKT parsing | POINT(lng lat) - correct order |
| Spatial index | idx_customers_location | GIST index exists |
