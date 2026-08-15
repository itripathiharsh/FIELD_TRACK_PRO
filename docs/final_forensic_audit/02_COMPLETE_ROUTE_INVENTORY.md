# Final Forensic Audit — Complete Route Inventory

**Date:** 2026-08-09
**Source:** FastAPI OpenAPI schema (actual registered routes)

---

## Route Summary

| Category | Count |
|----------|-------|
| Total routes | 43 |
| Open (no auth) | 7 |
| Authenticated | 36 |
| Auth routes | 4 |
| User routes | 5 |
| Employee routes | 4 |
| Customer routes | 4 |
| Territory routes | 5 |
| Visit routes | 11 |
| Geo routes | 1 |
| Media routes | 3 |
| Signature routes | 1 |
| Health routes | 3 |

---

## Complete Route Inventory

### Auth Routes

| Method | Path | Auth | Summary |
|--------|------|------|---------|
| POST | /api/v1/auth/login | OPEN | Login |
| POST | /api/v1/auth/logout | OPEN | Logout |
| GET | /api/v1/auth/me | AUTH | Current user |
| POST | /api/v1/auth/refresh | OPEN | Refresh token |

### User Routes

| Method | Path | Auth | Summary |
|--------|------|------|---------|
| POST | /api/v1/users | AUTH | Create user |
| GET | /api/v1/users/{user_id} | AUTH | Get user |
| PATCH | /api/v1/users/{user_id}/activate | AUTH | Activate user |
| PATCH | /api/v1/users/{user_id}/deactivate | AUTH | Deactivate user |
| PATCH | /api/v1/users/me/password | AUTH | Change password |

### Employee Routes

| Method | Path | Auth | Summary |
|--------|------|------|---------|
| GET | /api/v1/employees | AUTH | List employees |
| POST | /api/v1/employees | AUTH | Create employee |
| GET | /api/v1/employees/me | AUTH | Current employee |
| GET | /api/v1/employees/{employee_id} | AUTH | Get employee |

### Customer Routes

| Method | Path | Auth | Summary |
|--------|------|------|---------|
| GET | /api/v1/customers | AUTH | List customers |
| POST | /api/v1/customers | AUTH | Create customer |
| GET | /api/v1/customers/{customer_id} | AUTH | Get customer |
| PATCH | /api/v1/customers/{customer_id} | AUTH | Update customer |

### Territory Routes

| Method | Path | Auth | Summary |
|--------|------|------|---------|
| GET | /api/v1/territories | AUTH | List territories |
| POST | /api/v1/territories | AUTH | Create territory |
| GET | /api/v1/territories/{territory_id} | AUTH | Get territory |
| PATCH | /api/v1/territories/{territory_id} | AUTH | Update territory |
| DELETE | /api/v1/territories/{territory_id} | AUTH | Delete territory |

### Visit Routes

| Method | Path | Auth | Summary |
|--------|------|------|---------|
| GET | /api/v1/visits | AUTH | List visits |
| POST | /api/v1/visits | AUTH | Create visit |
| GET | /api/v1/visits/me/today | AUTH | Today's visits |
| GET | /api/v1/visits/{visit_id} | AUTH | Get visit |
| POST | /api/v1/visits/{visit_id}/check-in | AUTH | Check in |
| POST | /api/v1/visits/{visit_id}/check-out | AUTH | Check out |
| GET | /api/v1/visits/{visit_id}/geo-logs | AUTH | Geo logs |
| GET | /api/v1/visits/{visit_id}/media | AUTH | List media |
| POST | /api/v1/visits/{visit_id}/media | AUTH | Upload media |
| GET | /api/v1/visits/{visit_id}/signatures | AUTH | List signatures |
| POST | /api/v1/visits/{visit_id}/signatures | AUTH | Upload signature |
| PATCH | /api/v1/visits/{visit_id}/status | AUTH | Force status |

### Geo Routes

| Method | Path | Auth | Summary |
|--------|------|------|---------|
| POST | /api/v1/geo/verify-location | AUTH | Verify location |

### Media Routes

| Method | Path | Auth | Summary |
|--------|------|------|---------|
| GET | /api/v1/media/{media_id} | AUTH | Get metadata |
| GET | /api/v1/media/{media_id}/download | AUTH | Download (pre-signed URL) |
| DELETE | /api/v1/media/{media_id} | AUTH | Delete |

### Signature Routes

| Method | Path | Auth | Summary |
|--------|------|------|---------|
| GET | /api/v1/signatures/{signature_id}/download | AUTH | Download |

### Health Routes

| Method | Path | Auth | Summary |
|--------|------|------|---------|
| GET | /health | OPEN | Root health |
| GET | /api/v1/health | OPEN | API health |
| GET | /api/v1/health/db | OPEN | DB health |

---

## Security Scheme

- **Type:** HTTPBearer (JWT)
- **Header:** Authorization: Bearer <token>
