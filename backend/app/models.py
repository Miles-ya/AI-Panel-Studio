from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Discussion(Base):
    __tablename__ = "discussions"
    __table_args__ = (
        CheckConstraint("expert_count BETWEEN 2 AND 8", name="ck_discussion_expert_count"),
        CheckConstraint("max_public_utterances = 15", name="ck_discussion_max_utterances"),
        CheckConstraint(
            "status IN ('DRAFT', 'CAST_READY', 'RUNNING', 'FINISHED', 'FAILED')",
            name="ck_discussion_status",
        ),
        CheckConstraint(
            "summary_status IN ('pending', 'succeeded', 'fallback')",
            name="ck_discussion_summary_status",
        ),
        CheckConstraint("length(trim(topic)) BETWEEN 1 AND 300", name="ck_discussion_topic"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    topic: Mapped[str] = mapped_column(String(300), nullable=False)
    expert_count: Mapped[int] = mapped_column(Integer, nullable=False, default=4)
    max_public_utterances: Mapped[int] = mapped_column(Integer, nullable=False, default=15)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    cast_confirmed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    cast_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    summary: Mapped[str | None] = mapped_column(Text)
    summary_status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    error_code: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Participant(Base):
    __tablename__ = "participants"
    __table_args__ = (
        UniqueConstraint("discussion_id", "id", name="uq_participant_discussion_id"),
        UniqueConstraint("discussion_id", "color", name="uq_participant_color"),
        CheckConstraint("role IN ('moderator', 'expert')", name="ck_participant_role"),
        CheckConstraint(
            "runtime_status IN ('idle', 'preparing', 'speaking')",
            name="ck_participant_runtime_status",
        ),
        CheckConstraint(
            "color GLOB '#[0-9A-Fa-f][0-9A-Fa-f][0-9A-Fa-f][0-9A-Fa-f][0-9A-Fa-f][0-9A-Fa-f]'",
            name="ck_participant_color_hex",
        ),
        CheckConstraint(
            "public_focus IS NULL OR length(public_focus) <= 50",
            name="ck_participant_public_focus_length",
        ),
        Index("ix_participants_discussion_id", "discussion_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    discussion_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("discussions.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    profession: Mapped[str] = mapped_column(String(100), nullable=False)
    title: Mapped[str] = mapped_column(String(150), nullable=False)
    stance: Mapped[str] = mapped_column(String(300), nullable=False)
    color: Mapped[str] = mapped_column(String(7), nullable=False)
    runtime_status: Mapped[str] = mapped_column(String(16), nullable=False, default="idle")
    public_focus: Mapped[str | None] = mapped_column(String(50))
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Utterance(Base):
    __tablename__ = "utterances"
    __table_args__ = (
        ForeignKeyConstraint(
            ["discussion_id", "participant_id"],
            ["participants.discussion_id", "participants.id"],
            ondelete="CASCADE",
            name="fk_utterance_same_discussion_participant",
        ),
        UniqueConstraint("discussion_id", "sequence", name="uq_utterance_discussion_sequence"),
        CheckConstraint("sequence >= 1", name="ck_utterance_sequence"),
        CheckConstraint("length(trim(content)) BETWEEN 1 AND 300", name="ck_utterance_content"),
        Index("ix_utterances_discussion_id", "discussion_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    discussion_id: Mapped[str] = mapped_column(String(36), nullable=False)
    participant_id: Mapped[str] = mapped_column(String(36), nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class Insight(Base):
    __tablename__ = "insights"
    __table_args__ = (
        CheckConstraint(
            "type IN ('consensus', 'disagreement')", name="ck_insight_type"
        ),
        Index("ix_insights_discussion_id", "discussion_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    discussion_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("discussions.id", ondelete="CASCADE"), nullable=False
    )
    type: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(String(300), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
