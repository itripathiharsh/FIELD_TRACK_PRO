# ADVERSARIAL FRAUD & ABUSE AUDIT REPORT
**Target System**: FieldTrack Pro (FastAPI Backend, PostgreSQL/PostGIS, Android Client, React Admin Web)  
**Audit Date**: August 8, 2026  
**Auditor Role**: Principal Adversarial Security & Anti-Fraud Tester  
**Status**: COMPLETE — ALL FINDINGS DOCUMENTED (NO PRODUCTION CODE MODIFIED)

---

## 1. Executive Summary

This report documents the findings of an adversarial security and business-logic fraud audit conducted against the **FieldTrack Pro** system. The objective of this audit was to act as a dishonest, lazy field sales representative attempting to receive credit for customer visits without physically performing the required field work.

The audit revealed **10 significant vulnerabilities and design gaps**, including **1 Critical Vulnerability** (Client-Reported Trust in GPS Mock Location Flag) and **4 High Severity Vulnerabilities** (Object-Level Authorization Bypass, Media Reusability without EXIF/Hash binding, Zero Dwell Time Enforcement, and Evidence-less Visit Completion).

---

## 2. Threat Model & Attacker Personas

### Primary Threat Actor: The Dishonest Field Representative
- **Motivation**: Receive visit quotas, commission, and travel reimbursements while staying at home or attending to personal errands.
- **Capabilities**: Possesses a company-issued or personal Android smartphone, valid employee JWT credentials, standard HTTP tools (cURL, Postman, Python scripts), and 10 minutes of effort.
- **Goal**: Transition assigned visit states from `PENDING` to `COMPLETED` while ensuring associated database records (`geo_verification_logs`, `visit_media`) appear valid to management.

---

## 3. Trust Boundaries & Attack Surface

```
[ Unstrusted Client Domain ]                  [ Trusted Backend Core ]
Android App / HTTP API Client --------(JWT)-------> FastAPI Router
  - User Controls Coordinates                        - Role Middleware
  - User Controls is_mock_location                   - Geo Verification Service
  - User Controls Photo Bytes                        - State Machine Guard
                                                     - PostgreSQL / PostGIS DB
```

### Critical Architectural Finding
The backend currently treats HTTP payload attributes (`is_mock_location`, `accuracy_m`, `latitude`, `longitude`) as **truthful client telemetry**. Because the backend cannot independently verify the hardware provenance of an HTTP request, any API call originating outside the official Android client can bypass client-side checks entirely.

---

## 4. Discovered Vulnerability Catalog

### CONFIRMED-VULN-01: Client-Controlled `is_mock_location` & `accuracy_m` Bypass
- **Severity**: **CRITICAL**
- **Likelihood**: **HIGH**
- **Fraud Impact**: **HIGH**
- **Affected File/Endpoint**: `app/schemas/visit.py`, `app/services/geo_verification_service.py`, `POST /api/v1/visits/{id}/check-in`
- **Classification**: **CONFIRMED**
- **Preconditions**: Authenticated `EMPLOYEE` JWT.
- **Technical Description**: `CheckInRequest` and `CheckOutRequest` models define `is_mock_location: bool = False` and `accuracy_m: float | None = None`. In `GeoVerificationService.verify_location`, mock detection logic relies directly on `if is_mock_location: return GeoVerificationResult(is_valid=False, ...)`:

```python
# app/services/geo_verification_service.py (Lines 89-90)
if is_mock_location:
    return GeoVerificationResult(is_valid=False, ...)
```

If a dishonest representative sends a raw JSON POST payload directly to `/api/v1/visits/{visit_id}/check-in`:
```json
{
  "latitude": 12.9716,
  "longitude": 77.5946,
  "accuracy_m": 5.0,
  "is_mock_location": false
}
```
The server calculates Haversine distance as `0.0 meters`, accepts `is_mock_location=false`, and records a valid check-in event, even if the representative is physically located in another city.
- **Remediation Direction**: Implement server-side cell tower / IP geolocation cross-referencing, device telemetry signing, or trusted hardware attestation (e.g. SafetyNet / Play Integrity API).

---

### CONFIRMED-VULN-02: Object-Level Authorization (IDOR) Gap in Visit Roster Access
- **Severity**: **HIGH**
- **Likelihood**: **HIGH**
- **Fraud Impact**: **MEDIUM**
- **Affected File/Endpoint**: `app/api/v1/visits.py` (`list_visits` & `get_visit`)
- **Classification**: **CONFIRMED**
- **Preconditions**: Authenticated `EMPLOYEE` JWT.
- **Technical Description**: The routes `GET /api/v1/visits` and `GET /api/v1/visits/{visit_id}` use `dependencies=[AnyAuth]`:

```python
# app/api/v1/visits.py (Lines 43-51)
@router.get("", response_model=list[VisitRead], dependencies=[AnyAuth])
async def list_visits(...):
    return await visit_service.list_visits(session, employee_id, status, skip, limit)
```

When an employee calls `GET /api/v1/visits`, the backend returns all visits assigned to **all employees** in the database. An employee can inspect customer coordinates, scheduled times, and visit IDs belonging to colleagues.

---

### CONFIRMED-VULN-03: Photo Reusability & Complete Absence of EXIF / Perceptual Hash Binding
- **Severity**: **HIGH**
- **Likelihood**: **HIGH**
- **Fraud Impact**: **HIGH**
- **Affected File/Endpoint**: `app/services/file_validation_service.py`, `POST /api/v1/visits/{id}/media`
- **Classification**: **CONFIRMED**
- **Preconditions**: Authenticated `EMPLOYEE` JWT.
- **Technical Description**: `FileValidationService.validate_and_inspect` performs magic-byte inspection (`\xFF\xD8\xFF` for JPEG, `\x89PNG` for PNG) and size verification. However:
  1. The server **does not extract EXIF metadata** (Camera capture timestamp, EXIF GPS coordinates).
  2. The server **does not check for duplicate file checksums (SHA-256)** across visits.
  3. The server **does not compute perceptual hashes (pHash)** to detect cropped, recompressed, or screenshot images.
- **Fraud Scenario**: A representative saves a generic photo of a building on their phone and uploads the exact same JPEG file to 50 different customer visits across 30 days. All 50 uploads pass validation and are stored as valid media evidence.

---

### CONFIRMED-VULN-04: Zero Minimum Visit Duration Enforcement (Instant Check-In/Check-Out)
- **Severity**: **HIGH**
- **Likelihood**: **HIGH**
- **Fraud Impact**: **HIGH**
- **Affected File/Endpoint**: `app/services/visit_service.py` (`check_out`)
- **Classification**: **CONFIRMED**
- **Preconditions**: Authenticated `EMPLOYEE` JWT.
- **Technical Description**: `check_out` verifies state transition from `IN_PROGRESS` to `COMPLETED` via `assert_valid_transition`. However, it does not calculate `check_out_at - check_in_at`. A representative can issue a check-in request at `10:00:00 AM` and a check-out request at `10:00:01 AM` (1 second later). The visit transitions to `COMPLETED` without any check on minimal dwell time at the customer site.

---

### CONFIRMED-VULN-05: Check-Out Execution Without Inspection Evidence or Form Submission
- **Severity**: **HIGH**
- **Likelihood**: **HIGH**
- **Fraud Impact**: **HIGH**
- **Affected File/Endpoint**: `app/services/visit_service.py` (`check_out`)
- **Classification**: **CONFIRMED**
- **Preconditions**: Authenticated `EMPLOYEE` JWT.
- **Technical Description**: `check_out` does not verify whether any media records exist in `visit_media` or whether any requirement forms were completed. A representative can check in and check out without uploading a single photo or answering a single checklist question, leaving the visit in a `COMPLETED` state with zero supporting evidence.

---

### CONFIRMED-VULN-06: Absence of Scheduled Visit Window Enforcement
- **Severity**: **MEDIUM**
- **Likelihood**: **MEDIUM**
- **Fraud Impact**: **MEDIUM**
- **Affected File/Endpoint**: `app/services/visit_service.py` (`check_in`)
- **Classification**: **CONFIRMED**
- **Preconditions**: Authenticated `EMPLOYEE` JWT.
- **Technical Description**: `check_in` does not compare `datetime.now(tz=timezone.utc)` against `visit.scheduled_at`. A representative can check in to a visit scheduled for next month or three weeks ago, allowing off-schedule visit completion without administrative approval.

---

### CONFIRMED-VULN-07: Offline Queue Payload Manipulation
- **Severity**: **MEDIUM**
- **Likelihood**: **MEDIUM**
- **Fraud Impact**: **MEDIUM**
- **Affected File/Endpoint**: Android `OfflineQueueManager`
- **Classification**: **LIKELY**
- **Preconditions**: Access to Android device local storage or rooted device.
- **Technical Description**: Offline action items are stored as JSON files or SharedPreferences on the device. An employee can modify the cached JSON payload (altering latitude, longitude, or timestamp) prior to toggling airplane mode off, forcing the app to sync fabricated telemetry once network connectivity resumes.

---

### CONFIRMED-VULN-08: Media Storage Guessable Key Enumeration
- **Severity**: **MEDIUM**
- **Likelihood**: **LOW**
- **Fraud Impact**: **MEDIUM**
- **Affected File/Endpoint**: `app/services/file_validation_service.py` (`generate_storage_key`)
- **Classification**: **CONFIRMED**
- **Preconditions**: Authenticated user.
- **Technical Description**: Storage keys follow the deterministic format `visits/{visit_id}/{media_id}_{sanitized_name}`. If storage provider permissions are misconfigured or presigned URLs are exposed, knowing the `visit_id` and `media_id` allows direct binary download.

---

### CONFIRMED-VULN-09: Race Condition on Concurrent Check-In Requests
- **Severity**: **MEDIUM**
- **Likelihood**: **LOW**
- **Fraud Impact**: **LOW**
- **Affected File/Endpoint**: `app/services/visit_service.py` (`check_in`)
- **Classification**: **CONFIRMED**
- **Preconditions**: Concurrent HTTP POST requests.
- **Technical Description**: `check_in` reads `visit.status` before acquiring a database row lock (`with_for_update`). Simultaneous check-in requests sent at the exact same millisecond can create duplicate entries in `geo_verification_logs` before the first transaction commits the `IN_PROGRESS` status update.

---

### CONFIRMED-VULN-10: Lack of Rate Limiting on Authentication Endpoints
- **Severity**: **LOW**
- **Likelihood**: **HIGH**
- **Fraud Impact**: **MEDIUM**
- **Affected File/Endpoint**: `app/api/v1/auth.py` (`POST /api/v1/auth/login`)
- **Classification**: **CONFIRMED**
- **Preconditions**: None.
- **Technical Description**: The login endpoint does not incorporate rate-limiting middleware (such as `slowapi`). An attacker or automated script can execute thousands of password attempts per minute against employee accounts.

---

## 5. System Abuse & Fraud Matrix

| Attack Category | Specific Fraud Scenario | Status | Vulnerability Ref |
| :--- | :--- | :---: | :---: |
| **GPS Verification** | Direct API call sending fake coordinates & `is_mock_location=false` | **CONFIRMED** | CONFIRMED-VULN-01 |
| **Authorization** | Employee listing all visits across all representatives | **CONFIRMED** | CONFIRMED-VULN-02 |
| **Media Management** | Uploading same JPEG photo across multiple visits | **CONFIRMED** | CONFIRMED-VULN-03 |
| **Visit Dwell Time** | Completing visit in 1 second (Instant check-in/out) | **CONFIRMED** | CONFIRMED-VULN-04 |
| **Evidence Binding** | Completing visit without uploading any photos or forms | **CONFIRMED** | CONFIRMED-VULN-05 |
| **Schedule Control** | Checking in to visits scheduled in the distant past/future | **CONFIRMED** | CONFIRMED-VULN-06 |
| **Offline Mode** | Modifying queued JSON payload prior to synchronization | **LIKELY** | CONFIRMED-VULN-07 |
| **Storage Security** | Accessing storage keys via predictable paths | **CONFIRMED** | CONFIRMED-VULN-08 |
| **Concurrency** | Concurrent check-in requests causing duplicate geo logs | **CONFIRMED** | CONFIRMED-VULN-09 |
| **Auth Security** | Automated brute-force credential attacks on `/auth/login` | **CONFIRMED** | CONFIRMED-VULN-10 |

---

## 6. Recommended Remediation Roadmap (Phase 10+)

1. **Enforce Hardware Attestation & Eliminate Client Trust of `is_mock_location`**:
   - Do not accept `is_mock_location` as a trusted boolean from the client JSON payload.
   - Require Android Play Integrity attestation tokens for check-in requests.
2. **Implement Object-Level Ownership Filtering (IDOR Protection)**:
   - Restrict `GET /api/v1/visits` for `EMPLOYEE` role to return ONLY visits where `visit.employee_id == current_employee.id`.
3. **Enforce EXIF Extraction, Hash Deduplication & Perceptual Hashing**:
   - Extract EXIF timestamp and EXIF GPS metadata server-side; reject photos whose EXIF GPS coordinates differ from the customer site or whose creation time is outside the visit window.
   - Compute pHash and SHA-256 checksums to reject duplicate photo submissions across visits.
4. **Mandate Minimum Dwell Time & Evidence Checks on Check-Out**:
   - Require `check_out_at - check_in_at >= 5 minutes` (or configured threshold).
   - Reject check-out requests if `visit_media` count is zero or required forms are incomplete.
5. **Enforce Scheduled Time Windows**:
   - Reject check-in attempts outside `[scheduled_at - 1 hour, scheduled_at + 4 hours]`.
6. **Implement Rate Limiting**:
   - Add `slowapi` rate limiting to `/api/v1/auth/login` (e.g. 5 attempts per minute per IP).

---

## 7. Final Declaration

This audit was conducted strictly in accordance with adversarial testing guidelines. **No production or application source code was modified during this phase.**

**PHASE 9 — COMPLETE**
