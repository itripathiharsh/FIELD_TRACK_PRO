from __future__ import annotations
import uuid
from datetime import datetime
from sqlalchemy import String, ForeignKey, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class Area(Base):
    """
    The geographic layer between a Zone (Territory) and an Outlet (Customer):
    client hierarchy is Zone -> Area -> Outlet -> Employee assignment. Added
    because Territory alone was being used to approximate two real levels at
    once - confirmed against the client's actual Zone/Area/Outlet export
    (Meeting 3 audit), which showed both levels genuinely exist and an
    outlet's Area is not the same thing as its Zone.

    Deliberately no case-insensitive DB uniqueness constraint on (territory_id,
    name): the source data shows real spelling/casing inconsistencies
    ("Kanpur nagar" vs "Kanpur Nagar" vs "Kanapur Nagar") that must be
    resolved by an admin reviewing them, never silently merged by a
    constraint. `area_service.create_area` does a case-insensitive check on
    create and surfaces a clear conflict instead.
    """

    __tablename__ = "areas"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(150))
    territory_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("territories.id", ondelete="RESTRICT"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # lazy="joined": to_area_read reads territory.name directly on every
    # fetch path - must never hit the MissingGreenlet trap an un-eager-loaded
    # relationship access would trigger (see Customer.area's identical fix).
    territory: Mapped["Territory"] = relationship(back_populates="areas", lazy="joined")
    customers: Mapped[list["Customer"]] = relationship(back_populates="area")
