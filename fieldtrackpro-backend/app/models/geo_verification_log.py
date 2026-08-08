from __future__ import annotations
import enum
import uuid
from typing import Any
from datetime import datetime
from decimal import Decimal
from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from geoalchemy2 import Geography
from app.database import Base


class GeoVerificationType(str, enum.Enum):
    """
    Which lifecycle event produced the verification attempt.

    FT-031: without this an admin reviewing the audit trail cannot tell a
    check-in attempt from a check-out attempt.
    """

    CHECK_IN = "CHECK_IN"
    CHECK_OUT = "CHECK_OUT"


class GeoVerificationLog(Base):
    """
    Immutable record of one location verification attempt.

    Insert-only by policy (Security Design section 4). Application database
    privileges revoke UPDATE and DELETE on this table (FT-032), so the audit
    trail cannot be rewritten by the API even if application logic is wrong.
    """

    __tablename__ = "geo_verification_logs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    visit_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("visits.id", ondelete="CASCADE"))
    verification_type: Mapped[GeoVerificationType] = mapped_column(
        Enum(GeoVerificationType, name="geo_verification_type_enum"),
        default=GeoVerificationType.CHECK_IN,
        server_default=GeoVerificationType.CHECK_IN.value,
    )
    attempted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    device_location: Mapped[Any] = mapped_column(Geography(geometry_type="POINT", srid=4326))
    distance_from_customer_m: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    is_valid: Mapped[bool] = mapped_column(Boolean)
    failure_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(255), nullable=True)

    visit: Mapped["Visit"] = relationship(back_populates="geo_verification_logs")

    __table_args__ = (
        # FT-033: a retried check-in must not create a second audit row.
        UniqueConstraint("visit_id", "idempotency_key", name="uq_geo_log_visit_idempotency"),
    )
