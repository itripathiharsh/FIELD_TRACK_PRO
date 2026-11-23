from __future__ import annotations
import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class EmployeeCustomerAssignment(Base):
    """
    Direct assignment between an Employee and an Outlet (Customer).
    Enables FOS ↔ Outlet mapping resolved to canonical database IDs (employee_id, customer_id).
    """

    __tablename__ = "employee_customer_assignments"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    employee_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), index=True
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("customers.id", ondelete="CASCADE"), index=True
    )
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Release 3.2 (Tally FOS sync). Rows that existed before are LEGACY (server default); rows the
    # synchronisation owns are TALLY; rows created inside FieldTrack are APP.
    source: Mapped[str] = mapped_column(String(10), nullable=False, default="APP", server_default="LEGACY")
    tally_group: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    tally_ledger_guid: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    synced_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    employee: Mapped["Employee"] = relationship(back_populates="outlet_assignments")
    customer: Mapped["Customer"] = relationship(back_populates="employee_assignments")

    __table_args__ = (
        UniqueConstraint("employee_id", "customer_id", name="uq_employee_customer_assignment"),
    )
