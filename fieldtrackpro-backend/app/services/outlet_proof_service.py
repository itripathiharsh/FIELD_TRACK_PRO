"""
Live outlet proof service.

An outlet proof is ONE bundle: a live photo of the outlet plus the GPS fix
taken at that exact click, so the two corroborate each other. See
app/models/outlet_proof.py for the status lifecycle.

Rules (all thresholds are config-driven, see app/config.py outlet_proof_*):
  * the photo is camera-live: captured_at must be fresh, location must not be a
    mock provider, accuracy must be good, coordinates must be inside India;
  * the stored image is RE-ENCODED (EXIF orientation applied, ALL metadata
    including EXIF GPS stripped, downscaled, JPEG) - the GPS that counts is the
    one in the form fields, never anything inside the image file;
  * the same photo can not be reused for a different outlet;
  * kind/status is derived server-side: no verified location -> INITIAL/PENDING;
    verified + within confirm radius -> CONFIRMATION/CONFIRMED (no admin action);
    verified + farther -> CHANGE_REQUEST/PENDING (admin review, never auto-applied);
  * only an admin approval changes customer.location (plus the optional,
    default-disabled auto-verify rule).

Logging never includes coordinates or tokens (see test_production_logging).
"""
from __future__ import annotations

import asyncio
import io
import logging
import math
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import UploadFile
from geoalchemy2.shape import from_shape
from shapely.geometry import Point
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.uploads import read_upload_limited
from app.config import settings
from app.core.context import get_current_request_id
from app.exceptions.custom import BaseAPIException
from app.models.area import Area
from app.models.customer import Customer
from app.models.customer_location_proposal import CustomerLocationProposal, LocationProposalStatus
from app.models.customer_prospect import CustomerProspect
from app.models.employee import Employee
from app.models.notification import NotificationType
from app.models.outlet_proof import OutletProof, OutletProofKind, OutletProofStatus
from app.models.territory import Territory
from app.models.user import Role, User
from app.schemas.outlet_proof import OutletProofRead
from app.services.customer_service import (
    assert_employee_can_view_customer,
    calculate_distance_meters,
    extract_coords,
)
from app.services.employee_service import get_employee_by_user_id
from app.services.file_validation_service import FileValidationService
from app.services.storage_service import storage_service

logger = logging.getLogger("fieldtrackpro")

# India bounding box (lat 6-37.5, lon 68-98) - a coarse sanity check, not a border test.
INDIA_LAT_MIN, INDIA_LAT_MAX = 6.0, 37.5
INDIA_LON_MIN, INDIA_LON_MAX = 68.0, 98.0
IST = timezone(timedelta(hours=5, minutes=30))  # India has no DST

_PENDING_REVIEW_KINDS = (OutletProofKind.INITIAL.value, OutletProofKind.CHANGE_REQUEST.value)
_COUNTED_STATUSES = (
    OutletProofStatus.PENDING.value,
    OutletProofStatus.APPROVED.value,
    OutletProofStatus.CONFIRMED.value,
    OutletProofStatus.SUPERSEDED.value,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _err(status: int, code: str, detail: str) -> BaseAPIException:
    return BaseAPIException(status_code=status, detail=detail, error_code=code)


def _ist_date(dt: datetime):
    return dt.astimezone(IST).date()


def _dist(a_lat: float, a_lon: float, b_lat: float, b_lon: float) -> float:
    return calculate_distance_meters(a_lat, a_lon, b_lat, b_lon)


# ---------------------------------------------------------------------------
# Capture + image validation
# ---------------------------------------------------------------------------

def parse_captured_at(raw: str | None) -> datetime:
    if not raw or not raw.strip():
        raise _err(422, "OUTLET_PROOF_CAPTURED_AT_REQUIRED", "captured_at (ISO-8601 with timezone) is required.")
    try:
        dt = datetime.fromisoformat(raw.strip().replace("Z", "+00:00"))
    except ValueError:
        raise _err(422, "OUTLET_PROOF_CAPTURED_AT_INVALID", "captured_at must be an ISO-8601 timestamp.")
    if dt.tzinfo is None:
        raise _err(422, "OUTLET_PROOF_CAPTURED_AT_INVALID", "captured_at must include a timezone offset (e.g. Z or +05:30).")
    return dt.astimezone(timezone.utc)


def validate_capture(
    latitude: float | None,
    longitude: float | None,
    accuracy_m: float | None,
    captured_at: datetime,
    is_mock_location: bool | None,
    now: datetime | None = None,
) -> None:
    """Server-side live-capture rules. Raises BaseAPIException with a stable error_code."""
    now = now or _now()
    if is_mock_location is None:
        raise _err(422, "OUTLET_PROOF_MOCK_FLAG_REQUIRED", "is_mock_location is required.")
    if is_mock_location:
        raise _err(422, "OUTLET_PROOF_MOCK_LOCATION", "A mock/fake GPS location cannot be used as outlet proof.")
    if latitude is None or longitude is None or not (math.isfinite(latitude) and math.isfinite(longitude)):
        raise _err(422, "OUTLET_PROOF_COORDINATES_REQUIRED", "latitude and longitude are required.")
    if accuracy_m is None or not math.isfinite(accuracy_m) or accuracy_m < 0:
        raise _err(422, "OUTLET_PROOF_ACCURACY_REQUIRED", "accuracy_m (GPS accuracy in metres) is required.")
    if accuracy_m > settings.outlet_proof_max_accuracy_m:
        raise _err(
            422,
            "OUTLET_PROOF_ACCURACY_TOO_LOW",
            f"GPS accuracy is too poor (must be {settings.outlet_proof_max_accuracy_m:g} m or better). "
            "Move to open sky and retake the photo.",
        )
    if not (INDIA_LAT_MIN <= latitude <= INDIA_LAT_MAX and INDIA_LON_MIN <= longitude <= INDIA_LON_MAX):
        raise _err(422, "OUTLET_PROOF_OUTSIDE_INDIA", "The captured location is outside India.")
    age = (now - captured_at).total_seconds()
    if age > settings.outlet_proof_max_age_seconds:
        raise _err(
            422,
            "OUTLET_PROOF_STALE_CAPTURE",
            "The photo was not captured live (too old). Take the photo again right at the outlet.",
        )
    if age < -settings.outlet_proof_future_tolerance_seconds:
        raise _err(422, "OUTLET_PROOF_FUTURE_CAPTURE", "captured_at is in the future. Check the device clock.")


def reencode_image(raw: bytes) -> bytes:
    """
    Apply EXIF orientation, drop ALL metadata (EXIF/GPS/XMP/ICC...), downscale the longest
    side to settings.outlet_proof_max_dimension_px and save as JPEG. Deterministic for the
    same input (used for the duplicate-photo checksum). Raises a 415/422 BaseAPIException.
    """
    from PIL import Image, ImageOps

    try:
        with Image.open(io.BytesIO(raw)) as img:
            if img.width * img.height > 60_000_000:
                raise _err(422, "OUTLET_PROOF_IMAGE_TOO_LARGE", "Image dimensions are too large.")
            img.load()
            img = ImageOps.exif_transpose(img)
            if img.mode in ("RGBA", "LA", "P"):
                rgba = img.convert("RGBA")
                bg = Image.new("RGB", rgba.size, (255, 255, 255))
                bg.paste(rgba, mask=rgba.split()[-1])
                img = bg
            elif img.mode != "RGB":
                img = img.convert("RGB")
            limit = settings.outlet_proof_max_dimension_px
            if max(img.size) > limit:
                ratio = limit / max(img.size)
                img = img.resize(
                    (max(1, int(img.width * ratio)), max(1, int(img.height * ratio))),
                    Image.Resampling.LANCZOS,
                )
            out = io.BytesIO()
            # No exif=/icc_profile= kwargs and a fresh image object => nothing carried over.
            img.save(out, format="JPEG", quality=settings.outlet_proof_jpeg_quality, optimize=True)
            return out.getvalue()
    except BaseAPIException:
        raise
    except Exception:
        raise _err(415, "OUTLET_PROOF_INVALID_IMAGE", "The uploaded file is not a readable image.")


# ---------------------------------------------------------------------------
# Lookups / helpers
# ---------------------------------------------------------------------------

async def _lock_customer(session: AsyncSession, customer_id: uuid.UUID) -> Customer:
    # of=Customer: Customer.territory/area are lazy="joined"; Postgres rejects FOR UPDATE on
    # the nullable side of an outer join (same note as mark_tally_entry_done).
    stmt = select(Customer).where(Customer.id == customer_id).with_for_update(of=Customer)
    # populate_existing: after waiting for the lock, re-read the row (a concurrent first registration may have
    # just set the location) instead of trusting a copy already in the session.
    customer = (await session.execute(stmt.execution_options(populate_existing=True))).scalar_one_or_none()
    if customer is None:
        raise _err(404, "CUSTOMER_NOT_FOUND", f"Customer with id '{customer_id}' not found.")
    return customer


async def _approved_primary(session: AsyncSession, customer_id: uuid.UUID) -> OutletProof | None:
    stmt = select(OutletProof).where(
        OutletProof.customer_id == customer_id,
        OutletProof.is_primary.is_(True),
        OutletProof.status == OutletProofStatus.APPROVED.value,
    )
    return (await session.execute(stmt.limit(1))).scalar_one_or_none()


async def _existing_by_idempotency(session: AsyncSession, user_id: uuid.UUID, key: str | None) -> OutletProof | None:
    if not key:
        return None
    stmt = select(OutletProof).where(OutletProof.submitted_by == user_id, OutletProof.idempotency_key == key)
    return (await session.execute(stmt)).scalar_one_or_none()


async def _notify(session: AsyncSession, user_id: uuid.UUID, title: str, message: str) -> None:
    """Best-effort (REMINDER type); never undoes a decision already committed."""
    try:
        from app.services.notification_service import notification_service

        await notification_service.create_notification(
            user_id=user_id,
            notification_type=NotificationType.REMINDER,
            title=title,
            message=message,
            session=session,
        )
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("event=outlet_proof_notify_failed error=%s", type(exc).__name__)


# ---------------------------------------------------------------------------
# Upload
# ---------------------------------------------------------------------------

async def create_outlet_proof(
    *,
    photo: UploadFile,
    latitude: float | None,
    longitude: float | None,
    accuracy_m: float | None,
    captured_at_raw: str | None,
    is_mock_location: bool | None,
    device_info: str | None,
    idempotency_key: str | None,
    customer_id: uuid.UUID | None,
    current_user: User,
    session: AsyncSession,
) -> OutletProof:
    req_id = get_current_request_id()

    # 0. Idempotent replay: return the already-stored proof, before any (time-sensitive) validation.
    existing = await _existing_by_idempotency(session, current_user.id, idempotency_key)
    if existing is not None:
        return existing

    # 1. Capture rules (cheap, before reading the image).
    captured_at = parse_captured_at(captured_at_raw)
    validate_capture(latitude, longitude, accuracy_m, captured_at, is_mock_location)
    assert latitude is not None and longitude is not None and accuracy_m is not None

    # 2. Target + scope. Employees: in-scope outlets only (404 otherwise, same as other customer routes).
    employee: Employee | None = None
    if current_user.role == Role.EMPLOYEE:
        employee = await get_employee_by_user_id(current_user.id, session)
    if customer_id is not None:
        await assert_employee_can_view_customer(customer_id, current_user, session)

    # 3. Image: bounded read, magic-byte validation (JPEG/PNG/WEBP, size cap), re-encode.
    raw = await read_upload_limited(photo, settings.outlet_proof_max_image_bytes)
    FileValidationService.validate_image(raw, photo.filename or "outlet.jpg")
    jpeg = await asyncio.to_thread(reencode_image, raw)
    checksum = FileValidationService.compute_sha256(jpeg)

    # 4. Duplicate-photo guard: the same photo may not back a DIFFERENT outlet.
    dup_stmt = select(OutletProof.id).where(OutletProof.checksum_sha256 == checksum)
    if customer_id is not None:
        dup_stmt = dup_stmt.where(
            (OutletProof.customer_id.is_(None)) | (OutletProof.customer_id != customer_id)
        )
    if (await session.execute(dup_stmt.limit(1))).first() is not None:
        raise _err(409, "OUTLET_PROOF_DUPLICATE_IMAGE", "This photo was already used as proof for another outlet.")

    # 5. Kind / status.
    proof_id = uuid.uuid4()
    kind = OutletProofKind.INITIAL.value
    status = OutletProofStatus.UNATTACHED.value
    distance: float | None = None
    customer: Customer | None = None
    if customer_id is not None:
        customer = await _lock_customer(session, customer_id)
        approved = await _approved_primary(session, customer.id)
        verified = customer.location is not None and (
            customer.location_status == "VERIFIED" or approved is not None
        )
        if customer.location is not None:
            c_lat, c_lon = extract_coords(customer.location)
            distance = _dist(c_lat, c_lon, latitude, longitude)
        if not verified:
            kind, status = OutletProofKind.INITIAL.value, OutletProofStatus.PENDING.value
        elif distance is not None and distance <= settings.outlet_proof_confirm_radius_m:
            kind, status = OutletProofKind.CONFIRMATION.value, OutletProofStatus.CONFIRMED.value
        else:
            kind, status = OutletProofKind.CHANGE_REQUEST.value, OutletProofStatus.PENDING.value

        if status == OutletProofStatus.PENDING.value:
            dup_pending = await session.execute(
                select(OutletProof.id).where(
                    OutletProof.customer_id == customer.id,
                    OutletProof.submitted_by == current_user.id,
                    OutletProof.status == OutletProofStatus.PENDING.value,
                    OutletProof.kind.in_(_PENDING_REVIEW_KINDS),
                ).limit(1)
            )
            if dup_pending.first() is not None:
                raise _err(
                    409,
                    "OUTLET_PROOF_ALREADY_PENDING",
                    "You already have an outlet proof for this outlet waiting for admin review.",
                )
        else:  # CONFIRMATION: one counted confirmation per person per outlet (keeps the count honest)
            prior = await session.execute(
                select(OutletProof.id).where(
                    OutletProof.customer_id == customer.id,
                    OutletProof.submitted_by == current_user.id,
                    OutletProof.status.in_(
                        (OutletProofStatus.CONFIRMED.value, OutletProofStatus.APPROVED.value)
                    ),
                ).limit(1)
            )
            if prior.first() is not None:
                raise _err(
                    409,
                    "OUTLET_PROOF_ALREADY_CONFIRMED",
                    "You have already provided an accepted proof for this outlet.",
                )

    # 6. Store the object (provider-agnostic), then the row. Clean the object up on any DB failure.
    storage_key = f"outlet-proofs/{_now():%Y}/{proof_id}.jpg"
    await storage_service.upload(jpeg, storage_key, "image/jpeg")
    proof = OutletProof(
        id=proof_id,
        customer_id=customer.id if customer else None,
        kind=kind,
        status=status,
        is_primary=False,
        storage_key=storage_key,
        storage_provider=settings.storage_provider.upper(),
        content_type="image/jpeg",
        size_bytes=len(jpeg),
        checksum_sha256=checksum,
        latitude=latitude,
        longitude=longitude,
        accuracy_m=accuracy_m,
        captured_at=captured_at,
        is_mock_location=False,
        device_info=(device_info or "").strip()[:200] or None,
        submitted_by=current_user.id,
        submitted_by_employee_id=employee.id if employee else None,
        distance_from_verified_m=distance,
        idempotency_key=idempotency_key,
    )
    session.add(proof)
    try:
        if customer is not None and kind == OutletProofKind.INITIAL.value:
            customer.location_status = "PENDING_APPROVAL"
        await session.flush()
        if customer is not None:
            if not await _maybe_accept_first_location(session, customer, proof):
                await _maybe_auto_verify(session, customer, proof)
        await session.commit()
    except IntegrityError:
        # Lost an idempotency race (or a constraint): drop our object and return the winner if any.
        await session.rollback()
        await _safe_delete_object(storage_key)
        winner = await _existing_by_idempotency(session, current_user.id, idempotency_key)
        if winner is not None:
            return winner
        raise
    except Exception:
        await session.rollback()
        await _safe_delete_object(storage_key)
        raise
    await session.refresh(proof)
    await flush_post_commit_notifications(session)

    logger.info(
        "event=outlet_proof_upload result=success request_id=%s proof_id=%s customer_id=%s kind=%s status=%s accuracy_m=%s",
        req_id, proof.id, proof.customer_id, proof.kind, proof.status, proof.accuracy_m,
    )
    return proof


async def _safe_delete_object(storage_key: str) -> None:
    try:
        await storage_service.delete(storage_key)
    except Exception:  # pragma: no cover - defensive
        logger.warning("event=outlet_proof_orphan_cleanup_failed storage_key=%s", storage_key)


# ---------------------------------------------------------------------------
# Approval core (shared by admin approve and the optional auto-verify rule)
# ---------------------------------------------------------------------------

async def _apply_approval(
    session: AsyncSession,
    customer: Customer,
    proof: OutletProof,
    reviewer_id: uuid.UUID | None,
    now: datetime,
) -> list[tuple[uuid.UUID, str, str]]:
    """
    Make `proof` the customer's primary proof/official pin. Caller holds the customer lock and
    commits. Returns notifications to send AFTER the commit as (user_id, title, message).
    """
    notes: list[tuple[uuid.UUID, str, str]] = []
    radius = settings.outlet_proof_confirm_radius_m

    olds = (
        await session.execute(
            select(OutletProof).where(
                OutletProof.customer_id == customer.id,
                OutletProof.id != proof.id,
                OutletProof.is_primary.is_(True),
            )
        )
    ).scalars().all()
    for old in olds:
        old.is_primary = False
        if old.status == OutletProofStatus.APPROVED.value:
            old.status = OutletProofStatus.SUPERSEDED.value

    proof.status = OutletProofStatus.APPROVED.value
    proof.is_primary = True
    proof.reviewed_by = reviewer_id
    proof.reviewed_at = now
    customer.location = from_shape(Point(proof.longitude, proof.latitude), srid=4326)
    customer.location_status = "VERIFIED"
    notes.append((proof.submitted_by, "Outlet location approved", "Your outlet photo and location were approved."))

    others = (
        await session.execute(
            select(OutletProof).where(
                OutletProof.customer_id == customer.id,
                OutletProof.id != proof.id,
                OutletProof.status.in_((OutletProofStatus.PENDING.value, OutletProofStatus.CONFIRMED.value)),
            )
        )
    ).scalars().all()
    for o in others:
        d = _dist(proof.latitude, proof.longitude, o.latitude, o.longitude)
        o.distance_from_verified_m = d
        if o.status == OutletProofStatus.PENDING.value:
            if d <= radius:
                o.status = OutletProofStatus.CONFIRMED.value
                o.kind = OutletProofKind.CONFIRMATION.value
                notes.append((o.submitted_by, "Outlet location confirmed", "Your outlet photo confirmed the approved location."))
            else:
                # Now a disagreement with the verified pin: stays PENDING for the admin.
                o.kind = OutletProofKind.CHANGE_REQUEST.value
        elif d > radius:  # an old confirmation of a location that has just moved
            o.status = OutletProofStatus.SUPERSEDED.value

    # Keep the older location-proposal flow consistent: pending proposals that agree with the
    # newly approved pin are closed as approved; disagreeing ones stay pending for the admin.
    legacy = (
        await session.execute(
            select(CustomerLocationProposal).where(
                CustomerLocationProposal.customer_id == customer.id,
                CustomerLocationProposal.status == LocationProposalStatus.PENDING,
            )
        )
    ).scalars().all()
    for lp in legacy:
        if _dist(proof.latitude, proof.longitude, lp.proposed_latitude, lp.proposed_longitude) <= radius:
            lp.status = LocationProposalStatus.APPROVED
            lp.reviewed_by = reviewer_id
            lp.reviewed_at = now

    await session.flush()
    return notes


async def _maybe_accept_first_location(session: AsyncSession, customer: Customer, proof: OutletProof) -> bool:
    """
    FIRST LOCATION = AUTOMATIC ACCEPTANCE (business rule, outlet_proof_first_location_auto_accept).

    The caller holds the customer row lock and has already validated the capture (fresh, accurate, not mock, inside
    India, real photo). Accepted here only when the outlet has NO coordinates at all and no proof was ever accepted for
    it, so this can happen once per outlet: a concurrent second registration waits on the lock, re-reads the row and
    is then handled as a CONFIRMATION or CHANGE_REQUEST. Nothing here creates a visit or a check-in.
    """
    if not settings.outlet_proof_first_location_auto_accept:
        return False
    if proof.kind != OutletProofKind.INITIAL.value or proof.status != OutletProofStatus.PENDING.value:
        return False
    if customer.location is not None:
        return False
    ever_accepted = (
        await session.execute(
            select(OutletProof.id).where(
                OutletProof.customer_id == customer.id,
                OutletProof.id != proof.id,
                OutletProof.status.in_((OutletProofStatus.APPROVED.value, OutletProofStatus.SUPERSEDED.value)),
            ).limit(1)
        )
    ).first()
    if ever_accepted is not None:
        return False
    notes = await _apply_approval(session, customer, proof, None, _now())
    proof.auto_accepted = True
    # The submitter is told it was registered (not "approved by an admin").
    notes = [(uid, "Outlet location registered", "Your photo and GPS were saved as this outlet's location.")
             if uid == proof.submitted_by and title == "Outlet location approved" else (uid, title, msg)
             for uid, title, msg in notes]
    session.info.setdefault("outlet_proof_post_commit_notes", []).extend(notes)
    logger.info(
        "event=outlet_proof_first_location result=auto_accepted request_id=%s customer_id=%s proof_id=%s accuracy_m=%s",
        get_current_request_id(), customer.id, proof.id, proof.accuracy_m,
    )
    return True


async def _maybe_auto_verify(session: AsyncSession, customer: Customer, new_proof: OutletProof) -> bool:
    """
    Default OFF (outlet_proof_auto_verify_min_agreeing = 0). With N >= 2: when N distinct
    employees on N distinct IST dates each have a PENDING INITIAL proof within the confirm
    radius of the newest proof, each with accuracy <= outlet_proof_auto_verify_max_accuracy_m,
    the most accurate one is approved (reviewed_by = NULL = system). Only for outlets with no
    verified location (INITIAL); a CHANGE_REQUEST is never auto-applied.
    """
    n = settings.outlet_proof_auto_verify_min_agreeing
    if n < 2 or new_proof.kind != OutletProofKind.INITIAL.value or new_proof.status != OutletProofStatus.PENDING.value:
        return False
    cands = (
        await session.execute(
            select(OutletProof).where(
                OutletProof.customer_id == customer.id,
                OutletProof.status == OutletProofStatus.PENDING.value,
                OutletProof.kind == OutletProofKind.INITIAL.value,
                OutletProof.accuracy_m <= settings.outlet_proof_auto_verify_max_accuracy_m,
            )
        )
    ).scalars().all()
    near = [
        p for p in cands
        if _dist(new_proof.latitude, new_proof.longitude, p.latitude, p.longitude)
        <= settings.outlet_proof_confirm_radius_m
    ]
    picked: list[OutletProof] = []
    emps: set = set()
    dates: set = set()
    for p in sorted(near, key=lambda x: x.captured_at):
        d = _ist_date(p.captured_at)
        if p.submitted_by in emps or d in dates:
            continue
        emps.add(p.submitted_by)
        dates.add(d)
        picked.append(p)
    if len(picked) < n or new_proof.id not in {p.id for p in picked}:
        return False
    best = min(picked, key=lambda p: p.accuracy_m)
    notes = await _apply_approval(session, customer, best, None, _now())
    # Notifications commit internally; defer them until after the caller's own commit.
    session.info.setdefault("outlet_proof_post_commit_notes", []).extend(notes)
    logger.info(
        "event=outlet_proof_auto_verify result=approved request_id=%s customer_id=%s proof_id=%s agreeing=%s",
        get_current_request_id(), customer.id, best.id, len(picked),
    )
    return True


async def flush_post_commit_notifications(session: AsyncSession) -> None:
    for user_id, title, message in session.info.pop("outlet_proof_post_commit_notes", []):
        await _notify(session, user_id, title, message)


# ---------------------------------------------------------------------------
# Admin review
# ---------------------------------------------------------------------------

async def _lock_pending_proof_with_customer(
    proof_id: uuid.UUID, session: AsyncSession
) -> tuple[OutletProof, Customer]:
    """Lock order is always customer THEN proof (matches upload) to avoid deadlocks."""
    peek = (await session.execute(select(OutletProof).where(OutletProof.id == proof_id))).scalar_one_or_none()
    if peek is None:
        raise _err(404, "OUTLET_PROOF_NOT_FOUND", "Outlet proof not found.")
    if peek.customer_id is None:
        raise _err(
            409,
            "OUTLET_PROOF_PROSPECT_PENDING",
            "This proof belongs to a new-outlet submission; approve or reject the submission instead.",
        )
    customer = await _lock_customer(session, peek.customer_id)
    proof = (
        await session.execute(
            select(OutletProof).where(OutletProof.id == proof_id).with_for_update().execution_options(populate_existing=True)
        )
    ).scalar_one()
    if proof.status != OutletProofStatus.PENDING.value:
        current = proof.status
        await session.rollback()
        raise _err(409, "OUTLET_PROOF_NOT_PENDING", f"This proof is already {current.lower()}.")
    return proof, customer


async def approve_outlet_proof(proof_id: uuid.UUID, admin: User, session: AsyncSession) -> OutletProof:
    proof, customer = await _lock_pending_proof_with_customer(proof_id, session)
    notes = await _apply_approval(session, customer, proof, admin.id, _now())
    await session.commit()
    await session.refresh(proof)
    for user_id, title, message in notes:
        await _notify(session, user_id, title, message)
    logger.info(
        "event=outlet_proof_approve result=success request_id=%s proof_id=%s customer_id=%s reviewed_by=%s",
        get_current_request_id(), proof.id, proof.customer_id, admin.id,
    )
    return proof


async def reject_outlet_proof(proof_id: uuid.UUID, reason: str, admin: User, session: AsyncSession) -> OutletProof:
    reason = (reason or "").strip()
    if len(reason) < 3:
        raise _err(422, "REJECTION_REASON_REQUIRED", "A rejection reason of at least 3 characters is required.")
    proof, customer = await _lock_pending_proof_with_customer(proof_id, session)
    proof.status = OutletProofStatus.REJECTED.value
    proof.reviewed_by = admin.id
    proof.reviewed_at = _now()
    proof.rejection_reason = reason[:255]
    await session.flush()

    # Restore location_status only when WE had put it into PENDING_APPROVAL and nothing else
    # is still waiting for review (other pending INITIAL proofs / older location proposals).
    if customer.location_status == "PENDING_APPROVAL":
        other_initial = (
            await session.execute(
                select(OutletProof.id).where(
                    OutletProof.customer_id == customer.id,
                    OutletProof.status == OutletProofStatus.PENDING.value,
                    OutletProof.kind == OutletProofKind.INITIAL.value,
                ).limit(1)
            )
        ).first()
        legacy_pending = (
            await session.execute(
                select(CustomerLocationProposal.id).where(
                    CustomerLocationProposal.customer_id == customer.id,
                    CustomerLocationProposal.status == LocationProposalStatus.PENDING,
                ).limit(1)
            )
        ).first()
        if other_initial is None and legacy_pending is None:
            customer.location_status = "MISSING" if customer.location is None else "VERIFIED"
    await session.commit()
    await session.refresh(proof)
    await _notify(
        session, proof.submitted_by, "Outlet photo rejected",
        f"Your outlet photo/location submission was rejected: {reason}",
    )
    logger.info(
        "event=outlet_proof_reject result=success request_id=%s proof_id=%s reviewed_by=%s",
        get_current_request_id(), proof.id, admin.id,
    )
    return proof


# ---------------------------------------------------------------------------
# Prospect integration (called from customer_prospect_service; flush only, caller commits)
# ---------------------------------------------------------------------------

async def claim_unattached_proof(proof_id: uuid.UUID, current_user: User, session: AsyncSession) -> OutletProof:
    """Validate an UNATTACHED proof for use by a new-outlet submission (owner only, not expired)."""
    proof = (
        await session.execute(select(OutletProof).where(OutletProof.id == proof_id).with_for_update())
    ).scalar_one_or_none()
    if proof is None or proof.submitted_by != current_user.id:
        raise _err(404, "OUTLET_PROOF_NOT_FOUND", "Outlet proof not found.")
    if proof.status != OutletProofStatus.UNATTACHED.value or proof.prospect_id is not None:
        raise _err(409, "OUTLET_PROOF_NOT_UNATTACHED", "This outlet proof is already used.")
    if proof.created_at < _now() - timedelta(hours=settings.outlet_proof_unattached_ttl_hours):
        raise _err(409, "OUTLET_PROOF_EXPIRED", "This outlet proof has expired. Take the photo again.")
    return proof


def link_proof_to_prospect(proof: OutletProof, prospect: CustomerProspect) -> None:
    proof.prospect_id = prospect.id
    proof.kind = OutletProofKind.INITIAL.value
    proof.status = OutletProofStatus.PENDING.value


async def on_prospect_approved(
    prospect_id: uuid.UUID, customer: Customer, admin: User, session: AsyncSession
) -> bool:
    """Attach the prospect's proof(s) to the new customer; the first becomes the APPROVED primary."""
    proofs = (
        await session.execute(
            select(OutletProof).where(
                OutletProof.prospect_id == prospect_id,
                OutletProof.status == OutletProofStatus.PENDING.value,
            ).order_by(OutletProof.received_at)
        )
    ).scalars().all()
    now = _now()
    for i, p in enumerate(proofs):
        p.customer_id = customer.id
        if i == 0:
            p.status = OutletProofStatus.APPROVED.value
            p.is_primary = True
            p.reviewed_by = admin.id
            p.reviewed_at = now
    await session.flush()
    return bool(proofs)


async def on_prospect_rejected(
    prospect_id: uuid.UUID, reason: str, admin: User, session: AsyncSession
) -> None:
    proofs = (
        await session.execute(
            select(OutletProof).where(
                OutletProof.prospect_id == prospect_id,
                OutletProof.status == OutletProofStatus.PENDING.value,
            )
        )
    ).scalars().all()
    now = _now()
    for p in proofs:
        p.status = OutletProofStatus.REJECTED.value
        p.reviewed_by = admin.id
        p.reviewed_at = now
        p.rejection_reason = (reason or "")[:255]
    await session.flush()


# ---------------------------------------------------------------------------
# Cleanup helper (scheduler + tests)
# ---------------------------------------------------------------------------

async def cleanup_expired_unattached(session: AsyncSession, now: datetime | None = None) -> int:
    """Delete UNATTACHED proofs (and their objects) older than the TTL. Returns rows removed."""
    now = now or _now()
    cutoff = now - timedelta(hours=settings.outlet_proof_unattached_ttl_hours)
    rows = (
        await session.execute(
            select(OutletProof).where(
                OutletProof.status == OutletProofStatus.UNATTACHED.value,
                OutletProof.created_at < cutoff,
            )
        )
    ).scalars().all()
    for row in rows:
        await _safe_delete_object(row.storage_key)
        await session.delete(row)
    await session.commit()
    if rows:
        logger.info("event=outlet_proof_cleanup removed=%s", len(rows))
    return len(rows)


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------

async def _signed_url(proof: OutletProof) -> str | None:
    try:
        return await storage_service.generate_presigned_url(
            proof.storage_key, settings.outlet_proof_signed_url_minutes
        )
    except Exception:
        return None


async def _submitter_names(session: AsyncSession, proofs: list[OutletProof]) -> dict[uuid.UUID, str]:
    out: dict[uuid.UUID, str] = {}
    uids = {p.submitted_by for p in proofs}
    if not uids:
        return out
    for uid, email in (await session.execute(select(User.id, User.email).where(User.id.in_(uids)))).all():
        out[uid] = email
    for uid, name in (
        await session.execute(select(Employee.user_id, Employee.full_name).where(Employee.user_id.in_(uids)))
    ).all():
        if name:
            out[uid] = name
    return out


def _base_read(proof: OutletProof, names: dict, image_url: str | None) -> OutletProofRead:
    return OutletProofRead(
        id=proof.id,
        customer_id=proof.customer_id,
        prospect_id=proof.prospect_id,
        kind=proof.kind,
        status=proof.status,
        is_primary=proof.is_primary,
        auto_accepted=bool(proof.auto_accepted),
        latitude=proof.latitude,
        longitude=proof.longitude,
        accuracy_m=proof.accuracy_m,
        captured_at=proof.captured_at,
        received_at=proof.received_at,
        is_mock_location=proof.is_mock_location,
        device_info=proof.device_info,
        content_type=proof.content_type,
        size_bytes=proof.size_bytes,
        storage_provider=proof.storage_provider,
        submitted_by=proof.submitted_by,
        submitted_by_name=names.get(proof.submitted_by),
        distance_from_verified_m=proof.distance_from_verified_m,
        reviewed_by=proof.reviewed_by,
        reviewed_at=proof.reviewed_at,
        rejection_reason=proof.rejection_reason,
        image_url=image_url,
        created_at=proof.created_at,
    )


async def to_read(proof: OutletProof, session: AsyncSession) -> OutletProofRead:
    names = await _submitter_names(session, [proof])
    return _base_read(proof, names, await _signed_url(proof))


async def to_reads(proofs: list[OutletProof], session: AsyncSession, admin_extras: bool) -> list[OutletProofRead]:
    names = await _submitter_names(session, proofs)
    reads = [_base_read(p, names, await _signed_url(p)) for p in proofs]
    if not admin_extras or not proofs:
        return reads

    cust_ids = {p.customer_id for p in proofs if p.customer_id}
    info: dict = {}
    if cust_ids:
        rows = (
            await session.execute(
                select(Customer.id, Customer.name, Customer.outlet_code, Customer.location, Territory.name, Area.name)
                .outerjoin(Territory, Territory.id == Customer.territory_id)
                .outerjoin(Area, Area.id == Customer.area_id)
                .where(Customer.id.in_(cust_ids))
            )
        ).all()
        info = {r[0]: r for r in rows}
    pros_ids = {p.prospect_id for p in proofs if p.prospect_id}
    pnames: dict = {}
    if pros_ids:
        pnames = dict(
            (await session.execute(select(CustomerProspect.id, CustomerProspect.name).where(CustomerProspect.id.in_(pros_ids)))).all()
        )
    pending_by_cust: dict = {}
    if cust_ids:
        pend = (
            await session.execute(
                select(OutletProof).where(
                    OutletProof.customer_id.in_(cust_ids),
                    OutletProof.status == OutletProofStatus.PENDING.value,
                )
            )
        ).scalars().all()
        for q in pend:
            pending_by_cust.setdefault(q.customer_id, []).append(q)

    for p, r in zip(proofs, reads):
        row = info.get(p.customer_id)
        if row is not None:
            r.customer_name, r.customer_outlet_code, r.territory_name, r.area_name = row[1], row[2], row[4], row[5]
            if row[3] is not None:
                r.customer_latitude, r.customer_longitude = extract_coords(row[3])
        if p.prospect_id:
            r.prospect_name = pnames.get(p.prospect_id)
        if p.customer_id:
            r.nearby_pending_proofs = sum(
                1
                for q in pending_by_cust.get(p.customer_id, [])
                if q.id != p.id
                and _dist(p.latitude, p.longitude, q.latitude, q.longitude) <= settings.outlet_proof_confirm_radius_m
            )
    return reads


async def list_outlet_proofs(
    session: AsyncSession,
    *,
    status: str | None = None,
    customer_id: uuid.UUID | None = None,
    kind: str | None = None,
    submitted_by: uuid.UUID | None = None,
    skip: int = 0,
    limit: int = 50,
) -> tuple[list[OutletProof], int]:
    filters = []
    if status and status.upper() != "ALL":
        st = status.upper()
        if st not in {s.value for s in OutletProofStatus}:
            raise _err(422, "OUTLET_PROOF_INVALID_FILTER", f"Unknown status '{status}'.")
        filters.append(OutletProof.status == st)
    else:
        # UNATTACHED proofs are an implementation detail of the two-step new-outlet flow.
        filters.append(OutletProof.status != OutletProofStatus.UNATTACHED.value)
    if kind:
        kd = kind.upper()
        if kd not in {k.value for k in OutletProofKind}:
            raise _err(422, "OUTLET_PROOF_INVALID_FILTER", f"Unknown kind '{kind}'.")
        filters.append(OutletProof.kind == kd)
    if customer_id is not None:
        filters.append(OutletProof.customer_id == customer_id)
    if submitted_by is not None:
        filters.append(OutletProof.submitted_by == submitted_by)
    total = (await session.execute(select(func.count(OutletProof.id)).where(*filters))).scalar_one()
    rows = (
        await session.execute(
            select(OutletProof).where(*filters)
            .order_by(OutletProof.received_at.desc(), OutletProof.id)
            .offset(skip).limit(limit)
        )
    ).scalars().all()
    return list(rows), total


async def get_proof_for_viewer(proof_id: uuid.UUID, current_user: User, session: AsyncSession) -> OutletProof:
    """Admin: any proof. Employee: only their own; anything else looks non-existent (404)."""
    proof = (await session.execute(select(OutletProof).where(OutletProof.id == proof_id))).scalar_one_or_none()
    if proof is None or (not current_user.has_global_scope and proof.submitted_by != current_user.id):
        raise _err(404, "OUTLET_PROOF_NOT_FOUND", "Outlet proof not found.")
    return proof


async def read_image_bytes(proof: OutletProof) -> bytes:
    return await storage_service.download(proof.storage_key)


async def primary_proof_for_customer(customer_id: uuid.UUID, session: AsyncSession) -> OutletProof | None:
    return await _approved_primary(session, customer_id)


async def enrich_customer_reads(session: AsyncSession, reads: list) -> None:
    """
    Fill the additive CustomerRead fields (primary_outlet_image_available, primary_outlet_proof_id,
    outlet_proof_count, outlet_location_confirmations) with two grouped queries. Mutates in place.
    """
    ids = [r.id for r in reads]
    if not ids:
        return
    counts = (
        await session.execute(
            select(
                OutletProof.customer_id,
                func.count(OutletProof.id).filter(OutletProof.status.in_(_COUNTED_STATUSES)),
                func.count(OutletProof.id).filter(OutletProof.status == OutletProofStatus.CONFIRMED.value),
            )
            .where(OutletProof.customer_id.in_(ids))
            .group_by(OutletProof.customer_id)
        )
    ).all()
    primary_rows = (
        await session.execute(
            select(OutletProof.customer_id, OutletProof.id, OutletProof.accuracy_m).where(
                OutletProof.customer_id.in_(ids),
                OutletProof.is_primary.is_(True),
                OutletProof.status == OutletProofStatus.APPROVED.value,
            )
        )
    ).all()
    primaries = {row[0]: (row[1], row[2]) for row in primary_rows}
    by_id = {r.id: r for r in reads}
    for cid, total, confirmed in counts:
        by_id[cid].outlet_proof_count = total
        by_id[cid].outlet_location_confirmations = confirmed
    for cid, (pid, pin_acc) in primaries.items():
        by_id[cid].primary_outlet_proof_id = pid
        by_id[cid].primary_outlet_image_available = True
        by_id[cid].outlet_pin_accuracy_m = float(pin_acc) if pin_acc is not None else None

async def attach_outlet_proofs(session, reads):
    """Fill outlet_proof_* on CustomerProspectRead objects from their linked proof (one query)."""
    from sqlalchemy import select
    from app.models.outlet_proof import OutletProof

    ids = [r.id for r in reads]
    if not ids:
        return reads
    rows = (await session.execute(
        select(OutletProof).where(OutletProof.prospect_id.in_(ids)).order_by(OutletProof.created_at.desc())
    )).scalars().all()
    latest = {}
    for pr in rows:
        latest.setdefault(pr.prospect_id, pr)
    for r in reads:
        pr = latest.get(r.id)
        if pr is not None:
            r.outlet_proof_id = pr.id
            r.outlet_proof_accuracy_m = pr.accuracy_m
            r.outlet_proof_captured_at = pr.captured_at
    return reads
