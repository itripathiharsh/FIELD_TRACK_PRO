from __future__ import annotations
import uuid
from sqlalchemy import String, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class RequirementCategory(Base):
    __tablename__ = "requirement_categories"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(100))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    requirement_forms: Mapped[list["RequirementForm"]] = relationship(back_populates="category")
