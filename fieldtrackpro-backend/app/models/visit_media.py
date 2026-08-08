from __future__ import annotations
import enum
import uuid
from datetime import datetime
from sqlalchemy import ForeignKey, Enum, String, BigInteger, DateTime, func
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
    storage_key: Mapped[str] = mapped_column(String(500))
    file_size_bytes: Mapped[int] = mapped_column(BigInteger)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    visit: Mapped["Visit"] = relationship(back_populates="media")
