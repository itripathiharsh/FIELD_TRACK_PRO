from __future__ import annotations
import uuid
from typing import Optional
from datetime import date, datetime
from sqlalchemy import String, ForeignKey, DateTime, Date, Boolean, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class Employee(Base):
    __tablename__ = "employees"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), unique=True)
    full_name: Mapped[str] = mapped_column(String(150))
    territory_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("territories.id", ondelete="SET NULL"), nullable=True)
    employee_code: Mapped[Optional[str]] = mapped_column(String(50), unique=True, nullable=True)
    
    # Real business client fields
    working_profile: Mapped[Optional[str]] = mapped_column(String(100), nullable=True) # e.g. FOS, TSE, Sales Manager, ASM, etc.
    cug: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    date_of_birth: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    address: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Optional secured PII fields (not exposed publicly)
    father_name: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    mother_name: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    aadhaar_no: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    pan_no: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user: Mapped["User"] = relationship(back_populates="employee")
    territory: Mapped[Optional["Territory"]] = relationship(back_populates="employees")
    visits: Mapped[list["Visit"]] = relationship(back_populates="employee")
    outlet_assignments: Mapped[list["EmployeeCustomerAssignment"]] = relationship(
        back_populates="employee", cascade="all, delete-orphan"
    )
