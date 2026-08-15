from __future__ import annotations
import enum
import uuid
from typing import Optional
from datetime import datetime
from sqlalchemy import BigInteger, ForeignKey, Enum, Index, String, DateTime, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class SignatureType(str, enum.Enum):
    EMPLOYEE = "EMPLOYEE"
    CUSTOMER = "CUSTOMER"


class SignatureCaptureMethod(str, enum.Enum):
    # Drawn on-screen (existing finger-drawn canvas).
    SIGNATURE = "SIGNATURE"
    # A photo of an already-signed physical document/acknowledgement, not a
    # cryptographic signature - just an attached photo.
    PHOTO_UPLOAD = "PHOTO_UPLOAD"


class VisitSignature(Base):
    __tablename__ = "visit_signatures"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    visit_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("visits.id", ondelete="CASCADE"))
    signature_type: Mapped[SignatureType] = mapped_column(Enum(SignatureType, name="signature_type_enum"))
    capture_method: Mapped[SignatureCaptureMethod] = mapped_column(
        Enum(SignatureCaptureMethod, name="signature_capture_method_enum"),
        default=SignatureCaptureMethod.SIGNATURE,
        server_default=SignatureCaptureMethod.SIGNATURE.value,
    )
    storage_key: Mapped[str] = mapped_column(String(500))
    # Nullable: rows captured before this column existed cannot be retroactively
    # verified without re-reading their stored bytes, so historical rows are
    # left NULL rather than guessed. Every row created going forward always
    # populates these (enforced in signature_service, not the DB) - the same
    # server_default-free convention already used by VisitMedia.checksum_sha256.
    content_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    file_size_bytes: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    checksum_sha256: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    # Who actually submitted this row (always a real login - EMPLOYEE or
    # ADMIN; customers have no account of their own). This is an honest audit
    # trail of who captured the evidence, not proof of who physically held
    # the pen - see signature_service's docstring on upload_signature.
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    signed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # NULL = this is the current/active signature for its (visit, type).
    # Replacing a signature sets this instead of deleting the row or its
    # storage blob, so a corrected capture never destroys the prior evidence.
    superseded_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    visit: Mapped["Visit"] = relationship(back_populates="signatures")

    __table_args__ = (
        # Only one CURRENT signature per (visit, type) - historical
        # (superseded) rows for the same pair are allowed to coexist, since
        # replacing a signature inserts a new row rather than overwriting.
        Index(
            "uq_visit_signature_current",
            "visit_id",
            "signature_type",
            unique=True,
            postgresql_where=text("superseded_at IS NULL"),
        ),
    )
