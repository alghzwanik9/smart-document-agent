"""Pydantic schemas: the payroll extraction the LLM must fill, and the shapes of the API."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

_ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹٫", "01234567890123456789.")
_THOUSANDS = str.maketrans("", "", ",  ٬")


def parse_amount(value: Any) -> float | None:
    """'5,000' and '٥٠٠٠' are 5000; null and blank stay None; anything else is an error for the retry."""
    if value is None or isinstance(value, bool):
        return None if value is None else _reject(value)
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).translate(_ARABIC_DIGITS).translate(_THOUSANDS)
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return _reject(value)


def format_amount(value: float) -> str:
    """The one spelling of an amount that is stored: 5300.0 is '5300', 5400.5 is '5400.5'."""
    return str(int(value)) if float(value).is_integer() else repr(value)


def _reject(value: Any):
    raise ValueError(f"not an amount: {value!r}")


class PayrollRecord(BaseModel):
    """One employee in a payroll sheet. Everything is optional: what the sheet does not state stays empty."""

    model_config = ConfigDict(extra="ignore")

    employee_name: str | None = None
    employee_id: str | None = None
    period: str | None = Field(default=None, description="The month or period the sheet pays for, as written")
    basic_salary: float | None = None
    allowances: float | None = None
    deductions: float | None = None
    net_salary: float | None = None
    currency: str | None = None

    @field_validator("employee_name", "employee_id", "period", "currency", mode="before")
    @classmethod
    def _text(cls, value: Any) -> Any:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @field_validator("basic_salary", "allowances", "deductions", "net_salary", mode="before")
    @classmethod
    def _amount(cls, value: Any) -> float | None:
        return parse_amount(value)


class ValidationWarning(BaseModel):
    """A data quality or deterministic validation warning flagged during extraction."""

    model_config = ConfigDict(extra="ignore")

    warning_type: str
    message: str
    record_index: int | None = None
    field_name: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class PayrollExtraction(BaseModel):
    model_config = ConfigDict(extra="ignore")

    records: list[PayrollRecord] = Field(default_factory=list)
    warnings: list[ValidationWarning] = Field(default_factory=list)


PAYROLL_FIELDS = tuple(PayrollRecord.model_fields)
AMOUNT_FIELDS = ("basic_salary", "allowances", "deductions", "net_salary")


class FieldDraft(BaseModel):
    """A value taken from a document, before it is stored as a row of `extracted_fields`."""

    record_index: int
    field_name: str
    value: str
    confidence: float


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    filename: str
    file_type: str
    file_size: int
    upload_date: datetime
    status: str
    error_message: str | None = None


class DocumentPage(BaseModel):
    items: list[DocumentOut]
    total: int
    page: int
    page_size: int


class UploadAccepted(BaseModel):
    document_id: int
    status: str


class FieldCorrection(BaseModel):
    corrected_value: str = Field(max_length=500)
    reason: str | None = Field(default=None, max_length=500)


class ExtractedFieldOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    document_id: int
    record_index: int
    field_name: str
    original_value: str | None = None
    corrected_value: str | None = None
    is_corrected: bool
    confidence: float | None = None
    extraction_model_version: str | None = None


@dataclass(frozen=True)
class LearnedCorrection:
    """A value the system got wrong once and the user's fix for it, offered to the next extraction as an example."""

    field_name: str
    original_value: str
    corrected_value: str


class CorrectionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    field_id: int
    document_id: int
    field_name: str
    original_value: str | None = None
    corrected_value: str
    correction_date: datetime


class CorrectionPage(BaseModel):
    items: list[CorrectionOut]
    total: int
    page: int
    page_size: int


class AnalyticsSummary(BaseModel):
    documents_total: int
    documents_by_type: dict[str, int]
    documents_by_status: dict[str, int]
    fields_total: int
    average_confidence: float | None = None
    corrections_total: int
    corrected_by_field: dict[str, int]


# ---------------------------------------------------------------------- Yahya Intelligent Office System Schemas
class PersonCreate(BaseModel):
    employee_number: str | None = None
    full_name: str
    national_id: str | None = None


class PersonOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    per_id: str
    employee_number: str | None = None
    full_name: str
    created_at: datetime


class CaseEventCreateRequest(BaseModel):
    event_type: str = "COMMENT"
    description: str
    old_value: str | None = None
    new_value: str | None = None
    reason: str | None = None


class CaseEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    case_id: str
    ev_id: str
    event_type: str
    description: str
    old_value: str | None = None
    new_value: str | None = None
    reason: str | None = None
    created_at: datetime


class CaseRelationCreateRequest(BaseModel):
    target_case_id: str
    relation_type: str


class CaseRelationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source_case_id: str
    target_case_id: str
    relation_type: str
    created_at: datetime


class CaseCreateRequest(BaseModel):
    per_id: str | None = None
    employee_number: str | None = None
    full_name: str | None = None
    national_id: str | None = None
    subject: str
    domain: str = "PAY"
    priority: str = "P2"
    statutory_deadline: datetime | None = None
    reference_number: str | None = None
    monetary_amount: float | None = None
    document_id: int | None = None
    initial_event_description: str | None = None


class CaseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    case_id: str
    per_id: str
    subject: str
    domain: str
    status: str
    priority: str
    statutory_deadline: datetime | None = None
    close_reason: str | None = None
    document_id: int | None = None
    reference_number: str | None = None
    monetary_amount: float | None = None
    created_at: datetime


class CaseDetailOut(CaseOut):
    person: PersonOut | None = None
    events: list[CaseEventOut] = Field(default_factory=list)
    outgoing_relations: list[CaseRelationOut] = Field(default_factory=list)
    incoming_relations: list[CaseRelationOut] = Field(default_factory=list)


class IntakeEvaluationRequest(BaseModel):
    employee_number: str | None = None
    full_name: str
    national_id: str | None = None
    subject: str
    reference_number: str | None = None
    monetary_amount: float | None = None
    statutory_deadline: datetime | None = None
    domain: str = "PAY"
    document_id: int | None = None


class SimilarCaseSummary(BaseModel):
    case_id: str
    subject: str
    per_id: str
    status: str
    last_event: str | None = None
    matched_fields: list[str] = Field(default_factory=list)
    differences: list[str] = Field(default_factory=list)


class IntakeEvaluationResult(BaseModel):
    decision: Literal["NO_MATCH", "SIMILAR_FOUND", "SAME_PERSON_NEW_TOPIC"]
    suggested_priority: str
    business_days_remaining: int | None = None
    person: PersonOut | None = None
    similar_cases: list[SimilarCaseSummary] = Field(default_factory=list)
    reason: str


class YahyaHierarchyOut(BaseModel):
    per_id: str
    employee_number: str | None = None
    full_name: str
    created_at: datetime
    cases: list[CaseDetailOut] = Field(default_factory=list)

