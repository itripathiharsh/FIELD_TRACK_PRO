"""
Tally -> FieldTrack FOS assignment synchronisation (release 3.2).

In this client's Tally the FOS (field salesperson) of a customer is the PARENT GROUP of the customer's ledger:
every FOS has one ledger group per brand ("Raunak Usha", "Raunak ZBR", "Sahil Gautam (Usha)" ...) and the
outlet ledgers sit inside those groups. The agent already exports every ledger's parent group; the backend stores
it on tally_debtor_ledgers.parent_group / customers.tally_parent_group.

Three tables, all additive:
  tally_fos_groups      one row per Tally ledger group that holds outlet ledgers, and what it means
                        (MAPPED to an employee, NOT_FOS = not a salesperson group, or UNMAPPED = awaiting an admin)
  fos_assignment_audit  one row per change (or conflict) the synchronisation made or found, with the Tally identity
  fos_sync_runs         one row per synchronisation run (dry run or apply) with its counters
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

# tally_fos_groups.status
GROUP_UNMAPPED = "UNMAPPED"
GROUP_MAPPED = "MAPPED"
GROUP_NOT_FOS = "NOT_FOS"

# employee_customer_assignments.source
SRC_LEGACY = "LEGACY"  # created before the Tally synchronisation existed (seed / import); kept until reconciled
SRC_TALLY = "TALLY"    # owned by the synchronisation: follows the customer's Tally group
SRC_APP = "APP"        # created inside FieldTrack (e.g. an employee's own prospect outlet)

# customers.fos_status
ST_ASSIGNED = "ASSIGNED"
ST_MULTIPLE = "MULTIPLE"              # more than one FOS (different groups of the same shop)
ST_UNASSIGNED = "UNASSIGNED"          # Tally says: no FOS (the ledger sits in a non-FOS group)
ST_UNMAPPED_GROUP = "UNMAPPED_GROUP"  # the Tally group is not mapped to an employee yet (existing access is kept)
ST_CONFLICT = "CONFLICT"              # a pre-sync assignment disagrees with Tally (kept until approved)
ST_NO_TALLY = "NO_TALLY"              # no in-scope Tally debtor ledger (e.g. a prospect not yet in Tally)
ALL_STATUSES = (ST_ASSIGNED, ST_MULTIPLE, ST_UNASSIGNED, ST_UNMAPPED_GROUP, ST_CONFLICT, ST_NO_TALLY)


class TallyFosGroup(Base):
    __tablename__ = "tally_fos_groups"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    group_key: Mapped[str] = mapped_column(String(150), unique=True, index=True)  # normalised, see fos_logic
    group_name: Mapped[str] = mapped_column(String(150))                         # as Tally spells it
    status: Mapped[str] = mapped_column(String(10), nullable=False, default=GROUP_UNMAPPED, server_default=GROUP_UNMAPPED)
    employee_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("employees.id", ondelete="SET NULL"), nullable=True, index=True)
    suggested_employee_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("employees.id", ondelete="SET NULL"), nullable=True)
    suggestion_basis: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    decided_by: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    decided_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    note: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class FosSyncRun(Base):
    __tablename__ = "fos_sync_runs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    trigger: Mapped[str] = mapped_column(String(16), nullable=False)  # LEDGER_SYNC | ADMIN | GROUP_MAPPING | CLI
    dry_run: Mapped[bool] = mapped_column(nullable=False, default=False)
    legacy_policy: Mapped[str] = mapped_column(String(12), nullable=False, default="REPORT_ONLY")
    status: Mapped[str] = mapped_column(String(10), nullable=False, default="RUNNING")  # RUNNING | COMPLETE | FAILED
    triggered_by: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    summary: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)


class FosAssignmentAudit(Base):
    __tablename__ = "fos_assignment_audit"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    run_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("fos_sync_runs.id", ondelete="SET NULL"), nullable=True, index=True)
    customer_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("customers.id", ondelete="SET NULL"), nullable=True, index=True)
    customer_name: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    previous_employee_id: Mapped[Optional[uuid.UUID]] = mapped_column(nullable=True)
    previous_fos: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    new_employee_id: Mapped[Optional[uuid.UUID]] = mapped_column(nullable=True)
    new_fos: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    action: Mapped[str] = mapped_column(String(24), nullable=False)
    source: Mapped[str] = mapped_column(String(12), nullable=False, default="TALLY", server_default="TALLY")
    tally_group: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    tally_ledger_guid: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    result: Mapped[str] = mapped_column(String(16), nullable=False, default="APPLIED", server_default="APPLIED")
    detail: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)

    __table_args__ = (Index("ix_fos_audit_customer_created", "customer_id", "created_at"),)
