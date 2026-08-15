"""
Employee-Territory assignment history (P2-D).

`Employee.territory_id` remains a plain FK - a cheap fallback for employees
who predate this feature or have never been explicitly reassigned. Once an
admin creates the first assignment row for an employee, this table becomes
the source of truth for "what territory is this employee working right now",
resolved at read time (see territory_assignment_service.get_effective_territory_id)
rather than by overwriting that column - so a permanent reassignment that
takes effect in the future, or a temporary one that expires on its own, both
resolve correctly without a scheduled job, and no historical visit's
territory context is ever rewritten.
"""
from __future__ import annotations

import enum
import uuid
from datetime import date, datetime
from typing import Optional

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Index, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class AssignmentType(str, enum.Enum):
    PERMANENT = "PERMANENT"
    TEMPORARY = "TEMPORARY"


class EmployeeTerritoryAssignment(Base):
    __tablename__ = "employee_territory_assignments"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    employee_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), index=True
    )
    # RESTRICT, not SET NULL: unlike the live Employee.territory_id pointer,
    # a history row must never silently lose which territory it recorded.
    territory_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("territories.id", ondelete="RESTRICT"))
    assignment_type: Mapped[AssignmentType] = mapped_column(Enum(AssignmentType, name="assignment_type_enum"))
    start_date: Mapped[date] = mapped_column(Date)
    # Required for TEMPORARY, must be null for PERMANENT - enforced in the
    # service layer since it depends on assignment_type.
    end_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    employee: Mapped["Employee"] = relationship()
    territory: Mapped["Territory"] = relationship()

    __table_args__ = (
        Index("ix_employee_territory_assignments_employee_start", "employee_id", "start_date"),
    )
