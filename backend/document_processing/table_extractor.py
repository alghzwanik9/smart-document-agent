"""Payroll tables read by code, not by the model.

A payroll sheet is mostly one table: a line of column titles and one row per employee. Once it is known which column
holds which field, copying the rows is mechanical, so only the titles (and a few sample rows) ever need a model, and
often not even those: common titles in Arabic and English are matched here. Everything in this module is deterministic.

Tables are found in the text the parsers produce: lines whose cells are joined by `|` (Excel, CSV, Word tables, and the
tables pdfplumber finds in a PDF page). A scanned page or free text has none, and then the caller reads the whole text.
"""
from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass

from core.schemas import AMOUNT_FIELDS, PAYROLL_FIELDS, PayrollRecord, parse_amount

MIN_COLUMNS = 3             # a line of fewer cells is not part of a table (titles, sheet and page markers)
HEADER_SEARCH_LINES = 5     # the titles are among the first lines of a block (a title row or two may come before)
SAMPLE_ROWS = 3             # rows shown to the model with the titles
SAMPLE_CELL_CHARS = 60
MIN_SHARE = 0.5             # a mapping is believed when at least this share of the rows it reads look right
ARITHMETIC_TOLERANCE = 0.01

# Column titles, by the field they hold. Matched after `_key` (case, diacritics, hamza, punctuation and units in brackets
# do not matter) and only as a whole title: "net" is a net salary, "net of tax" is left to the model.
SYNONYMS = {
    "employee_name": ("name", "employee name", "employee", "full name", "staff name", "worker name",
                      "الاسم", "اسم", "اسم الموظف", "الموظف", "اسم العامل", "الاسم الكامل"),
    "employee_id": ("id", "employee id", "emp id", "emp no", "emp number", "employee no", "employee number",
                    "staff id", "staff no", "code", "employee code",
                    "الرقم الوظيفي", "رقم الموظف", "رقم وظيفي", "الرقم", "كود الموظف", "الكود", "الرقم الوظيفى"),
    "period": ("period", "month", "pay period", "payroll month", "الفترة", "الشهر", "شهر", "فترة الراتب"),
    "basic_salary": ("basic", "basic salary", "basic pay", "base salary", "base pay", "الراتب الاساسي", "الاساسي",
                     "اساسي", "الراتب الأساسي", "راتب اساسي"),
    "allowances": ("allowances", "allowance", "total allowances", "البدلات", "بدلات", "اجمالي البدلات", "مجموع البدلات"),
    "deductions": ("deductions", "deduction", "total deductions", "الاستقطاعات", "استقطاعات", "الخصومات", "خصومات",
                   "اجمالي الخصومات", "مجموع الخصومات", "اجمالي الاستقطاعات"),
    "net_salary": ("net", "net salary", "net pay", "net amount", "take home", "take home pay", "الصافي", "صافي",
                   "صافي الراتب", "صافي المستحق", "صافي الاجر", "الراتب الصافي"),
    "currency": ("currency", "العملة", "عملة"),
}
TOTAL_WORDS = ("total", "totals", "grand", "sum", "subtotal", "المجموع", "مجموع", "الاجمالي", "اجمالي", "الاجماليات")


# ---------------------------------------------------------------------- reading the text
@dataclass(frozen=True)
class Table:
    header: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]


def _key(text: str) -> str:
    """A title or a name with the differences that carry no meaning removed, for comparing."""
    text = re.sub(r"[(\[].*?[)\]]", " ", unicodedata.normalize("NFKC", text))       # "Basic (SAR)" is "Basic"
    # NFD splits a hamza or a diacritic off its letter, and the Mn filter drops it: أ إ آ become ا, and ؤ ئ become و ي
    text = "".join(ch for ch in unicodedata.normalize("NFD", text.casefold()) if unicodedata.category(ch) != "Mn")
    text = text.translate(str.maketrans({"ى": "ي", "ة": "ه", "ـ": None}))
    return " ".join(re.sub(r"[^\w]+", " ", text).split())


_SYNONYM_FIELD = {_key(title): field for field, titles in SYNONYMS.items() for title in titles}


def _is_number(cell: str) -> bool:
    if not re.search(r"[0-9٠-٩۰-۹]", cell):     # parse_amount reads "nan" and "inf" as numbers: a name must stay a name
        return False
    try:
        return parse_amount(cell) is not None
    except ValueError:
        return False


def _cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.split("|")]


def find_tables(text: str) -> list[Table]:
    """Each run of lines with several cells, split at its titles. A block with no titles of its own (the next page of
    a table) is read with the titles of the table before it when it has the same number of columns."""
    tables: list[Table] = []
    block: list[list[str]] = []

    def close() -> None:
        if not block:
            return
        start = next((i for i, cells in enumerate(block[:HEADER_SEARCH_LINES])
                      if sum(1 for c in cells if c) >= 2 and not any(_is_number(c) for c in cells)), None)
        if start is not None:
            tables.append(Table(tuple(block[start]), tuple(tuple(r) for r in block[start + 1:])))
        elif tables and len(block[0]) == len(tables[-1].header):
            tables.append(Table(tables[-1].header, tuple(tuple(r) for r in block)))
        block.clear()

    for line in text.splitlines():
        cells = _cells(line) if "|" in line else []
        if len(cells) >= MIN_COLUMNS:
            block.append(cells)
        else:
            close()
    close()
    return tables


def fingerprint(header: tuple[str, ...]) -> str:
    """The identity of a layout: the same titles in the same order are the same layout, whatever the rows say."""
    return hashlib.sha256("\x1f".join(_key(cell) for cell in header).encode()).hexdigest()[:32]


def sample(table: Table) -> list[str]:
    """The titles and the first rows as lines, trimmed: all a model needs to tell the columns apart."""
    lines = [table.header, *table.rows[:SAMPLE_ROWS]]
    return [" | ".join(cell[:SAMPLE_CELL_CHARS] for cell in line) for line in lines]


# ---------------------------------------------------------------------- which column holds what
Mapping = list[str | None]      # one entry per column of the titles: the field it holds, or None


def map_by_synonyms(header: tuple[str, ...]) -> Mapping:
    mapping: Mapping = []
    for cell in header:
        field = _SYNONYM_FIELD.get(_key(cell))
        mapping.append(None if field in mapping else field)     # a title seen twice keeps its first column
    return mapping


def sufficient(mapping: Mapping) -> bool:
    """Enough to be a payroll table: somebody is named and an amount is paid."""
    fields = set(mapping)
    return bool(fields & {"employee_name", "employee_id"}) and bool(fields & {"basic_salary", "net_salary"})


def valid_mapping(columns, width: int) -> Mapping:
    """A model's answer as a mapping, or ValueError: one known field or null per column, none used twice."""
    if not isinstance(columns, list) or len(columns) != width:
        raise ValueError("wrong number of columns")
    seen: set[str] = set()
    for field in columns:
        if field is None:
            continue
        if field not in PAYROLL_FIELDS or field in seen:
            raise ValueError("unknown or repeated field")
        seen.add(field)
    return list(columns)


# ---------------------------------------------------------------------- the rows
def arithmetic_holds(record: PayrollRecord) -> bool | None:
    """basic + allowances - deductions == net, when the sheet gave enough to check; else None."""
    if record.basic_salary is None or record.net_salary is None:
        return None
    expected = record.basic_salary + (record.allowances or 0) - (record.deductions or 0)
    return abs(expected - record.net_salary) <= ARITHMETIC_TOLERANCE


def _is_total(identity: str) -> bool:
    words = _key(identity).split()
    return bool(words) and words[0] in TOTAL_WORDS


def build_records(table: Table, mapping: Mapping) -> list[PayrollRecord]:
    """One record per employee row. A row is skipped when it names nobody, holds no amount, repeats the titles, or
    is a total: it is not an employee."""
    titles = [_key(cell) for cell in table.header]
    records = []
    for row in table.rows:
        if [_key(cell) for cell in row] == titles:
            continue
        values: dict[str, str | float] = {}
        for index, field in enumerate(mapping):
            cell = row[index] if field and index < len(row) else ""
            if not cell:
                continue
            if field in AMOUNT_FIELDS:
                try:
                    amount = parse_amount(cell)
                except ValueError:
                    continue            # "n/a" or "-" is no amount
                if amount is not None:
                    values[field] = amount
            else:
                values[field] = cell
        identity = str(values.get("employee_name") or values.get("employee_id") or "")
        if identity and not _is_total(identity) and any(field in values for field in AMOUNT_FIELDS):
            records.append(PayrollRecord(**values))
    return records


def plausible(records: list[PayrollRecord]) -> bool:
    """Whether a mapping that was not matched by title reads this table sensibly: the name column holds words, and the
    arithmetic of the rows that can be checked mostly holds. A mapping that fails is not trusted, and not kept."""
    if not records:
        return False
    names = [r.employee_name for r in records if r.employee_name]
    if names and sum(1 for n in names if re.search(r"[^\W\d_]", n)) / len(names) < MIN_SHARE:
        return False
    checked = [verdict for verdict in (arithmetic_holds(r) for r in records) if verdict is not None]
    return not checked or sum(checked) / len(checked) >= MIN_SHARE
