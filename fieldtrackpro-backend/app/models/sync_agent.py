from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class SyncAgent(Base):
    """
    Registered local sync agent instance (e.g. installed on client's Tally machine).
    Authentication is performed via high-entropy API key hashed in the database.
    The backend derives tenant/organization context strictly from this model.
    """
    __tablename__ = "sync_agents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    organization_id: Mapped[str] = mapped_column(String(100), default="default", index=True, nullable=False)
    
    # Hashed agent credential (bcrypt/argon2 or sha256 with salt)
    api_key_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    
    # Target Tally company metadata
    tally_company_guid: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    tally_company_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)
    agent_version: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    
    last_heartbeat_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_sync_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
