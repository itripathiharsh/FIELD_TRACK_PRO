# FieldTrack Pro — API Design
### Phase 2.2 — System Design

REST/JSON API against the schema in Database Design. Base path: `/api/v1`. All endpoints (except `/auth/*`) require a valid JWT in `Authorization: Bearer <token>`. Role required is noted per endpoint.

---

## 1. Auth

| Method | Endpoint | Role | Description |
|---|---|---|---|
| POST | `/auth/login` | Public | Email/mobile + password → access + refresh token |
| POST | `/auth/refresh` | Public (valid refresh token) | Issue new access token |
| POST | `/auth/logout` | Any | Revoke refresh token |

**`POST /auth/login`**
```json
// Request
{ "identifier": "employee@example.com", "password": "••••••" }

// Response 200
{
  "accessToken": "eyJ...",
  "refreshToken": "eyJ...",
  "user": { "id": "uuid", "role": "EMPLOYEE", "fullName": "Ravi Kumar" }
}
```
Response 401 on bad credentials, 429 if rate-limited (per A6).

---

## 2. Employees (Admin-managed)

| Method | Endpoint | Role | Description |
|---|---|---|---|
| GET | `/employees` | ADMIN | List employees, filter by `territoryId`, `isActive` |
| POST | `/employees` | ADMIN | Create employee (creates `users` + `employees` row) |
| GET | `/employees/{id}` | ADMIN | Get single employee |
| PUT | `/employees/{id}` | ADMIN | Update employee details |
| PATCH | `/employees/{id}/deactivate` | ADMIN | Soft-deactivate |
| GET | `/employees/me` | EMPLOYEE | Own profile |

---

## 3. Territories

| Method | Endpoint | Role | Description |
|---|---|---|---|
| GET | `/territories` | ADMIN | List all |
| POST | `/territories` | ADMIN | Create |
| PUT | `/territories/{id}` | ADMIN | Update |

---

## 4. Customers

| Method | Endpoint | Role | Description |
|---|---|---|---|
| GET | `/customers` | ADMIN | List, filter by `territoryId`, search by name |
| POST | `/customers` | ADMIN | Create (backend auto-geocodes address if lat/long not supplied) |
| GET | `/customers/{id}` | ADMIN, EMPLOYEE | Get single customer (employee only if assigned a visit to them) |
| PUT | `/customers/{id}` | ADMIN | Update (incl. `geofenceRadiusM` override) |
| GET | `/customers/{id}/visits` | ADMIN | Visit history for Customer Visit History report |

**`POST /customers`**
```json
// Request
{
  "name": "Sharma Traders",
  "contactNumber": "+91XXXXXXXXXX",
  "address": "123 MG Road, Lucknow",
  "geofenceRadiusM": 75
}

// Response 201
{
  "id": "uuid",
  "name": "Sharma Traders",
  "location": { "lat": 26.8467, "lng": 80.9462 },
  "geofenceRadiusM": 75
}
```

---

## 5. Visits

| Method | Endpoint | Role | Description |
|---|---|---|---|
| GET | `/visits` | ADMIN | List all, filter by `status`, `employeeId`, `dateFrom/dateTo` |
| GET | `/visits/me/today` | EMPLOYEE | Today's assigned visits (Dashboard) |
| POST | `/visits` | ADMIN | Schedule a visit |
| POST | `/visits/bulk` | ADMIN | Bulk-create recurring/multiple visits |
| GET | `/visits/{id}` | ADMIN, EMPLOYEE (own) | Visit detail |
| POST | `/visits/{id}/check-in` | EMPLOYEE (own) | Submit GPS coords for geo-verification |
| POST | `/visits/{id}/check-out` | EMPLOYEE (own) | Mark visit complete, submit final location |
| PATCH | `/visits/{id}/status` | ADMIN | Manual status override (e.g., mark MISSED) |

**`POST /visits/{id}/check-in`** — the most important endpoint in the system (backs E5)
```json
// Request
{ "latitude": 26.8467, "longitude": 80.9462, "accuracy": 12.5 }

// Response 200 (success)
{
  "visitStatus": "IN_PROGRESS",
  "verification": { "isValid": true, "distanceMeters": 18.2 }
}

// Response 422 (failed verification)
{
  "verification": { "isValid": false, "distanceMeters": 340.7, "reason": "OUTSIDE_RADIUS" }
}
```
Every call — success or failure — writes a row to `geo_verification_logs` server-side (non-negotiable, per E5/Architecture Section 4).

---

## 6. Requirement Forms

| Method | Endpoint | Role | Description |
|---|---|---|---|
| GET | `/requirement-categories` | EMPLOYEE, ADMIN | Dropdown taxonomy |
| POST | `/requirement-categories` | ADMIN | Add new category |
| POST | `/visits/{id}/requirement-form` | EMPLOYEE (own) | Submit captured requirement |
| GET | `/visits/{id}/requirement-form` | ADMIN, EMPLOYEE (own) | Retrieve submitted form |

---

## 7. Media & Signatures

| Method | Endpoint | Role | Description |
|---|---|---|---|
| POST | `/visits/{id}/media` | EMPLOYEE (own) | Upload photo/document (multipart) |
| GET | `/visits/{id}/media` | ADMIN, EMPLOYEE (own) | List attachments |
| POST | `/visits/{id}/signatures` | EMPLOYEE (own) | Upload signature image (`signatureType`: EMPLOYEE/CUSTOMER) |
| GET | `/visits/{id}/signatures` | ADMIN, EMPLOYEE (own) | Retrieve both signatures |

All uploads validated server-side for MIME type + size before hitting MinIO (per G5) — never trust client-declared type.

---

## 8. Reports & Analytics

| Method | Endpoint | Role | Description |
|---|---|---|---|
| GET | `/reports/employee-visits` | ADMIN | K1 — filter by `employeeId`, `dateFrom/dateTo` |
| GET | `/reports/customer-history` | ADMIN | K2 — filter by `customerId` |
| GET | `/reports/productivity` | ADMIN | K3 — visits/day, avg duration, distance per employee |
| GET | `/reports/geo-verification` | ADMIN | K4 — flagged/failed check-ins |
| GET | `/reports/{type}/export` | ADMIN | K6 — `?format=csv` or `?format=pdf` on any report above |

---

## 9. Notifications

| Method | Endpoint | Role | Description |
|---|---|---|---|
| GET | `/notifications/me` | Any | List own notifications, filter `isRead` |
| PATCH | `/notifications/{id}/read` | Any | Mark as read |
| POST | `/notifications/device-token` | Any | Register FCM device token |

---

## 10. Dashboard / Overview

| Method | Endpoint | Role | Description |
|---|---|---|---|
| GET | `/dashboard/overview` | ADMIN | Summary counts: active employees, visits today, flagged count |
| GET | `/dashboard/live-map` | ADMIN | Last-known check-in/check-out locations for all employees today |

---

## 11. Standard Conventions

- **Pagination:** all list endpoints accept `?page=0&size=20`, return `{ content: [...], totalElements, totalPages }`.
- **Errors:** consistent shape across all endpoints:
```json
{ "timestamp": "...", "status": 422, "error": "UNPROCESSABLE_ENTITY", "message": "...", "path": "/api/v1/visits/{id}/check-in" }
```
- **Dates:** ISO-8601 UTC everywhere (`2026-07-30T10:15:00Z`) — client (Android/React) converts to local display time.
- **Idempotency:** `POST /visits/{id}/check-in` should be safe to retry (e.g., if Android's network call times out but the request landed) — same request within a short window returns the existing result rather than double-logging. Relevant for the offline-sync retry path (I7).
- **Authorization enforcement:** every `{id}`-scoped endpoint verifies the requesting employee owns that resource (e.g., an employee can't check in to someone else's visit) — enforced in the service layer, not just route-level role checks.

---

**Next up:** Folder Structure (Phase 2.3) — turning the backend package layout from Architecture doc into the actual repo structure for both backend and frontend/Android projects.
