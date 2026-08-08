# FieldTrack Pro — File & Media Management
### Phase 5 — The other service-layer piece Android needs before Phase 6 build starts
### Revision 2 — backend services rewritten for Python; Android Compose signature component unchanged

Backend service layer for everything that isn't structured data — photos, documents, signatures — all landing in MinIO per the Tech Stack decision. Built before Android (Phase 6) so the app's upload buttons have real endpoints to hit, not mocks.

---

## 1. MinIO Storage Service (Shared Foundation for Everything Below)

```python
# app/storage/minio_client.py
import uuid
from minio import Minio
from app.config import settings
from app.exceptions.custom import StorageException

_client = Minio(
    settings.minio_endpoint,
    access_key=settings.minio_access_key,
    secret_key=settings.minio_secret_key,
    secure=settings.minio_secure,
)


class MediaStorageService:
    def __init__(self, bucket: str = settings.minio_bucket):
        self.bucket = bucket

    def upload(self, file_bytes: bytes, content_type: str, original_filename: str, key_prefix: str) -> str:
        extension = _get_safe_extension(original_filename)
        storage_key = f"{key_prefix}/{uuid.uuid4()}.{extension}"

        try:
            _client.put_object(
                self.bucket, storage_key,
                data=io.BytesIO(file_bytes), length=len(file_bytes),
                content_type=content_type,
            )
        except Exception as e:
            raise StorageException("Failed to upload file") from e
        return storage_key

    def generate_presigned_url(self, storage_key: str, expiry_minutes: int = 15) -> str:
        try:
            return _client.presigned_get_object(
                self.bucket, storage_key, expires=timedelta(minutes=expiry_minutes)
            )
        except Exception as e:
            raise StorageException("Failed to generate access URL") from e
```

**Note the key generation**: `storage_key` is server-generated (`uuid.uuid4()`), never derived from the client's original filename — per the path-traversal/collision protection called out in Security Design Section 5. Original filename is preserved separately as metadata for display purposes only, never used as part of the storage path. Identical rule, identical implementation approach to the original.

---

## 2. Image Upload

```python
# app/storage/image_upload.py
from PIL import Image
import io
from fastapi import UploadFile
from app.exceptions.custom import FileTooLargeException, InvalidFileTypeException

MAX_IMAGE_SIZE = 10 * 1024 * 1024   # 10MB
ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp"}


class ImageUploadService:
    def __init__(self, storage: MediaStorageService, attachment_repo, validator: FileValidator):
        self.storage = storage
        self.attachment_repo = attachment_repo
        self.validator = validator

    async def upload_image(self, visit_id, file: UploadFile) -> VisitAttachmentResponse:
        contents = await file.read()
        if len(contents) > MAX_IMAGE_SIZE:
            raise FileTooLargeException("Image exceeds 10MB limit")
        self.validator.validate_actual_file_type(contents, ALLOWED_TYPES)   # magic-byte check, see Section 5

        compressed = compress_image(contents, max_dimension=1920, quality=80)
        storage_key = self.storage.upload(compressed, "image/jpeg", file.filename, f"visits/{visit_id}/media")

        attachment = VisitAttachment(
            visit_id=visit_id, file_type="IMAGE",
            storage_key=storage_key, original_name=file.filename,
        )
        await self.attachment_repo.save(attachment)
        return VisitAttachmentResponse.from_orm(attachment)


def compress_image(raw_bytes: bytes, max_dimension: int, quality: int) -> bytes:
    image = Image.open(io.BytesIO(raw_bytes))
    image.thumbnail((max_dimension, max_dimension))   # preserves aspect ratio
    if image.mode in ("RGBA", "P"):
        image = image.convert("RGB")   # JPEG has no alpha channel
    output = io.BytesIO()
    image.save(output, format="JPEG", quality=quality, optimize=True)
    return output.getvalue()
```

**Compression is mandatory, not optional** — field employees are uploading from mobile data on inconsistent networks (per Requirements doc's usability targets), and uncompressed photos from modern phone cameras routinely run 5-8MB each. Pillow's `.thumbnail()` + JPEG quality reduction is the direct Python equivalent of the original Thumbnailator call — same max-dimension and quality parameters, same effect on upload time and storage cost.

---

## 3. Document Upload

```python
# app/storage/document_upload.py
from fastapi import UploadFile
from app.exceptions.custom import FileTooLargeException

MAX_DOC_SIZE = 20 * 1024 * 1024   # 20MB
ALLOWED_TYPES = {
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


class DocumentUploadService:
    def __init__(self, storage: MediaStorageService, attachment_repo, validator: FileValidator):
        self.storage = storage
        self.attachment_repo = attachment_repo
        self.validator = validator

    async def upload_document(self, visit_id, file: UploadFile) -> VisitAttachmentResponse:
        contents = await file.read()
        if len(contents) > MAX_DOC_SIZE:
            raise FileTooLargeException("Document exceeds 20MB limit")
        self.validator.validate_actual_file_type(contents, ALLOWED_TYPES)   # magic-byte check, not just declared MIME type

        storage_key = self.storage.upload(contents, file.content_type, file.filename, f"visits/{visit_id}/media")

        attachment = VisitAttachment(
            visit_id=visit_id, file_type="DOCUMENT",
            storage_key=storage_key, original_name=file.filename,
        )
        await self.attachment_repo.save(attachment)
        return VisitAttachmentResponse.from_orm(attachment)
```

No compression here (compressing a PDF/Word doc isn't meaningful the way it is for images) — the size cap and type restriction are the controls instead, same as the original.

---

## 4. Digital Signatures

Signatures come from the Android Compose Canvas component (per Tech Stack decision — no third-party signature library needed) as a PNG image, uploaded through a dedicated endpoint rather than reusing the generic image upload, because signatures have different rules: no compression (would degrade the legal-record quality of the signature) and a hard uniqueness constraint per visit.

```python
# app/storage/signature_service.py
from app.exceptions.custom import InvalidArgumentException, DuplicateResourceException

VALID_SIGNED_BY = {"EMPLOYEE", "CUSTOMER"}


class SignatureService:
    def __init__(self, storage: MediaStorageService, signature_repo):
        self.storage = storage
        self.signature_repo = signature_repo

    async def upload_signature(self, visit_id, signed_by: str, file: UploadFile) -> VisitSignatureResponse:
        if signed_by not in VALID_SIGNED_BY:
            raise InvalidArgumentException("signedBy must be EMPLOYEE or CUSTOMER")

        # Uniqueness enforced at DB level too (uq_visit_signature constraint), but checking
        # here first gives a clean 409 instead of a raw constraint-violation error
        if await self.signature_repo.exists(visit_id, signed_by):
            raise DuplicateResourceException(f"{signed_by} signature already recorded for this visit")

        contents = await file.read()
        storage_key = self.storage.upload(contents, "image/png", file.filename, f"visits/{visit_id}/signatures")
        # no compression — signature clarity matters more than file size here, and these are small PNGs anyway

        signature = VisitSignature(visit_id=visit_id, signature_type=signed_by, storage_key=storage_key)
        await self.signature_repo.save(signature)
        return VisitSignatureResponse.from_orm(signature)
```

**Android Compose Canvas component** (unchanged — referenced for context; actual Android implementation happens in Phase 6, this is the shape it needs to produce, and it has no dependency on backend language):
```kotlin
@Composable
fun SignaturePad(onSignatureComplete: (Bitmap) -> Unit) {
    val path = remember { Path() }
    Canvas(modifier = Modifier.pointerInput(Unit) {
        detectDragGestures { change, _ -> path.lineTo(change.position.x, change.position.y) }
    }) {
        drawPath(path, color = Color.Black, style = Stroke(width = 4f))
    }
    // "Done" button captures Canvas as Bitmap, converts to PNG, passes to onSignatureComplete
}
```

---

## 5. File Validation — Shared Across All Upload Types

```python
# app/storage/file_validation.py
import magic
from app.exceptions.custom import InvalidFileTypeException


class FileValidator:
    def validate_actual_file_type(self, file_bytes: bytes, allowed_mime_types: set[str]) -> None:
        detected_type = magic.from_buffer(file_bytes, mime=True)   # reads actual file content, not client-declared header
        if detected_type not in allowed_mime_types:
            raise InvalidFileTypeException(
                f"File content does not match an allowed type (detected: {detected_type})"
            )
```

Using **`python-magic`** (a `libmagic` binding) for magic-byte detection rather than trusting the client-declared `Content-Type` header — the direct Python equivalent of the original Apache Tika usage, same enforcement point for the "never trust client-declared MIME type" rule from Security Design Section 5. Requires the system `libmagic1` package be present in the container (see Python Backend Setup doc's note on this and the Deployment doc's Dockerfile).

---

## 6. Storage Management

*(Unchanged — bucket layout, access pattern, and retention policy are language-independent decisions.)*

### Bucket Organization
```
fieldtrackpro-{env}/
  visits/
    {visitId}/
      media/
        {uuid}.jpg
        {uuid}.pdf
      signatures/
        {uuid}.png   (EMPLOYEE)
        {uuid}.png   (CUSTOMER)
```

### Access Pattern
- **No direct MinIO URLs ever exposed to clients** — every file access goes through `GET /visits/{id}/media` or `/signatures`, which returns short-lived (15-minute) pre-signed URLs generated on demand by `MediaStorageService.generate_presigned_url()`. This matches the Security Design principle of never exposing MinIO directly, so object keys can't be guessed/enumerated.
- Android/Web never construct storage URLs themselves — they always call the backend to get a fresh pre-signed URL, since URLs expire.

### Retention & Cleanup
- **No automated deletion for MVP** — per the Requirements doc's data retention section, visit records (and their attached media) are retained indefinitely. No cleanup job needed at this phase.
- **Orphan prevention**: file upload and DB record creation happen inside the same request handler, with the DB write (`await self.attachment_repo.save(attachment)`) as the last step — if it fails after a successful MinIO upload, the transaction still needs the attachment row to exist for the file to be reachable (MinIO isn't transactional with Postgres, same as the original), so a periodic reconciliation job remains a reasonable Phase 9+ addition if orphaned files in MinIO ever become a real problem. Not needed for MVP launch, flagging as a known small gap rather than solving it now — carried forward unchanged from the original doc.

### Storage Capacity Planning (Rough Guidance for On-Prem Sizing)
- Compressed images: ~300-500KB each after compression
- Documents: variable, capped at 20MB
- Signatures: ~20-50KB each (small PNGs)
- At, say, 50 employees × 8 visits/day × 3 photos/visit average: roughly 3,600 photos/day ≈ 1.5-2GB/day → worth flagging to whoever manages the on-prem server so disk capacity planning happens before storage fills up unexpectedly, not after.

---

## Phase 5 — Complete

Image upload (with compression), document upload, signature capture/storage, and the shared validation + pre-signed URL access pattern are all built — behaviorally identical to the original, now in Python.

**Next up:** Phase 6 — Android Application. Every backend dependency (Auth, Core APIs, Maps/Location services, File/Media services) now exists — this is the first phase where Android can be built against a fully real backend, not mocks.
