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
    customer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("customers.id", ondelete="RESTRICT"), index=True)
    employee_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("employees.id", ondelete="RESTRICT"), index=True)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[VisitStatus] = mapped_column(Enum(VisitStatus, name="visit_status_enum"), default=VisitStatus.PENDING, index=True)
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
    # The form template an employee must fill for this visit (Forms-as-a-
    # Visit-workflow fix). Nullable - not every visit requires a form.
    # RESTRICT so a template currently required by a visit can never be
    # deleted out from under it (mirrors how form_templates.submissions
    # already blocks deletion) - only a submission-free DRAFT template with
    # no visits pointing at it is ever actually deletable.
    required_form_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("form_templates.id", ondelete="RESTRICT"), nullable=True, index=True
    )

    employee: Mapped["Employee"] = relationship(back_populates="visits", lazy="joined")
    customer: Mapped["Customer"] = relationship(back_populates="visits", lazy="joined")
    # lazy="joined" to match customer/employee above - required_form_name is
    # read on every visit list/detail response, so it must never trip the
    # async lazy-load trap (MissingGreenlet) that bit this codebase before.
    required_form: Mapped[Optional["FormTemplate"]] = relationship(lazy="joined")
    requirement_form: Mapped[Optional["RequirementForm"]] = relationship(back_populates="visit", uselist=False, cascade="all, delete-orphan")
    media: Mapped[list["VisitMedia"]] = relationship(back_populates="visit", cascade="all, delete-orphan")
    signatures: Mapped[list["VisitSignature"]] = relationship(back_populates="visit", cascade="all, delete-orphan")
    geo_verification_logs: Mapped[list["GeoVerificationLog"]] = relationship(back_populates="visit", cascade="all, delete-orphan")
    # No cascade delete: payments are financial history and must survive even
    # if a visit row were ever removed (the FK is RESTRICT, not CASCADE, so a
    # visit with payments cannot be deleted at all).
    payments: Mapped[list["Payment"]] = relationship(back_populates="visit")

    @property
    def required_form_name(self) -> Optional[str]:
        return self.required_form.name if self.required_form else None

    @property
    def required_form_status(self):
        return self.required_form.status if self.required_form else None
