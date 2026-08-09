# File & Media Module - Repair Plan

**Date:** 2026-08-09
**Based on:** docs/FILE_MEDIA_INDEPENDENT_AUDIT.md
**Source of truth:** Original planning documents

---

## Requirement Reconciliation

### D1 - Image Compression

| Field | Value |
|-------|-------|
| **Audit Finding** | Image compression not implemented |
| **Source Document** | `guides/phase 5/22_file_media_management.md` Section 2 |
| **Source Quote** | "Compression is mandatory, not optional" |
| **Required Spec** | max_dimension=1920, quality=80, JPEG, preserve aspect ratio |
| **Applies to** | Photos only (NOT signatures) |
| **Classification** | **MANDATORY** |
| **Current Code** | `media_service.py` - no compression step |
| **Required Change** | Add Pillow-based compression before storage |
| **Files** | `backend/services/media_service.py`, `backend/pyproject.toml` |
| **Tests** | Compression reduces dimensions, aspect ratio preserved, JPEG output, small images unchanged |

### D2 - Pre-signed URLs

| Field | Value |
|-------|-------|
| **Audit Finding** | Pre-signed URLs not implemented |
| **Source Document** | `guides/phase 5/22_file_media_management.md` Section 6, `guides/phase 2/09_security_design.md` Section 4 |
| **Source Quote** | "No direct MinIO URLs ever exposed to clients" / "access only via backend-issued pre-signed URLs with short expiry" |
| **Required Spec** | 15-minute expiry, backend authorization before URL generation |
| **Classification** | **MANDATORY** (Security Requirement) |
| **Current Code** | Direct byte streaming endpoints |
| **Required Change** | Add `generate_presigned_url()` to storage, modify download endpoints |
| **Files** | `backend/services/storage_service.py`, `backend/services/storage/minio_provider.py`, `backend/api/v1/media.py`, `backend/api/v1/signatures.py` |
| **Tests** | Valid URL generation, expiry, unauthorized access denied, cross-employee blocked |

### D3 - Document Size Limit

| Field | Value |
|-------|-------|
| **Audit Finding** | Document size limit is 10MB (should be 20MB) |
| **Source Document** | `guides/phase 5/22_file_media_management.md` Section 3 |
| **Source Quote** | "MAX_DOC_SIZE = 20 * 1024 * 1024 # 20MB" |
| **Required Spec** | Images: 10MB, Documents: 20MB |
| **Classification** | **MANDATORY** |
| **Current Code** | Single 10MB limit for all uploads |
| **Required Change** | Separate size limits by media type |
| **Files** | `backend/services/file_validation_service.py` |
| **Tests** | 20MB document accepted, 21MB rejected, 10MB image accepted, 11MB rejected |

### D4 - Android WorkManager

| Field | Value |
|-------|-------|
| **Audit Finding** | WorkManager not implemented for uploads |
| **Source Document** | `guides/phase 6/23_android_application.md` Section 7 |
| **Source Quote** | "On poor field networks, uploads run through WorkManager (not a direct fire-and-forget coroutine)" |
| **Classification** | **MANDATORY** |
| **Current Code** | Direct coroutine upload |
| **Required Change** | Implement WorkManager workers for media and signature uploads |
| **Files** | New: `android/.../workers/MediaUploadWorker.kt`, `android/.../workers/SignatureUploadWorker.kt` |
| **Tests** | Worker enqueue, retry on failure, network constraint, success state |

### D5 - python-magic Validation

| Field | Value |
|-------|-------|
| **Audit Finding** | Hardcoded magic bytes instead of python-magic |
| **Source Document** | `guides/phase 5/22_file_media_management.md` Section 5 |
| **Source Quote** | "Using python-magic (a libmagic binding) for magic-byte detection" |
| **Classification** | **MANDATORY** |
| **Current Code** | Hardcoded `MAGIC_SIGNATURES` dict |
| **Required Change** | Add python-magic dependency, use `magic.from_buffer()` |
| **Files** | `backend/services/file_validation_service.py`, `backend/pyproject.toml` |
| **Tests** | Correct content detected, forged extension rejected, wrong content rejected |

### D6 - Attachment Preview Screen

| Field | Value |
|-------|-------|
| **Audit Finding** | Screen #13 missing |
| **Source Document** | `guides/Phase 2.5/11_android_screen_list.md` |
| **Source Quote** | "Attachment Preview | Full-screen view of an attached photo/document before/after upload" |
| **Classification** | **MANDATORY** |
| **Current Code** | Not implemented |
| **Required Change** | Create AttachmentPreviewScreen composable |
| **Files** | New: `android/.../screens/media/AttachmentPreviewScreen.kt` |
| **Tests** | Preview state, error state, navigation |

### D7 - Memory-Safe File Handling

| Field | Value |
|-------|-------|
| **Audit Finding** | Entire file read into memory |
| **Source Document** | Best practice + architecture doc |
| **Classification** | **MANDATORY** (for production safety) |
| **Current Code** | `readBytes()` loads entire file |
| **Required Change** | Use streaming/chunked reads where possible |
| **Files** | `android/.../screens/media/MediaUploadScreen.kt` |
| **Tests** | Large file handled without OOM |

### D8 - Pre-signed URL Generation

| Field | Value |
|-------|-------|
| **Audit Finding** | No pre-signed URL generation method |
| **Source Document** | `guides/phase 5/22_file_media_management.md` Section 1 |
| **Source Quote** | `generate_presigned_url(self, storage_key, expiry_minutes=15)` |
| **Classification** | **MANDATORY** (Security) |
| **Current Code** | Not implemented |
| **Required Change** | Add to storage service and MinIO provider |
| **Files** | `backend/services/storage_service.py`, `backend/services/storage/minio_provider.py` |
| **Tests** | URL generation, expiry, access control |

### D9 - Separate Document Upload

| Field | Value |
|-------|-------|
| **Audit Finding** | Single endpoint for all uploads |
| **Source Document** | `guides/phase 5/22_file_media_management.md` Sections 2-3 |
| **Classification** | **MANDATORY** |
| **Current Code** | Single POST /visits/{id}/media endpoint |
| **Required Change** | Different validation for images vs documents (size, types) |
| **Files** | `backend/services/media_service.py`, `backend/api/v1/media.py` |
| **Tests** | Document-specific validation, image-specific validation |

### D10 - Signature Download Pre-signed URL

| Field | Value |
|-------|-------|
| **Audit Finding** | Direct bytes instead of pre-signed URL |
| **Source Document** | Same as D2 |
| **Classification** | **MANDATORY** (Security) |
| **Current Code** | Direct byte streaming |
| **Required Change** | Return pre-signed URL |
| **Files** | `backend/api/v1/signatures.py` |
| **Tests** | URL returned, authorization enforced |

### D11 - Android Upload Retry

| Field | Value |
|-------|-------|
| **Audit Finding** | No retry mechanism |
| **Source Document** | `guides/phase 6/23_android_application.md` Section 7 |
| **Classification** | **MANDATORY** |
| **Current Code** | Direct coroutine, no retry |
| **Required Change** | WorkManager with exponential backoff |
| **Files** | Workers (same as D4) |
| **Tests** | Retry on transient failure, no retry on permanent failure |

---

## Implementation Order

1. **python-magic validation** (D5) - Foundation for file security
2. **Image compression** (D1) - Core media feature
3. **Document size limits** (D3, D9) - Separate validation
4. **Pre-signed URL architecture** (D2, D8, D10) - Security architecture
5. **Android WorkManager** (D4, D11) - Upload resilience
6. **Attachment Preview** (D6) - Android screen
7. **Memory-safe handling** (D7) - Safety improvement
8. **Comprehensive tests** - Verify all requirements
9. **Full verification** - Regression + new functionality

---

## Out of Scope (This Phase)

| Item | Reason |
|------|--------|
| Requirement Forms | Separate module |
| Reports | Separate module |
| Notifications | Separate module |
| FT-065 | Separate phase |
| TLS/deployment | Infrastructure phase |
| Visual redesign | Frozen design |
