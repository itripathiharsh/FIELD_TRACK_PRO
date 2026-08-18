from typing import Optional
import uuid
from datetime import datetime
from sqlalchemy import String, Float, Integer, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class Territory(Base):
    __tablename__ = "territories"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(100))
    center_latitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    center_longitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    # Whole kilometers only - see app/schemas/territory.py's int typing, which
    # is what actually rejects fractional input at the API boundary.
    radius_km: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(20), server_default="ACTIVE", default="ACTIVE")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    employees: Mapped[list["Employee"]] = relationship(back_populates="territory")
    customers: Mapped[list["Customer"]] = relationship(back_populates="territory")
    # Zone -> Area -> Outlet: the client's real geographic hierarchy has an
    # Area level between Zone (this Territory) and Outlet (Customer) - see
    # app/models/area.py.
    areas: Mapped[list["Area"]] = relationship(back_populates="territory")

