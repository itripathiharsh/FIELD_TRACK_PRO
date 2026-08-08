from __future__ import annotations
import uuid
from typing import Any
from datetime import datetime
from decimal import Decimal
from sqlalchemy import ForeignKey, DateTime, Numeric, Boolean, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from geoalchemy2 import Geography
from app.database import Base


class GeoVerificationLog(Base):
    __tablename__ = "geo_verification_logs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    visit_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("visits.id", ondelete="CASCADE"))
    attempted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    device_location: Mapped[Any] = mapped_column(Geography(geometry_type="POINT", srid=4326))
    distance_from_customer_m: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    is_valid: Mapped[bool] = mapped_column(Boolean)
    failure_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(255), nullable=True)

    visit: Mapped["Visit"] = relationship(back_populates="geo_verification_logs")
