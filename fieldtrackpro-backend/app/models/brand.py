from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, DateTime, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.customer_brand import CustomerBrand
    from app.models.payment import PaymentBrandAllocation


class Brand(Base):
    """
    Authoritative centralized Brand entity.
    Enforces normalized case-insensitive uniqueness so variations like
    'USHA', 'usha', 'Usha' map to a single master brand.
    """
    __tablename__ = "brands"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    customer_brands: Mapped[list["CustomerBrand"]] = relationship(back_populates="brand_rel")
    payment_allocations: Mapped[list["PaymentBrandAllocation"]] = relationship(back_populates="brand_rel")
