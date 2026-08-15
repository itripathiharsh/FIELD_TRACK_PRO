from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class LoginAttempt(Base):
    """
    A single failed-login record (P1-3).

    Backs the login rate limiter via the shared database rather than
    in-process memory, so the budget is enforced identically no matter which
    backend worker/process handles a given request - the previous in-memory
    counter let an attacker bypass the limit simply by being routed to a
    different worker. Rows are deleted on a successful login (clearing the
    identifier's budget) or naturally excluded once they age out of the
    sliding window; there is no separate cleanup job.
    """

    __tablename__ = "login_attempts"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    # Normalised (stripped + lowercased) email/mobile identifier - never the
    # raw casing a client happened to send, so the budget cannot be evaded by
    # varying case.
    identifier: Mapped[str] = mapped_column(String(255))
    attempted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_login_attempts_identifier_attempted_at", "identifier", "attempted_at"),
    )
