# FieldTrack Pro — ER Diagrams
### Phase 2.5 — System Design (Final piece of Phase 2)

Visual representation of the schema from Database Design. One full diagram, plus a zoomed-in view of the core `visits` cluster since that's where most of the product's complexity lives.

---

## 1. Full Entity-Relationship Diagram

```mermaid
erDiagram
    USERS ||--o| EMPLOYEES : "has profile"
    USERS ||--o{ REFRESH_TOKENS : "owns"
    USERS ||--o{ NOTIFICATIONS : "receives"

    TERRITORIES ||--o{ EMPLOYEES : "assigned to"
    TERRITORIES ||--o{ CUSTOMERS : "assigned to"

    EMPLOYEES ||--o{ VISITS : "performs"
    CUSTOMERS ||--o{ VISITS : "receives"

    VISITS ||--o| REQUIREMENT_FORMS : "captures"
    VISITS ||--o{ VISIT_ATTACHMENTS : "has"
    VISITS ||--o{ VISIT_SIGNATURES : "has"
    VISITS ||--o{ GEO_VERIFICATION_LOGS : "logs"
    VISITS ||--o{ NOTIFICATIONS : "triggers"

    USERS {
        uuid id PK
        string email UK
        string phone UK
        string password_hash
        string role
        boolean is_active
    }

    EMPLOYEES {
        uuid id PK
        uuid user_id FK
        string full_name
        uuid territory_id FK
        string employee_code UK
    }

    TERRITORIES {
        uuid id PK
        string name
        text description
    }

    CUSTOMERS {
        uuid id PK
        string name
        string contact_number
        text address
        geography location
        int geofence_radius_m
        uuid territory_id FK
    }

    VISITS {
        uuid id PK
        uuid employee_id FK
        uuid customer_id FK
        timestamp scheduled_at
        string status
        timestamp check_in_at
        geography check_in_location
        timestamp check_out_at
        geography check_out_location
        boolean synced
    }

    REQUIREMENT_FORMS {
        uuid id PK
        uuid visit_id FK
        string category
        text description
        string priority
        string expected_timeline
        string budget_range
    }

    VISIT_ATTACHMENTS {
        uuid id PK
        uuid visit_id FK
        string file_type
        string storage_key
        string original_name
    }

    VISIT_SIGNATURES {
        uuid id PK
        uuid visit_id FK
        string signed_by
        string storage_key
        timestamp signed_at
    }

    GEO_VERIFICATION_LOGS {
        uuid id PK
        uuid visit_id FK
        timestamp attempted_at
        geography attempted_location
        numeric distance_meters
        string result
        string reason
    }

    NOTIFICATIONS {
        uuid id PK
        uuid user_id FK
        string type
        string title
        text body
        uuid related_visit_id FK
        boolean is_read
    }

    REFRESH_TOKENS {
        uuid id PK
        uuid user_id FK
        string token_hash
        timestamp expires_at
        boolean revoked
    }
```

---

## 2. Core Cluster — The "Visit Lifecycle" (Zoomed In)

This is the part of the schema that carries the actual product logic — worth isolating since it's what Phase 3 backend work and Phase 4 GPS work will spend the most time on.

```mermaid
erDiagram
    VISITS ||--o| REQUIREMENT_FORMS : "1:1 — one form per visit"
    VISITS ||--o{ VISIT_ATTACHMENTS : "1:many — photos/docs"
    VISITS ||--o{ VISIT_SIGNATURES : "1:2 — employee + customer"
    VISITS ||--o{ GEO_VERIFICATION_LOGS : "1:many — every attempt logged"

    VISITS {
        uuid id PK
        string status "PENDING to IN_PROGRESS to COMPLETED to FLAGGED and MISSED"
        geography check_in_location "server-verified, not client-trusted"
    }
```

**Reading this cluster**: a single `visits` row is the anchor for everything else — one requirement form, N attachments, up to 2 signatures (enforced at application level, not DB constraint, since `signed_by` allows exactly EMPLOYEE or CUSTOMER but nothing stops duplicate submissions without a unique constraint — see note below), and N geo-verification log entries (every check-in attempt, not just the successful one).

---

## 3. Relationship Notes & Constraints Worth Calling Out

- **`visits.employee_id` and `visits.customer_id` are both mandatory** — a visit cannot exist without both. No "draft visit" concept in MVP.
- **`requirement_forms` is 1:1 with `visits`** via a unique constraint on `visit_id` — enforced in Database Design already, restated here since it's easy to miss in a plain schema listing.
- **`visit_signatures` should have a unique constraint on `(visit_id, signed_by)`** — this wasn't explicit in the Database Design DDL and is worth adding now: without it, nothing stops two "EMPLOYEE" signature rows for the same visit. Small gap, easy fix, flagging before Phase 3 build starts.
- **`geo_verification_logs` has no foreign key back from `visits`** — it's intentionally one-directional (logs reference the visit, not the other way around) since a visit can have zero, one, or many verification attempts, and the visit itself only cares about its final `check_in_location`/`check_out_location`, not the full attempt history.
- **`notifications.related_visit_id` is nullable** — not every notification is visit-related (e.g., account-level notices in the future), so this FK is optional by design, not an oversight.

---

## Phase 2 — Complete

Five pieces done: **Database Design → API Design → Folder Structure → Security Design → ER Diagrams.** Combined with the five Phase 1 docs, you now have a full spec Antigravity can build against without guessing at any structural decision.

**Next up:** Phase 3 — Backend Development (Spring Boot Setup, Authentication, APIs, Database, Business Logic) — this is where agents start actually writing code.
