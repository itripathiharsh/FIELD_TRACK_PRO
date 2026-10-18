"""
Outlet proof: a LIVE photo of an outlet and the GPS fix taken at that same
click, stored as ONE bundle so the two corroborate each other.

Used for (A) new outlets (a prospect) and (B) existing outlets whose location
is missing/unverified or being corrected. See app/services/outlet_proof_service.py.

Lifecycle (status):
  UNATTACHED  uploaded for a not-yet-submitted new outlet; expires after
              settings.outlet_proof_unattached_ttl_hours (cleanup helper deletes it)
  PENDING     waiting for admin review (INITIAL / CHANGE_REQUEST)
  APPROVED    the accepted proof; is_primary marks the one that sets the official pin/photo
  CONFIRMED   a later proof within the confirm radius of the verified pin (no admin action)
  SUPERSEDED  was APPROVED/CONFIRMED but a newer approved proof replaced the location
  REJECTED    admin rejected it (object kept for audit)
No absolute URLs are ever stored - only storage_key + storage_provider.
"""
from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class OutletProofKind(str, enum.Enum):
    INITIAL = "INITIAL"
    CONFIRMATION = "CONFIRMATION"
    CHANGE_REQUEST = "CHANGE_REQUEST"


class OutletProofStatus(str, enum.Enum):
    UNATTACHED = "UNATTACHED"
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    SUPERSEDED = "SUPERSEDED"
    CONFIRMED = "CONFIRMED"


class OutletProof(Base):
    __tablename__ = "outlet_proofs"
    __table_args__ = (
        CheckConstraint(
            "status = 'UNATTACHED' OR customer_id IS NOT NULL OR prospect_id IS NOT NULL",
            name="ck_outlet_proofs_has_target",
        ),
        UniqueConstraint("submitted_by", "idempotency_key", name="uq_outlet_proofs_submitter_idem"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    customer_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id", ondelete="CASCADE"), nullable=True, index=True
    )
    prospect_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customer_prospects.id", ondelete="SET NULL"), nullable=True, index=True
    )

    kind: Mapped[str] = mapped_column(String(20), nullable=False, default=OutletProofKind.INITIAL.value)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=OutletProofStatus.PENDING.value, index=True
    )
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")

    storage_key: Mapped[str] = mapped_column(Text, nullable=False)
    storage_provider: Mapped[str] = mapped_column(String(20), nullable=False, default="LOCAL")
    content_type: Mapped[str] = mapped_column(String(100), nullable=False, default="image/jpeg")
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    accuracy_m: Mapped[float] = mapped_column(Float, nullable=False)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    is_mock_location: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    device_info: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)

    submitted_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    submitted_by_employee_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("employees.id", ondelete="SET NULL"), nullable=True
    )
    reviewed_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    rejection_reason: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    distance_from_verified_m: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    submitter_user = relationship("User", foreign_keys=[submitted_by])
    submitter_employee = relationship("Employee", foreign_keys=[submitted_by_employee_id])
