from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.brand import Brand
    from app.models.customer_requirement import CustomerRequirement


class RequirementItem(Base):
    """
    Individual line item within a CustomerRequirement.
    Enables multi-item demand capture per visit (e.g. Samsung S25 x3, A16 x5).
    """
    __tablename__ = "requirement_items"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    requirement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customer_requirements.id", ondelete="CASCADE"), nullable=False, index=True
    )
    brand_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("brands.id", ondelete="SET NULL"), nullable=True, index=True
    )
    brand_name: Mapped[str] = mapped_column(String(100), nullable=False)
    product_model: Mapped[str] = mapped_column(String(200), nullable=False)
    
    # Rep's requested values
    requested_quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    expected_rate: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=Decimal("0.00"))
    requested_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=Decimal("0.00"))

    # Admin approved values (decided during review)
    approved_quantity: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    approved_rate: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 2), nullable=True)
    approved_amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 2), nullable=True)

    # Optional mapping to exact Tally stock item name for automated write-back
    tally_stock_item_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    requirement: Mapped["CustomerRequirement"] = relationship(back_populates="items")
    brand_rel: Mapped[Optional["Brand"]] = relationship()
