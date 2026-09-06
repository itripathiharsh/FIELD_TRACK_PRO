from __future__ import annotations

import enum
import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import ENUM, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.requirement_form import Priority
from app.models.visit import VisitType

if TYPE_CHECKING:
    from app.models.customer import Customer
    from app.models.employee import Employee
    from app.models.user import User


class MonthlyPlanStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    LOCKED = "LOCKED"


class PlannedVisitStatus(str, enum.Enum):
    PLANNED = "PLANNED"
    CANCELLED = "CANCELLED"
    COMPLETED = "COMPLETED"
    MISSED = "MISSED"


class MonthlyVisitPlan(Base):
    __tablename__ = "monthly_visit_plans"
    __table_args__ = (
        UniqueConstraint("employee_id", "year", "month", name="uq_monthly_visit_plan_employee_year_month"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    employee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("employees.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    year: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    month: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    status: Mapped[MonthlyPlanStatus] = mapped_column(
        ENUM(
            MonthlyPlanStatus,
            name="monthly_plan_status_enum",
            create_type=False,
            values_callable=lambda e: [i.value for i in e],
        ),
        nullable=False,
        default=MonthlyPlanStatus.ACTIVE,
        server_default=MonthlyPlanStatus.ACTIVE.value,
    )
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    employee: Mapped["Employee"] = relationship("Employee", back_populates="monthly_plans", lazy="joined")
    creator: Mapped["User"] = relationship("User", foreign_keys=[created_by], lazy="selectin")
    planned_visits: Mapped[list["PlannedVisit"]] = relationship(
        "PlannedVisit",
        back_populates="monthly_plan",
        cascade="all, delete-orphan",
        order_by="PlannedVisit.planned_date.asc()",
        lazy="selectin",
    )


class PlannedVisit(Base):
    __tablename__ = "planned_visits"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    monthly_plan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("monthly_visit_plans.id", ondelete="CASCADE"), nullable=False, index=True
    )
    employee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("employees.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    planned_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    visit_type: Mapped[VisitType] = mapped_column(
        ENUM(
            VisitType,
            name="visit_type_enum",
            create_type=False,
            values_callable=lambda e: [i.value for i in e],
        ),
        nullable=False,
        default=VisitType.PLANNED,
        server_default=VisitType.PLANNED.value,
    )
    priority: Mapped[Priority] = mapped_column(
        ENUM(
            Priority,
            name="priority_enum",
            create_type=False,
            values_callable=lambda e: [i.value for i in e],
        ),
        nullable=False,
        default=Priority.MEDIUM,
        server_default=Priority.MEDIUM.value,
    )
    notes: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    status: Mapped[PlannedVisitStatus] = mapped_column(
        ENUM(
            PlannedVisitStatus,
            name="planned_visit_status_enum",
            create_type=False,
            values_callable=lambda e: [i.value for i in e],
        ),
        nullable=False,
        default=PlannedVisitStatus.PLANNED,
        server_default=PlannedVisitStatus.PLANNED.value,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    monthly_plan: Mapped["MonthlyVisitPlan"] = relationship("MonthlyVisitPlan", back_populates="planned_visits")
    employee: Mapped["Employee"] = relationship("Employee", foreign_keys=[employee_id], lazy="joined")
    customer: Mapped["Customer"] = relationship("Customer", foreign_keys=[customer_id], lazy="joined")

    @property
    def customer_name(self) -> str:
        try:
            return self.customer.name if self.customer else ""
        except Exception:
            return ""

    @property
    def customer_outlet_code(self) -> Optional[str]:
        try:
            return self.customer.outlet_code if self.customer else None
        except Exception:
            return None

    @property
    def customer_address(self) -> str:
        try:
            return self.customer.address if self.customer else ""
        except Exception:
            return ""

    @property
    def employee_name(self) -> str:
        try:
            return self.employee.full_name if self.employee else ""
        except Exception:
            return ""

    @property
    def employee_code(self) -> Optional[str]:
        try:
            return self.employee.employee_code if self.employee else None
        except Exception:
            return None

    @property
    def area_name(self) -> Optional[str]:
        try:
            return self.customer.area.name if self.customer and self.customer.area else None
        except Exception:
            return None

    @property
    def territory_name(self) -> Optional[str]:
        try:
            return self.customer.territory.name if self.customer and self.customer.territory else None
        except Exception:
            return None
