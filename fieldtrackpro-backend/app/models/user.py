from __future__ import annotations
import enum
import uuid
from typing import Optional
from datetime import datetime
from sqlalchemy import String, Boolean, Enum, DateTime, Integer, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class Role(str, enum.Enum):
    """
    Authorization roles, least to most privileged: EMPLOYEE < ADMIN < SUPER_ADMIN.

    ACCOUNTANT sits outside that ladder: a web-only, READ-ONLY role for the financial reports and
    collections (``FINANCE_READ_ROLES``). It is admitted only where an endpoint lists it explicitly,
    never inherits ADMIN or EMPLOYEE access, and only a Super Admin may create it.

    SUPER_ADMIN is a strict superset of ADMIN (every admin-only endpoint also accepts it) plus
    role management. It is never assigned through signup, user creation or import: only the
    bootstrap script and the Super-Admin-only role-change endpoint can grant it.
    """

    SUPER_ADMIN = "SUPER_ADMIN"
    ADMIN = "ADMIN"
    EMPLOYEE = "EMPLOYEE"
    ACCOUNTANT = "ACCOUNTANT"


#: Roles that hold administrative (global-access) privileges. Use this - never `== Role.ADMIN` -
#: when deciding "is this caller an administrator?".
ADMIN_ROLES: tuple[Role, ...] = (Role.ADMIN, Role.SUPER_ADMIN)

#: Roles that may READ the financial reports and collections (no writes, no user management).
FINANCE_READ_ROLES: tuple[Role, ...] = (Role.ADMIN, Role.SUPER_ADMIN, Role.ACCOUNTANT)


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    email: Mapped[Optional[str]] = mapped_column(String(255), unique=True, nullable=True)
    mobile_number: Mapped[Optional[str]] = mapped_column(String(20), unique=True, nullable=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[Role] = mapped_column(Enum(Role, name="role_enum"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # Bumped whenever the account's sessions must die at once (admin password reset, role change):
    # access tokens carry the value they were issued under and are rejected on mismatch.
    token_version: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    # Set only while an admin-issued temporary password is pending. NULL = no temporary password
    # (legacy "initial password" accounts flagged via employees.must_change_password never expire).
    temp_password_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    employee: Mapped["Employee"] = relationship(back_populates="user", uselist=False, cascade="all, delete-orphan")
    refresh_tokens: Mapped[list["RefreshToken"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    notifications: Mapped[list["Notification"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    devices: Mapped[list["UserDevice"]] = relationship(back_populates="user", cascade="all, delete-orphan")

    @property
    def is_admin(self) -> bool:
        """True for ADMIN and SUPER_ADMIN."""
        return self.role in ADMIN_ROLES

    @property
    def has_global_scope(self) -> bool:
        """
        True for ADMIN, SUPER_ADMIN and ACCOUNTANT: sees every record (not only an employee's own scope).
        This is about SCOPE only. What an accountant may WRITE is decided centrally by the route policy
        (app.core.deps.auth.accountant_may); security decisions (password resets, role changes, account
        deletion) keep using ``is_admin``.
        """
        return self.role in ADMIN_ROLES or self.role == Role.ACCOUNTANT

    @property
    def is_super_admin(self) -> bool:
        return self.role == Role.SUPER_ADMIN
