"""AI-derived analysis kept separate from the original email content."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import (
    EmailCategory,
    EmailPriority,
    EmailSentiment,
    ExtractedField,
    ProcessingStatus,
)
from app.core.utils import utcnow
from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.email import Email


class EmailAnalysis(Base, TimestampMixin):
    """One validated AI analysis row per email (1:1)."""

    __tablename__ = "email_analysis"
    __table_args__ = (
        UniqueConstraint("email_id", name="uq_email_analysis_email_id"),
        Index("ix_email_analysis_user_id_category", "user_id", "category"),
        Index("ix_email_analysis_user_id_priority", "user_id", "priority"),
        Index("ix_email_analysis_user_id_sentiment", "user_id", "sentiment"),
        Index("ix_email_analysis_user_id_reply_required", "user_id", "reply_required"),
        Index("ix_email_analysis_user_id_action_required", "user_id", "action_required"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email_id: Mapped[int] = mapped_column(
        ForeignKey("emails.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    # Owner copy enables user-scoped aggregation without joining through emails.
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Classification -----------------------------------------------------
    category: Mapped[str] = mapped_column(
        String(40), nullable=False, default=EmailCategory.other.value, server_default=EmailCategory.other.value
    )
    category_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    intent: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    priority: Mapped[str] = mapped_column(
        String(20), nullable=False, default=EmailPriority.medium.value, server_default=EmailPriority.medium.value
    )
    priority_reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    sentiment: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=EmailSentiment.neutral.value,
        server_default=EmailSentiment.neutral.value,
    )
    sentiment_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    reply_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    action_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")

    # Summaries ------------------------------------------------------------
    summary_short: Mapped[str] = mapped_column(Text, nullable=False, default="")
    summary_detailed: Mapped[str] = mapped_column(Text, nullable=False, default="")
    key_points: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    unresolved_issues: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    # Provenance -----------------------------------------------------------
    provider: Mapped[str] = mapped_column(String(40), nullable=False, default="unknown")
    model: Mapped[str] = mapped_column(String(80), nullable=False, default="unknown")
    prompt_version: Mapped[str] = mapped_column(String(32), nullable=False, default="v1")
    schema_version: Mapped[str] = mapped_column(String(32), nullable=False, default="v1")
    processing_status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=ProcessingStatus.completed.value
    )
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    analysis_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    analyzed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    email: Mapped[Email] = relationship(back_populates="analysis", lazy="joined")
    entities: Mapped[list[ExtractedEntity]] = relationship(
        back_populates="analysis", cascade="all, delete-orphan", lazy="selectin"
    )


class ExtractedEntity(Base):
    """Key/value extracted details; keeps raw phrase plus normalised value."""

    __tablename__ = "extracted_entities"
    __table_args__ = (
        Index("ix_extracted_entities_user_id_field", "user_id", "field"),
        Index("ix_extracted_entities_email_id", "email_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    analysis_id: Mapped[int] = mapped_column(
        ForeignKey("email_analysis.id", ondelete="CASCADE"), nullable=False, index=True
    )
    email_id: Mapped[int] = mapped_column(ForeignKey("emails.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    field: Mapped[str] = mapped_column(String(40), nullable=False)
    value_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # ISO-8601 date/datetime or machine-readable number when normalisable.
    value_normalized: Mapped[str | None] = mapped_column(String(64), nullable=True)
    raw_phrase: Mapped[str | None] = mapped_column(String(255), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    evidence: Mapped[str | None] = mapped_column(Text, nullable=True)

    analysis: Mapped[EmailAnalysis] = relationship(back_populates="entities")

    @staticmethod
    def coerce_field(value: str) -> str:
        """Map a free-form field name onto a known key, else ``other``."""
        candidate = str(value or "").strip().lower().replace(" ", "_").replace("-", "_")
        known = {m.value for m in ExtractedField}
        if candidate in known:
            return candidate
        # Accept enum member names too (`EMAIL`, `OrderNumber`, ...).
        member = ExtractedField.__members__.get(candidate)
        return member.value if member else "other"
