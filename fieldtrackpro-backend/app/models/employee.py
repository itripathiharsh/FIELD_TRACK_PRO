from __future__ import annotations
import uuid
from typing import Optional
from datetime import datetime
from sqlalchemy import String, ForeignKey, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class Employee(Base):
    __tablename__ = "employees"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), unique=True)
    full_name: Mapped[str] = mapped_column(String(150))
    territory_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("territories.id", ondelete="SET NULL"), nullable=True)
    employee_code: Mapped[Optional[str]] = mapped_column(String(50), unique=True, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user: Mapped["User"] = relationship(back_populates="employee")
    territory: Mapped[Optional["Territory"]] = relationship(back_populates="employees")
    visits: Mapped[list["Visit"]] = relationship(back_populates="employee")
