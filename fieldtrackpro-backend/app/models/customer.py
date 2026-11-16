from __future__ import annotations
import uuid
from typing import Any, Optional
from datetime import datetime
from decimal import Decimal
from datetime import date
from sqlalchemy import String, Integer, ForeignKey, Text, DateTime, Date, Boolean, Numeric, func
from sqlalchemy.dialects.postgresql import JSONB
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
    gst_number: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, index=True)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))

    # Tally debtor-ledger identity: stable across ledger renames (matched first by the sync).
    tally_guid: Mapped[Optional[str]] = mapped_column(String(255), unique=True, nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    mobile_number: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    # The ledger closing balance exactly as Tally exported it at the last sync (signed
    # as Tally signs it). A reference / cross-check figure; it never drives outstanding.
    tally_closing_balance: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 2), nullable=True)
    tally_closing_balance_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    # Tally v2 ledger master facts (all exactly as Tally reports them; never inferred).
    # tally_is_debtor: True = ledger under Sundry Debtors; False = a Tally ledger that is
    # NOT a debtor (bank, supplier, expense ...) and so not an outlet - hidden from outlet
    # lists, never deleted; None = not (yet) seen in a full Tally ledger snapshot.
    tally_is_debtor: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True, index=True)
    tally_parent_group: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    tally_aliases: Mapped[Optional[list[str]]] = mapped_column(JSONB, nullable=True)
    tally_is_bill_wise: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    tally_credit_period: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    # Ledger opening balance = position at the start of Tally's current period
    # (tally_opening_balance_as_of, e.g. 2026-04-01 = the 31-03-2026 closing). Signed as Tally.
    tally_opening_balance: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 2), nullable=True)
    tally_opening_balance_as_of: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    # Set True only for an outlet approved from a CustomerProspect submission (there is no
    # Tally writeback for customers - Tally sync is import-only - so an admin must add it to
    # Tally by hand). False for every pre-existing/Tally-imported/admin-direct-created row;
    # this is a persistent reminder, not a one-time message, because admins approving several
    # outlets in a row can easily forget one by the time they get to Tally.
    needs_tally_entry: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    tally_entry_marked_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    tally_entry_marked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    
    # Zone (Territory) & Area
    territory_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("territories.id", ondelete="SET NULL"), nullable=True)
    area_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("areas.id", ondelete="SET NULL"), nullable=True, index=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    territory: Mapped[Optional["Territory"]] = relationship(back_populates="customers", lazy="joined")
    area: Mapped[Optional["Area"]] = relationship(back_populates="customers", lazy="joined")
    visits: Mapped[list["Visit"]] = relationship(back_populates="customer")
    invoices: Mapped[list["Invoice"]] = relationship(back_populates="customer")
    
    employee_assignments: Mapped[list["EmployeeCustomerAssignment"]] = relationship(
        back_populates="customer", cascade="all, delete-orphan"
    )
    financial_snapshots: Mapped[list["OutletFinancialSnapshot"]] = relationship(
        back_populates="customer", cascade="all, delete-orphan"
    )
    location_proposals: Mapped[list["CustomerLocationProposal"]] = relationship(
        back_populates="customer", cascade="all, delete-orphan", lazy="selectin"
    )
    brands: Mapped[list["CustomerBrand"]] = relationship(
        back_populates="customer", cascade="all, delete-orphan", lazy="selectin"
    )
    requirements: Mapped[list["CustomerRequirement"]] = relationship(
        back_populates="customer", cascade="all, delete-orphan", lazy="selectin"
    )
