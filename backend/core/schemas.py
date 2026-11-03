"""Pydantic schemas: the payroll extraction the LLM must fill, and the shapes of the API."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

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


class PayrollExtraction(BaseModel):
    model_config = ConfigDict(extra="ignore")

    records: list[PayrollRecord] = Field(default_factory=list)


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
