from __future__ import annotations
import enum
import uuid
from typing import Optional
from datetime import datetime
from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class ExceptionType(str, enum.Enum):
    VEHICLE_BREAKDOWN = "VEHICLE_BREAKDOWN"
    GPS_UNAVAILABLE = "GPS_UNAVAILABLE"
    OUTLET_CLOSED = "OUTLET_CLOSED"
    CUSTOMER_UNAVAILABLE = "CUSTOMER_UNAVAILABLE"
    OTHER = "OTHER"


class ExceptionStatus(str, enum.Enum):
    PENDING_REVIEW = "PENDING_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class FieldException(Base):
    """
    Field operational exceptions filed by employees when legitimate issues
    prevent normal check-in or visit execution (e.g. breakdown, GPS failure, closed outlet).
    Admins can review, approve, or reject each exception with notes.
    """

    __tablename__ = "field_exceptions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    visit_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("visits.id", ondelete="SET NULL"), nullable=True, index=True
    )
    employee_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("employees.id", ondelete="RESTRICT"), index=True
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("customers.id", ondelete="RESTRICT"), index=True
    )

    exception_type: Mapped[ExceptionType] = mapped_column(
        Enum(ExceptionType, name="field_exception_type_enum"), index=True
    )
    description: Mapped[str] = mapped_column(Text)
    status: Mapped[ExceptionStatus] = mapped_column(
        Enum(ExceptionStatus, name="field_exception_status_enum"),
        default=ExceptionStatus.PENDING_REVIEW,
        index=True,
    )

    admin_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    reviewed_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    visit: Mapped[Optional["Visit"]] = relationship(lazy="joined")
    employee: Mapped["Employee"] = relationship(lazy="joined")
    customer: Mapped["Customer"] = relationship(lazy="joined")
    reviewer: Mapped[Optional["User"]] = relationship(
        foreign_keys=[reviewed_by], lazy="joined"
    )
