from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, ForeignKey, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.customer import Customer
    from app.models.customer_requirement import CustomerRequirement
    from app.models.employee import Employee
    from app.models.order_item import OrderItem
    from app.models.user import User
    from app.models.visit import Visit


class Order(Base):
    """
    A confirmed customer order resulting from an approved CustomerRequirement.
    Enters tally_writeback_queue as CREATE_SALES_ORDER to post to TallyPrime.
    """
    __tablename__ = "orders"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_number: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    
    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    requirement_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customer_requirements.id", ondelete="SET NULL"), nullable=True, index=True
    )
    visit_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("visits.id", ondelete="SET NULL"), nullable=True, index=True
    )
    employee_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("employees.id", ondelete="SET NULL"), nullable=True, index=True
    )

    total_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=Decimal("0.00"))
    
    # Status: PENDING_TALLY, SENT_TO_TALLY, TALLY_CONFIRMED, TALLY_FAILED, CANCELLED
    status: Mapped[str] = mapped_column(String(50), default="PENDING_TALLY", nullable=False, index=True)
    
    # Tally confirmation details
    tally_guid: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    tally_master_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    tally_voucher_number: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    admin_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    customer: Mapped["Customer"] = relationship()
    employee: Mapped[Optional["Employee"]] = relationship()
    visit: Mapped[Optional["Visit"]] = relationship()
    requirement: Mapped[Optional["CustomerRequirement"]] = relationship()
    creator_user: Mapped["User"] = relationship("User", foreign_keys=[created_by])
    items: Mapped[list["OrderItem"]] = relationship(back_populates="order", cascade="all, delete-orphan")
