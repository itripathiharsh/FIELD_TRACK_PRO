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
    # FT-013: the phone number and the human contact are separate concerns. The
    # admin form labelled this column "Contact Person", so a realistic full name
    # overflowed varchar(20) and produced an unhandled 500.
    contact_number: Mapped[str] = mapped_column(String(20))
    contact_person: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    address: Mapped[str] = mapped_column(Text)
    location: Mapped[Any] = mapped_column(Geography(geometry_type="POINT", srid=4326))
    geofence_radius_m: Mapped[int] = mapped_column(Integer, default=75)
    # Stable, human-readable identity for cross-referencing this outlet against
    # external systems (Tally ledger code, Excel/MIS imports). Similarly named
    # retailers (e.g. "Balaji Enterprises" vs "Balaji Electrical") must never be
    # disambiguated by name alone when mapping financial records - this is the
    # anchor for that mapping. The internal `id` remains the canonical FK used
    # by every in-app relationship; this is only for external identity.
    outlet_code: Mapped[Optional[str]] = mapped_column(String(50), unique=True, nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    # Zone. Kept exactly as-is for backward compatibility (existing
    # filtering/import/reporting all key off this) even after `area_id` is
    # set - see app/models/area.py's docstring and customer_service.py for
    # how the two are kept consistent going forward without a customer ever
    # holding a Zone that disagrees with its own Area.
    territory_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("territories.id", ondelete="SET NULL"), nullable=True)
    # Area (Zone -> Area -> Outlet). Nullable: existing outlets have no Area
    # assigned yet - the client's real Zone/Area/Outlet export could not be
    # safely matched to existing Customer rows (see the Meeting 3 audit:
    # outlet identity across brand files is ambiguous), so no historical row
    # was ever auto-assigned an Area. New/updated outlets should be given one
    # going forward.
    area_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("areas.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    territory: Mapped[Optional["Territory"]] = relationship(back_populates="customers")
    # lazy="joined": CustomerRead.from_model reads area.name directly (not
    # just area_id) on every fetch path - this must never hit the
    # MissingGreenlet trap an un-eager-loaded relationship access would
    # trigger in this codebase's async setup (see Visit.employee/customer's
    # identical fix for the same reason).
    area: Mapped[Optional["Area"]] = relationship(back_populates="customers", lazy="joined")
    visits: Mapped[list["Visit"]] = relationship(back_populates="customer")
    invoices: Mapped[list["Invoice"]] = relationship(back_populates="customer")
