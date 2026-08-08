from __future__ import annotations
import enum
import uuid
from datetime import datetime
from sqlalchemy import ForeignKey, Enum, String, DateTime, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class SignatureType(str, enum.Enum):
    EMPLOYEE = "EMPLOYEE"
    CUSTOMER = "CUSTOMER"


class VisitSignature(Base):
    __tablename__ = "visit_signatures"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    visit_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("visits.id", ondelete="CASCADE"))
    signature_type: Mapped[SignatureType] = mapped_column(Enum(SignatureType, name="signature_type_enum"))
    storage_key: Mapped[str] = mapped_column(String(500))
    signed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    visit: Mapped["Visit"] = relationship(back_populates="signatures")

    __table_args__ = (
        UniqueConstraint("visit_id", "signature_type", name="uq_visit_signature"),
    )
