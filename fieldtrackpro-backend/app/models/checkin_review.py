from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

from geoalchemy2 import Geography
from sqlalchemy import DateTime, ForeignKey, Index, Numeric, String, Text, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class CheckInReviewKind:
    CONDITIONAL = "CONDITIONAL"                 # accepted while uncertain (point estimate inside)
    OFFLINE = "OFFLINE"                         # queued while offline, synced later
    VERIFICATION_REQUEST = "VERIFICATION_REQUEST"  # employee asked an admin to verify (point estimate outside)


class CheckInReviewStatus:
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class CheckInReview(Base):
    """
    Admin review of a check-in whose location could not be confirmed automatically.

    The row is the audit trail: it keeps the employee's fix, the accuracy figures, the decision made at the time and who
    approved or rejected it. It never changes the outlet's coordinates.
    """

    __tablename__ = "checkin_reviews"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    visit_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("visits.id", ondelete="CASCADE"), index=True)
    customer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("customers.id", ondelete="RESTRICT"), index=True)
    employee_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("employees.id", ondelete="SET NULL"), nullable=True)
    requested_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    kind: Mapped[str] = mapped_column(String(24), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="PENDING", default="PENDING")
    decision: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    distance_m: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2), nullable=True)
    accuracy_m: Mapped[Optional[Decimal]] = mapped_column(Numeric(8, 2), nullable=True)
    pin_accuracy_m: Mapped[Optional[Decimal]] = mapped_column(Numeric(8, 2), nullable=True)
    device_location: Mapped[Any] = mapped_column(Geography(geometry_type="POINT", srid=4326))
    device_captured_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    reviewed_by: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    review_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        # Concurrency / duplicate protection: at most one PENDING review of a kind per visit.
        Index("uq_checkin_review_pending", "visit_id", "kind", unique=True, postgresql_where=text("status = 'PENDING'")),
    )
