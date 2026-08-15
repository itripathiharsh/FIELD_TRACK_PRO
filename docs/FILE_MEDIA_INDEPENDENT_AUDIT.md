# File & Media Module - Independent Forensic Audit

**Date:** 2026-08-09
**Auditor:** Independent forensic verification
**Scope:** Complete File & Media module (G1-G5, FR-15, FR-16)

---

## 1. Executive Summary

The File & Media module is **INCOMPLETE**. While significant infrastructure exists
(media upload/download, signature capture UI, storage abstraction), several
**mandatory** requirements from the planning documents are missing or incorrectly
implemented.

**Critical defects:**
1. **Image compression is MANDATORY but NOT IMPLEMENTED** (Phase 5 doc Section 2)
2. **Pre-signed URLs are MANDATORY but NOT IMPLEMENTED** (Phase 5 doc Section 6, Security Design Section 4)
3. **Separate document upload endpoint MISSING** (Phase 5 doc Section 3)
4. **Android WorkManager for uploads MISSING** (Phase 6 doc Section 7)
5. **python-magic validation MISSING** (Phase 5 doc Section 5)

---

## 2. Source Documents Audited

| Document | Path |
|----------|------|
| Requirements | `guides/phase 1/01_requirements.md` |
| Features | `guides/phase 1/03_features.md` |
| Security Design | `guides/phase 2/09_security_design.md` |
| API Design | `guides/phase 2/07_api_design.md` |
| Business Logic | `guides/phase3/19_business_logic.md` |
| File & Media Management | `guides/phase 5/22_file_media_management.md` |
| Android Application | `guides/phase 6/23_android_application.md` |
| Android Screen List | `guides/Phase 2.5/11_android_screen_list.md` |
| User Journey | `guides/Phase 2.5/13_user_journey.md` |
| Repair Closure Report | `docs/REPAIR_CLOSURE_REPORT.md` |
| Gap Analysis | `docs/FILE_MEDIA_GAP_ANALYSIS.md` |
| Completion Report | `docs/FILE_MEDIA_COMPLETION_REPORT.md` |

---

## 3. Requirement Inventory

### Module G Requirements (from 03_features.md)
- G1: Image upload endpoint + storage (MinIO)
- G2: Document upload endpoint + storage
- G3: Digital signature capture component (Android canvas)
- G4: Signature storage as image, linked to visit record
- G5: File size/type validation + compression before upload

### Functional Requirements (from 01_requirements.md)
- FR-15: Employee can attach photos and documents to a visit record
- FR-16: Employee can capture both customer and employee digital signatures at visit completion

### Security Requirements (from 09_security_design.md)
- Section 4: Signatures/photos access ONLY via pre-signed URLs
- Section 5: Magic-byte validation, server-generated storage keys, size limits
- Section 6: Parameterized queries, no raw paths

---

## 4. Requirement Traceability Matrix

| ID | Requirement | Source | Backend | DB | Storage | Android | Tests | Status |
|----|-------------|--------|---------|----|---------|---------|-------|--------|
| G1.1 | Image upload endpoint | 03_features.md G1 | YES | YES | YES | YES | NO | PARTIALLY_VERIFIED |
| G1.2 | Image compression (MANDATORY) | 022_file_media S2 | **NO** | N/A | N/A | N/A | NO | **MISSING** |
| G1.3 | Pre-signed URL access | 022_file_media S6 | **NO** | N/A | **NO** | N/A | NO | **MISSING** |
| G2.1 | Document upload endpoint | 03_features.md G2 | PARTIAL | YES | YES | YES | NO | PARTIALLY_VERIFIED |
| G2.2 | Document type validation (PDF/DOC) | 022_file_media S3 | PARTIAL | N/A | N/A | N/A | NO | PARTIALLY_VERIFIED |
| G3.1 | Signature capture (Android canvas) | 03_features.md G3 | N/A | N/A | N/A | YES | NO | PARTIALLY_VERIFIED |
| G4.1 | Signature storage linked to visit | 03_features.md G4 | YES | YES | YES | YES | NO | PARTIALLY_VERIFIED |
| G4.2 | Signature uniqueness per visit | 022_file_media S4 | YES | YES | N/A | N/A | NO | VERIFIED |
| G5.1 | File size validation | 03_features.md G5 | YES | N/A | N/A | N/A | NO | VERIFIED |
| G5.2 | Magic-byte validation | 03_features.md G5 | PARTIAL | N/A | N/A | N/A | NO | PARTIALLY_VERIFIED |
| FR-15 | Photo/document attachment | 01_FR-15 | YES | YES | YES | YES | NO | PARTIALLY_VERIFIED |
| FR-16 | Digital signatures | 01_FR-16 | YES | YES | YES | YES | NO | PARTIALLY_VERIFIED |
| SEC-4 | Pre-signed URL only access | 09_security S4 | **NO** | N/A | **NO** | N/A | NO | **MISSING** |
| SEC-5 | Server-generated storage keys | 09_security S5 | YES | N/A | N/A | N/A | NO | VERIFIED |

---

## 5. Backend Audit

### Routes

| Endpoint | Required | Actual | Match |
|----------|----------|--------|-------|
| POST /visits/{id}/media | YES | YES | YES |
| GET /visits/{id}/media | YES | YES | YES |
| GET /media/{id} | YES | YES | YES |
| GET /media/{id}/download | Pre-signed URL | Direct bytes | **NO** |
| DELETE /media/{id} | YES | YES | YES |
| POST /visits/{id}/signatures | YES | YES | YES |
| GET /visits/{id}/signatures | YES | YES | YES |
| GET /signatures/{id}/download | Pre-signed URL | Direct bytes | **NO** |

### Services

**Media Service:**
- Validation: Magic bytes present but uses hardcoded prefixes, not python-magic
- Compression: **NOT IMPLEMENTED** (mandatory per Phase 5 Section 2)
- Storage key generation: Server-generated UUID - VERIFIED
- Ownership check: VERIFIED (via get_visit_for_user)
- Duplicate detection: VERIFIED (checksum constraint)
- Pre-signed URL: **NOT IMPLEMENTED**

**Signature Service:**
- Base64 decoding: VERIFIED
- Magic bytes validation: VERIFIED
- Size limit: VERIFIED (1MB)
- Uniqueness check: VERIFIED
- Storage: VERIFIED
- No compression: VERIFIED (correct per spec)

### Schemas

**MediaRead:** VERIFIED - all fields present
**SignatureCreate/Read:** VERIFIED - all fields present

---

## 6. Database Audit

### Tables

| Table | Exists | Columns Match | Constraints | Status |
|-------|--------|---------------|-------------|--------|
| visit_media | YES | YES | uq_visit_media_content | VERIFIED |
| visit_signatures | YES | YES | uq_visit_signature | VERIFIED |

### Migrations
Both tables created via Alembic migrations. No issues found.

---

## 7. MinIO/Storage Audit

| Feature | Required | Actual | Status |
|---------|----------|--------|--------|
| MinIO provider | YES | YES | VERIFIED |
| Local provider | YES (dev) | YES | VERIFIED |
| Bucket auto-create | YES | YES | VERIFIED |
| Upload | YES | YES | VERIFIED |
| Download | YES | YES | VERIFIED |
| Delete | YES | YES | VERIFIED |
| Pre-signed URL generation | **MANDATORY** | **NOT IMPLEMENTED** | **MISSING** |
| 15-min URL expiry | **MANDATORY** | **NOT IMPLEMENTED** | **MISSING** |

---

## 8. Security Audit

| Control | Required | Actual | Status |
|---------|----------|--------|--------|
| Magic-byte validation | YES | Hardcoded prefixes (not python-magic) | PARTIALLY_VERIFIED |
| File size limit (images 10MB) | YES | YES (10MB) | VERIFIED |
| File size limit (docs 20MB) | YES | **NO** (uses same 10MB limit) | **FAILED** |
| Server-generated storage keys | YES | YES | VERIFIED |
| No client-controlled paths | YES | YES | VERIFIED |
| Ownership validation | YES | YES | VERIFIED |
| Pre-signed URL access | **MANDATORY** | Direct byte streaming | **FAILED** |
| Cross-employee access prevention | YES | YES (via get_visit_for_user) | VERIFIED |

---

## 9. Android Audit

| Feature | Required | Actual | Status |
|---------|----------|--------|--------|
| Camera capture | YES | YES (ActivityResultContracts) | NOT_RUNTIME_VERIFIED |
| Photo picker | YES | YES (GetContent) | NOT_RUNTIME_VERIFIED |
| Document picker | YES | YES (GetContent PDF) | NOT_RUNTIME_VERIFIED |
| FileProvider | YES | YES | VERIFIED |
| Camera permission | YES | YES | VERIFIED |
| READ_MEDIA_IMAGES permission | YES | YES | VERIFIED |
| WorkManager for uploads | **MANDATORY** | **Direct coroutine** | **MISSING** |
| Signature canvas | YES | YES | NOT_RUNTIME_VERIFIED |
| Signature clear/retry | YES | YES | VERIFIED |
| Attachment Preview screen | YES (Screen 13) | **NOT IMPLEMENTED** | **MISSING** |
| Upload retry on failure | YES | **NO** | **MISSING** |

---

## 10. Signature Audit

| Feature | Required | Actual | Status |
|---------|----------|--------|--------|
| Employee signature | YES | YES | PARTIALLY_VERIFIED |
| Customer signature | YES | YES | PARTIALLY_VERIFIED |
| Canvas drawing | YES | YES | NOT_RUNTIME_VERIFIED |
| PNG export | YES | YES | VERIFIED |
| Base64 encoding | YES | YES | VERIFIED |
| No compression | YES | YES | VERIFIED |
| Uniqueness per visit type | YES | YES | VERIFIED |
| Visit association | YES | YES | VERIFIED |
| Download capability | YES | YES (direct bytes) | PARTIALLY_VERIFIED |

---

## 11. Compression Audit

**REQUIRED:** Phase 5 doc Section 2 states: "Compression is mandatory, not optional"

**Implementation:** NO compression is performed on uploaded images.

**Required behavior:**
- Max dimension: 1920px
- Quality: 80%
- Format: JPEG
- Preserve aspect ratio

**Actual behavior:**
- Raw bytes stored as-is
- No Pillow/PIL processing

**Status: MISSING**

**Impact:** Field employees uploading 5-8MB photos from modern phones will
experience slow uploads and high storage costs, directly contradicting the
documented usability targets.

---

## 12. Pre-signed URL Audit

**REQUIRED:** Phase 5 doc Section 6 states: "No direct MinIO URLs ever exposed
to clients -- every file access goes through GET /visits/{id}/media or
/signatures, which returns short-lived (15-minute) pre-signed URLs"

Security Design Section 4 states: "Signatures and photos: stored in MinIO, access
only via backend-issued pre-signed URLs with short expiry -- never expose MinIO
directly to clients"

**Implementation:** Direct byte streaming endpoints that read from MinIO and
return raw bytes.

**Status: MISSING (SECURITY ISSUE)**

**Impact:**
- Backend becomes a bandwidth bottleneck
- No URL expiry control
- Cannot revoke access without changing storage keys
- Does not match approved security architecture

---

## 13. API Contract Audit

### Endpoint Path Mismatches

| Planning Spec | Actual | Match |
|---------------|--------|-------|
| POST /visits/{id}/media | POST /api/v1/visits/{id}/media | YES |
| GET /visits/{id}/media | GET /api/v1/visits/{id}/media | YES |
| GET /media/{id}/download (pre-signed) | GET /api/v1/media/{id}/download (bytes) | **NO** |
| POST /visits/{id}/signatures | POST /api/v1/visits/{id}/signatures | YES |
| GET /signatures/{id}/download (pre-signed) | GET /api/v1/signatures/{id}/download (bytes) | **NO** |

### Android DTO vs Backend Schema

| Backend Field | Android DTO Field | Match |
|---------------|-------------------|-------|
| id | id | YES |
| visit_id | visitId | YES |
| media_type | mediaType | YES |
| storage_key | storageKey | YES |
| file_size_bytes | fileSizeBytes | YES |
| checksum_sha256 | checksumSha256 | YES |
| original_filename | originalFilename | YES |
| uploaded_by | uploadedBy | YES |
| uploaded_at | uploadedAt | YES |

---

## 14. Test Quality Audit

### What is tested:
- SignatureDto field mapping (3 tests)
- SignatureCaptureState path tracking (4 tests)
- Existing media model tests (from repair phase)

### What is NOT tested:
- Image upload with real file bytes
- Image compression (not implemented)
- Pre-signed URL generation (not implemented)
- File validation with magic bytes (real files)
- File size limit enforcement
- Duplicate detection with real files
- Signature upload with real image data
- Cross-employee access prevention
- Document type validation (PDF/DOC specific)
- Android upload flow (camera/picker)
- Signature uniqueness enforcement
- Storage failure handling
- Orphan cleanup

**Test coverage for File & Media: INSUFFICIENT**

---

## 15. Runtime/E2E Audit

| Flow | Status |
|------|--------|
| Photo upload (Android -> API -> MinIO -> DB) | NOT_RUNTIME_VERIFIED |
| Document upload | NOT_RUNTIME_VERIFIED |
| Signature capture and upload | NOT_RUNTIME_VERIFIED |
| Unauthorized cross-employee access | NOT_RUNTIME_VERIFIED |
| Invalid file rejection | NOT_RUNTIME_VERIFIED |
| Oversized file rejection | NOT_RUNTIME_VERIFIED |

No runtime testing was performed (this is an audit-only task).

---

## 16. Fabricated Functionality Audit

| Search Term | Production Hits | Test Hits | Status |
|-------------|-----------------|-----------|--------|
| demo | 0 | 0 | CLEAN |
| fake | 0 | 0 | CLEAN |
| sample | 0 | 0 | CLEAN |
| placeholder | 0 | 0 | CLEAN |
| hardcoded JPEG | 0 | 0 | CLEAN |
| sampleJpegBytes | 0 | 0 | CLEAN (removed) |

**Status: CLEAN** - No fabricated functionality found in production code.

---

## 17. Duplicate Implementation Audit

| Functionality | Implementations | Status |
|---------------|-----------------|--------|
| Media upload | 1 (media_service) | OK |
| Signature upload | 1 (signature_service) | OK |
| Storage | 2 (local + minio) | OK (intentional) |
| File validation | 1 (file_validation_service) | OK |
| Android media picker | 1 | OK |
| Android signature capture | 1 | OK |

**Status: NO DUPLICATION**

---

## 18. Defects Found

### Critical

| # | Defect | Source Reference | Impact |
|---|--------|------------------|--------|
| D1 | Image compression not implemented | Phase 5 S2: "mandatory, not optional" | Slow uploads, high storage cost |
| D2 | Pre-signed URLs not implemented | Phase 5 S6, Security S4 | Security architecture violation |
| D3 | Document size limit not enforced (20MB) | Phase 5 S3 | Spec non-compliance |
| D4 | Android WorkManager for uploads missing | Phase 6 S7 | No retry on poor networks |

### High

| # | Defect | Source Reference | Impact |
|---|--------|------------------|--------|
| D5 | python-magic validation not used | Phase 5 S5 | Weaker file validation |
| D6 | Attachment Preview screen missing | Android Screen List #13 | Incomplete Android flow |
| D7 | Media upload reads entire file into memory | Best practice | OOM risk for large files |
| D8 | No pre-signed URL generation method | Phase 5 S1 | Core feature missing |

### Medium

| # | Defect | Source Reference | Impact |
|---|--------|------------------|--------|
| D9 | Separate document upload endpoint not implemented | Phase 5 S3 | All uploads use same endpoint |
| D10 | Signature download returns direct bytes not pre-signed URL | Phase 5 S6 | Inconsistent with media |
| D11 | No upload retry mechanism in Android | Phase 6 S7 | Poor network resilience |

---

## 19. Missing Requirements

| ID | Requirement | Source | Status |
|----|-------------|--------|--------|
| M1 | Image compression (1920px, quality 80) | Phase 5 S2 | MISSING |
| M2 | Pre-signed URL generation | Phase 5 S1, S6 | MISSING |
| M3 | Pre-signed URL download endpoints | Phase 5 S6 | MISSING |
| M4 | python-magic file validation | Phase 5 S5 | MISSING |
| M5 | Separate document upload endpoint | Phase 5 S3 | MISSING |
| M6 | 20MB document size limit | Phase 5 S3 | MISSING |
| M7 | Android WorkManager upload | Phase 6 S7 | MISSING |
| M8 | Attachment Preview screen | Android Screen #13 | MISSING |
| M9 | Upload retry with backoff | Phase 6 S7 | MISSING |
| M10 | Signature type validation (EMPLOYEE/CUSTOMER explicit) | Phase 5 S4 | MISSING |

---

## 20. Deferred Requirements

None. The completion report did not defer any mandatory requirements.

---

## 21. Exact Required Fixes

### Fix D1: Image Compression
- Add Pillow dependency
- Implement `compress_image()` function in media_service.py
- Apply compression before storage for PHOTO type
- Max dimension: 1920px, quality: 80%, format: JPEG

### Fix D2/D3: Pre-signed URLs
- Add `generate_presigned_url(storage_key, expiry_minutes=15)` to storage_service
- Modify download endpoints to return redirect to pre-signed URL
- Update Android to handle URL redirects

### Fix D4: Android WorkManager
- Create SignatureUploadWorker and MediaUploadWorker
- Use WorkManager for all upload operations
- Implement retry with exponential backoff

### Fix D5: python-magic
- Add python-magic dependency
- Replace hardcoded magic bytes with magic.from_buffer()

### Fix D6: Attachment Preview Screen
- Create AttachmentPreviewScreen composable
- Show full-screen image/document before/after upload

---

## 22. Final Status

### Verification Totals

| Status | Count |
|--------|-------|
| **VERIFIED** | 8 |
| **PARTIALLY_VERIFIED** | 10 |
| **MISSING** | 10 |
| **FAILED** | 2 |
| **DEFERRED** | 0 |
| **NOT_APPLICABLE** | 0 |
| **NOT_RUNTIME_VERIFIED** | 5 |

### Final Classification: **INCOMPLETE**

The File & Media module has significant infrastructure but is missing
mandatory features required by the planning documents. Specifically:

1. **Image compression is mandatory** (Phase 5 S2) but not implemented
2. **Pre-signed URLs are mandatory** (Phase 5 S6, Security S4) but not implemented
3. **Android WorkManager uploads** are specified (Phase 6 S7) but not implemented
4. **python-magic validation** is specified (Phase 5 S5) but not implemented

The module should NOT be considered complete until these mandatory
requirements are implemented and verified.

---

## Final Verification Table

| Requirement | Status | Evidence | Problem | Required Action |
|-------------|--------|----------|---------|-----------------|
| G1: Image upload | PARTIALLY_VERIFIED | Endpoint exists, storage works | No compression | Add Pillow compression |
| G1.2: Compression | **MISSING** | Not in code | Mandatory per Phase 5 S2 | Implement compress_image() |
| G2: Document upload | PARTIALLY_VERIFIED | Uses same endpoint as images | No separate endpoint/type | Create document-specific flow |
| G3: Signature capture | PARTIALLY_VERIFIED | Canvas component exists | Not runtime tested | Device testing needed |
| G4: Signature storage | PARTIALLY_VERIFIED | Backend + DB complete | Download uses bytes not URL | Implement pre-signed URLs |
| G5: File validation | PARTIALLY_VERIFIED | Hardcoded magic bytes | python-magic not used | Add python-magic dependency |
| FR-15: Photo attachment | PARTIALLY_VERIFIED | Android picker exists | No WorkManager retry | Add WorkManager |
| FR-16: Signatures | PARTIALLY_VERIFIED | Full flow exists | No pre-signed URL download | Implement pre-signed URLs |
| SEC-4: Pre-signed URLs | **FAILED** | Direct byte streaming | Security architecture violated | Implement pre-signed URL service |
| SEC-5: Storage keys | VERIFIED | Server-generated UUID | None | None |
| SEC-5: Magic bytes | PARTIALLY_VERIFIED | Hardcoded prefixes | python-magic not used | Add python-magic |
| Android: Camera | NOT_RUNTIME_VERIFIED | Code exists | No device testing | Physical device test |
| Android: WorkManager | **MISSING** | Direct coroutine upload | No retry on failure | Implement WorkManager |
| Android: Preview screen | **MISSING** | Not implemented | Screen #13 missing | Create preview screen |
| Tests: Media upload | **MISSING** | No tests | No validation | Add integration tests |
| Tests: Signature upload | **MISSING** | No tests | No validation | Add integration tests |

---

**AUDIT CONCLUSION:** The File & Media module is **NOT COMPLETE**.
Mandatory requirements M1 (compression) and M2-M3 (pre-signed URLs) must be
implemented before this module can be considered production-ready.
