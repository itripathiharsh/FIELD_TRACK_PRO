from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any, Optional

from sqlalchemy import JSON, DateTime, Float, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.area import Area
    from app.models.customer import Customer
    from app.models.employee import Employee
    from app.models.territory import Territory
    from app.models.user import User


class ProspectStatus(str, enum.Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class CustomerProspect(Base):
    """
    A new outlet submitted by a field employee, held for admin review before
    it becomes a real Customer row. Unlike CustomerLocationProposal (which
    gates only the GPS pin of an ALREADY-LIVE customer), this gates the
    outlet's existence itself: nothing here is visible as a Customer - no
    directory entry, no assignment, no visits - until an admin approves it.

    Fields mirror CustomerProspectCreate 1:1 so the admin review screen can
    display and EDIT them before approving (fix a typo, assign the right
    outlet code) without the employee having to resubmit.
    """
    __tablename__ = "customer_prospects"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    status: Mapped[ProspectStatus] = mapped_column(
        String(20), nullable=False, default=ProspectStatus.PENDING, server_default="PENDING", index=True
    )

    # Editable outlet fields - same shape as Customer's own columns.
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    contact_number: Mapped[str] = mapped_column(String(20), nullable=False, default="")
    contact_person: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    gst_number: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    address: Mapped[str] = mapped_column(Text, nullable=False, default="")
    outlet_code: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    territory_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("territories.id", ondelete="SET NULL"), nullable=True
    )
    area_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("areas.id", ondelete="SET NULL"), nullable=True
    )
    # list[str] of brand names - same free-text-then-resolved pattern create_customer_prospect
    # already used for a live customer's brands.
    brand_names: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)

    proposed_latitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    proposed_longitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    gps_accuracy_meters: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    location_notes: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # Optional initial requirement/order, held exactly as submitted (dict shaped like
    # CustomerRequirementCreate, minus customer_id/visit_id which don't exist yet) and only
    # materialised into a real CustomerRequirement row when/if this prospect is approved.
    requirement_payload: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)

    submitted_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    submitted_by_employee_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("employees.id", ondelete="SET NULL"), nullable=True
    )
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    reviewed_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    rejection_reason: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Set once APPROVED, for traceability back from the (now real) customer to its origin.
    resulting_customer_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id", ondelete="SET NULL"), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    submitter_user: Mapped["User"] = relationship("User", foreign_keys=[submitted_by])
    submitter_employee: Mapped[Optional["Employee"]] = relationship("Employee", foreign_keys=[submitted_by_employee_id])
    reviewer_user: Mapped[Optional["User"]] = relationship("User", foreign_keys=[reviewed_by])
    resulting_customer: Mapped[Optional["Customer"]] = relationship("Customer", foreign_keys=[resulting_customer_id])
    territory: Mapped[Optional["Territory"]] = relationship("Territory", foreign_keys=[territory_id], lazy="joined")
    area: Mapped[Optional["Area"]] = relationship("Area", foreign_keys=[area_id], lazy="joined")
