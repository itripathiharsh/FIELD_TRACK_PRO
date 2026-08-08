from __future__ import annotations
import enum
import uuid
from typing import Any, Optional
from datetime import datetime
from sqlalchemy import ForeignKey, Enum, DateTime, func, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship
from geoalchemy2 import Geography
from app.database import Base


class VisitStatus(str, enum.Enum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    MISSED = "MISSED"
    FLAGGED = "FLAGGED"


class Visit(Base):
    __tablename__ = "visits"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    customer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("customers.id", ondelete="RESTRICT"))
    employee_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("employees.id", ondelete="RESTRICT"))
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[VisitStatus] = mapped_column(Enum(VisitStatus, name="visit_status_enum"), default=VisitStatus.PENDING)
    check_in_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    check_in_location: Mapped[Optional[Any]] = mapped_column(Geography(geometry_type="POINT", srid=4326), nullable=True)
    check_out_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    check_out_location: Mapped[Optional[Any]] = mapped_column(Geography(geometry_type="POINT", srid=4326), nullable=True)
    synced: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    employee: Mapped["Employee"] = relationship(back_populates="visits", lazy="joined")
    customer: Mapped["Customer"] = relationship(back_populates="visits", lazy="joined")
    requirement_form: Mapped[Optional["RequirementForm"]] = relationship(back_populates="visit", uselist=False, cascade="all, delete-orphan")
    media: Mapped[list["VisitMedia"]] = relationship(back_populates="visit", cascade="all, delete-orphan")
    signatures: Mapped[list["VisitSignature"]] = relationship(back_populates="visit", cascade="all, delete-orphan")
    geo_verification_logs: Mapped[list["GeoVerificationLog"]] = relationship(back_populates="visit", cascade="all, delete-orphan")
