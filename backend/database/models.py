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
