from __future__ import annotations
import uuid
from typing import Optional
from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class FOSEmployeeMapping(Base):
    """
    Persistent mapping between raw source FOS names (e.g., 'Sahil', 'RAUNAK', 'YOGESH')
    and FieldTrack employee accounts. Reusable across future Excel/MIS uploads.
    """

    __tablename__ = "fos_employee_mappings"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    raw_fos_name: Mapped[str] = mapped_column(String(150), unique=True, index=True)
    employee_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    employee: Mapped["Employee"] = relationship()
