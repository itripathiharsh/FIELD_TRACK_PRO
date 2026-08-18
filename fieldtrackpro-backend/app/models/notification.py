from __future__ import annotations
import enum
import uuid
from typing import Optional
from datetime import datetime
from sqlalchemy import ForeignKey, Enum, String, Text, Boolean, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class NotificationType(str, enum.Enum):
    NEW_VISIT = "NEW_VISIT"
    RESCHEDULED = "RESCHEDULED"
    CANCELLED = "CANCELLED"
    REMINDER = "REMINDER"
    OVERDUE = "OVERDUE"
    COMPLETED = "COMPLETED"
    GEO_FAILURE_ALERT = "GEO_FAILURE_ALERT"
    GEO_ALERT = "GEO_ALERT"


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    visit_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("visits.id", ondelete="SET NULL"), nullable=True)
    type: Mapped[NotificationType] = mapped_column(Enum(NotificationType, name="notification_type_enum"))
    message: Mapped[str] = mapped_column(Text)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="notifications")
    visit: Mapped[Optional["Visit"]] = relationship()
