# Project Context & Rules: FieldTrack Pro

## ⚠️ Core Rule: Automated / Test Data vs Production Data

**Automated / Test Data MUST NOT be kept in the final production push.**
Whenever we push to final production, all automated test entities will be cleaned/deleted:
- Automated Writeback Reps (`REP-*` / `emp_wb_*@fieldtrack.test`)
- Automated Writeback Outlets (`UPDDC10FEF`, etc.)
- Mock / Automated Test Visits
- GPS Mock Check-in Outlets (`CURR-GPS-001`)

**ONLY Real Client Data will remain in Production:**
- The **30 Real SGRG Staff Members** (employee codes `11001` to `11030`)
- The **1,631+ Real Client Outlets** (with real UPDD codes from Tally and BI Ledger)
- The **55 Territories & 465 Areas**
- The **Real Tally Invoices & Vouchers** (1.5 years of financial transactions)

## 📌 Roles & Data Visibility
Three application roles exist: `SUPER_ADMIN`, `ADMIN` and `EMPLOYEE`. There is no MANAGER role. `SUPER_ADMIN` is a strict superset of `ADMIN` that additionally manages roles (see `field track pro/fieldtrackpro-backend/ADMIN_SECURITY.md`); it is never created by signup, user creation or import.

- **SUPER_ADMIN**: Everything an ADMIN can do, plus role management (promote/demote, with re-authentication) and protected account operations.
- **ADMIN**: Global access to all master lists (all 30 employees, 55 territories, 1,650 outlets, customer requirements across all outlets, aging reports).
- **EMPLOYEE**: Restricted to their own profile, assigned customers, assigned daily visits, and customer requirements submitted by themselves.
