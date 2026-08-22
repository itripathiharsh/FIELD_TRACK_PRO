from __future__ import annotations
import uuid
from typing import Any, Optional
from datetime import datetime
from sqlalchemy import String, Integer, ForeignKey, Text, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from geoalchemy2 import Geography
from app.database import Base


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(150))
    # FT-013: phone number and human contact are separate concerns.
    contact_number: Mapped[str] = mapped_column(String(20), default="")
    contact_person: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    address: Mapped[str] = mapped_column(Text, default="")
    location: Mapped[Optional[Any]] = mapped_column(Geography(geometry_type="POINT", srid=4326), nullable=True)
    geofence_radius_m: Mapped[int] = mapped_column(Integer, default=75)
    
    # Location status: VERIFIED, NEEDS_REVIEW, MISSING
    location_status: Mapped[str] = mapped_column(String(30), server_default="MISSING", default="MISSING")
    
    # Stable external code (DMS Code / External MIS anchor)
    outlet_code: Mapped[Optional[str]] = mapped_column(String(50), unique=True, nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    
    # Zone (Territory) & Area
    territory_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("territories.id", ondelete="SET NULL"), nullable=True)
    area_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("areas.id", ondelete="SET NULL"), nullable=True, index=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    territory: Mapped[Optional["Territory"]] = relationship(back_populates="customers")
    area: Mapped[Optional["Area"]] = relationship(back_populates="customers", lazy="joined")
    visits: Mapped[list["Visit"]] = relationship(back_populates="customer")
    invoices: Mapped[list["Invoice"]] = relationship(back_populates="customer")
    
    employee_assignments: Mapped[list["EmployeeCustomerAssignment"]] = relationship(
        back_populates="customer", cascade="all, delete-orphan"
    )
    financial_snapshots: Mapped[list["OutletFinancialSnapshot"]] = relationship(
        back_populates="customer", cascade="all, delete-orphan"
    )
