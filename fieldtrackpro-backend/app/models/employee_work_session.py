from __future__ import annotations

import enum
import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Date, DateTime, Float, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import ENUM, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.employee import Employee


class WorkSessionStatus(str, enum.Enum):
    NOT_STARTED = "NOT_STARTED"
    STARTED = "STARTED"
    COMPLETED = "COMPLETED"


class EmployeeWorkSession(Base):
    __tablename__ = "employee_work_sessions"
    __table_args__ = (
        UniqueConstraint("employee_id", "work_date", name="uq_employee_work_date"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    employee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("employees.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    work_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    status: Mapped[WorkSessionStatus] = mapped_column(
        ENUM(
            WorkSessionStatus,
            name="work_session_status_enum",
            create_type=False,
            values_callable=lambda e: [i.value for i in e],
        ),
        nullable=False,
        default=WorkSessionStatus.STARTED,
        index=True,
    )

    start_time: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    start_latitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    start_longitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    start_accuracy_meters: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    end_time: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    end_latitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    end_longitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    end_accuracy_meters: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    start_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    end_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    employee: Mapped["Employee"] = relationship("Employee", back_populates="work_sessions")
