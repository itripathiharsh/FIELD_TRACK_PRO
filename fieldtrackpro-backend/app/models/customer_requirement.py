from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.customer import Customer
    from app.models.user import User


class CustomerRequirement(Base):
    __tablename__ = "customer_requirements"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    brand: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    requirement_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    product_details: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    quantity: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    expected_value: Mapped[Optional[float]] = mapped_column(Numeric(14, 2), nullable=True)
    follow_up_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True, index=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(50), server_default="OPEN", default="OPEN", nullable=False, index=True)

    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    customer: Mapped["Customer"] = relationship(back_populates="requirements")
    creator_user: Mapped["User"] = relationship("User", foreign_keys=[created_by])
