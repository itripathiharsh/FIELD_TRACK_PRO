from __future__ import annotations
import enum
import uuid
from datetime import datetime
from sqlalchemy import ForeignKey, Enum, String, Text, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class Priority(str, enum.Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class RequirementForm(Base):
    __tablename__ = "requirement_forms"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    visit_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("visits.id", ondelete="CASCADE"), unique=True)
    category_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("requirement_categories.id", ondelete="RESTRICT"))
    description: Mapped[str] = mapped_column(Text)
    priority: Mapped[Priority] = mapped_column(Enum(Priority, name="priority_enum"))
    expected_timeline: Mapped[str] = mapped_column(String(100))
    budget_range: Mapped[str | None] = mapped_column(String(100), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    visit: Mapped["Visit"] = relationship(back_populates="requirement_form")
    category: Mapped["RequirementCategory"] = relationship(back_populates="requirement_forms")
