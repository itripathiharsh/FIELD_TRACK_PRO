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
    contact_number: Mapped[str] = mapped_column(String(20))
    address: Mapped[str] = mapped_column(Text)
    location: Mapped[Any] = mapped_column(Geography(geometry_type="POINT", srid=4326))
    geofence_radius_m: Mapped[int] = mapped_column(Integer, default=75)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    territory_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("territories.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    territory: Mapped[Optional["Territory"]] = relationship(back_populates="customers")
    visits: Mapped[list["Visit"]] = relationship(back_populates="customer")
