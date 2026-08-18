from __future__ import annotations
import uuid
from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class EmployeeAreaAssignment(Base):
    """
    An employee's coverage of one Area - many-to-many, brand-agnostic.

    The client's real data (Meeting 3 audit) confirms one employee routinely
    covers many Areas across many Zones - the old model (Employee.territory_id
    / EmployeeTerritoryAssignment: one effective Zone per employee at a time)
    cannot represent that and is NOT being replaced here; it's left exactly as
    it was for backward compatibility (login session shape, existing
    reassignment history/reporting). This table is the new, additive answer
    to "which outlets does this employee currently cover" - anything that
    needs that answer going forward should join through here, not through
    Employee.territory_id.

    No brand dimension: confirmed with the client that FieldTrack's own
    employee/visit model has no brand concept and coverage should stay
    brand-agnostic, even though the source Excel data was brand-scoped.
    """

    __tablename__ = "employee_area_assignments"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    employee_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), index=True
    )
    area_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("areas.id", ondelete="CASCADE"), index=True
    )
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    employee: Mapped["Employee"] = relationship()
    area: Mapped["Area"] = relationship()

    __table_args__ = (
        UniqueConstraint("employee_id", "area_id", name="uq_employee_area_assignment"),
    )
