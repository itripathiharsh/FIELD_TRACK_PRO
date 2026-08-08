from __future__ import annotations
import enum
import uuid
from typing import Optional
from datetime import datetime
from sqlalchemy import (
    BigInteger,
    DateTime,
    Enum,
    ForeignKey,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class MediaType(str, enum.Enum):
    PHOTO = "PHOTO"
    DOCUMENT = "DOCUMENT"


class VisitMedia(Base):
    __tablename__ = "visit_media"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    visit_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("visits.id", ondelete="CASCADE"))
    media_type: Mapped[MediaType] = mapped_column(Enum(MediaType, name="media_type_enum"))
    storage_key: Mapped[str] = mapped_column(String(500), unique=True)
    file_size_bytes: Mapped[int] = mapped_column(BigInteger)

    # FT-036: content integrity and duplicate detection.
    # `checksum_sha256` proves the stored bytes are the bytes that were
    # uploaded; it also lets the service reject the same photograph being
    # re-submitted for a visit (adversarial audit VULN-03: one generic building
    # photo reused as "evidence" across many visits).
    checksum_sha256: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    # Preserved for display/download; never used to build the storage key.
    original_filename: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    uploaded_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    visit: Mapped["Visit"] = relationship(back_populates="media")

    __table_args__ = (
        # The same file content may not be attached to one visit twice.
        UniqueConstraint("visit_id", "checksum_sha256", name="uq_visit_media_content"),
    )
