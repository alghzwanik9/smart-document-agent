"""SQLAlchemy models for `documents`, `extracted_fields`, `feedback_loop` and `layout_mappings`."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

STATUSES = ("pending", "processing", "completed", "failed")


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    filename: Mapped[str] = mapped_column(Text, nullable=False)
    file_type: Mapped[str] = mapped_column(Text, nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    stored_path: Mapped[str] = mapped_column(Text, nullable=False)
    upload_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="pending", index=True)
    error_message: Mapped[str | None] = mapped_column(Text)

    fields: Mapped[list["ExtractedField"]] = relationship(
        back_populates="document", cascade="all, delete-orphan", passive_deletes=True,
        order_by="ExtractedField.record_index, ExtractedField.id",
    )


class ExtractedField(Base):
    __tablename__ = "extracted_fields"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    record_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    field_name: Mapped[str] = mapped_column(Text, nullable=False)
    original_value: Mapped[str | None] = mapped_column(Text)
    corrected_value: Mapped[str | None] = mapped_column(Text)
    is_corrected: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    confidence: Mapped[float | None] = mapped_column()
    extraction_model_version: Mapped[str | None] = mapped_column(Text)

    document: Mapped[Document] = relationship(back_populates="fields")


class FeedbackLoop(Base):
    """One user correction kept as a learning example. The vector lives in ChromaDB under `vector_id`."""

    __tablename__ = "feedback_loop"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    field_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("extracted_fields.id", ondelete="CASCADE"), nullable=False, index=True
    )
    document_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    field_name: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    original_value: Mapped[str | None] = mapped_column(Text)
    corrected_value: Mapped[str] = mapped_column(Text, nullable=False)
    correction_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)
    vector_id: Mapped[str | None] = mapped_column(Text)


class LayoutMapping(Base):
    """Which field each column of a payroll table holds, learned once per layout (the same column titles in the same
    order) so the model is never asked about that layout again."""

    __tablename__ = "layout_mappings"

    fingerprint: Mapped[str] = mapped_column(Text, primary_key=True)
    columns: Mapped[str] = mapped_column(Text, nullable=False)      # JSON list: a field name or null per column
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)
    use_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


# ---------------------------------------------------------------------- Yahya Intelligent Office System Models
CASE_STATUSES = {"NEW", "ANL", "WAI", "RDY", "CLS", "HLD"}
CASE_DOMAINS = {"PAY", "LEG", "AUD", "COR"}
RELATION_TYPES = {"REL-PARENT", "REL-MERGED", "REL-RELATED", "REL-PRECEDENT", "REL-SAME-PERSON"}


class PersonRecord(Base):
    __tablename__ = "person_records"

    per_id: Mapped[str] = mapped_column(Text, primary_key=True)
    employee_number: Mapped[str | None] = mapped_column(Text, index=True, nullable=True)
    full_name: Mapped[str] = mapped_column(Text, index=True, nullable=False)
    national_id_hash: Mapped[str | None] = mapped_column(Text, index=True, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)

    cases: Mapped[list["CaseRecord"]] = relationship(back_populates="person", cascade="all, delete-orphan")


class CaseRecord(Base):
    __tablename__ = "case_records"

    case_id: Mapped[str] = mapped_column(Text, primary_key=True)
    per_id: Mapped[str] = mapped_column(
        Text, ForeignKey("person_records.per_id", ondelete="CASCADE"), nullable=False, index=True
    )
    subject: Mapped[str] = mapped_column(Text, nullable=False)
    domain: Mapped[str] = mapped_column(Text, nullable=False, default="PAY", index=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="NEW", index=True)
    priority: Mapped[str] = mapped_column(Text, nullable=False, default="P2")
    statutory_deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    close_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    document_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("documents.id", ondelete="SET NULL"), nullable=True, index=True
    )
    reference_number: Mapped[str | None] = mapped_column(Text, nullable=True, index=True)
    monetary_amount: Mapped[float | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)

    person: Mapped[PersonRecord] = relationship(back_populates="cases")
    events: Mapped[list["CaseEvent"]] = relationship(
        back_populates="case", cascade="all, delete-orphan", order_by="CaseEvent.id"
    )
    document: Mapped[Document | None] = relationship()
    outgoing_relations: Mapped[list["CaseRelation"]] = relationship(
        foreign_keys="CaseRelation.source_case_id", back_populates="source_case", cascade="all, delete-orphan"
    )
    incoming_relations: Mapped[list["CaseRelation"]] = relationship(
        foreign_keys="CaseRelation.target_case_id", back_populates="target_case", cascade="all, delete-orphan"
    )


class CaseEvent(Base):
    __tablename__ = "case_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    case_id: Mapped[str] = mapped_column(
        Text, ForeignKey("case_records.case_id", ondelete="CASCADE"), nullable=False, index=True
    )
    ev_id: Mapped[str] = mapped_column(Text, nullable=False)
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    old_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    new_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)

    case: Mapped[CaseRecord] = relationship(back_populates="events")


class CaseRelation(Base):
    __tablename__ = "case_relations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_case_id: Mapped[str] = mapped_column(
        Text, ForeignKey("case_records.case_id", ondelete="CASCADE"), nullable=False, index=True
    )
    target_case_id: Mapped[str] = mapped_column(
        Text, ForeignKey("case_records.case_id", ondelete="CASCADE"), nullable=False, index=True
    )
    relation_type: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)

    source_case: Mapped[CaseRecord] = relationship(foreign_keys=[source_case_id], back_populates="outgoing_relations")
    target_case: Mapped[CaseRecord] = relationship(foreign_keys=[target_case_id], back_populates="incoming_relations")

