"""Payroll tables read by code, not by the model.

A payroll sheet is mostly one table: a line of column titles and one row per employee. Once it is known which column
holds which field, copying the rows is mechanical, so only the titles (and a few sample rows) ever need a model, and
often not even those: common titles in Arabic and English are matched here. Everything in this module is deterministic.

Tables are found in the text the parsers produce: lines whose cells are joined by `|` (Excel, CSV, Word tables, and the
tables pdfplumber finds in a PDF page). A scanned page or free text has none, and then the caller reads the whole text.
"""
from __future__ import annotations

import hashlib
import itertools
import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Sequence

from rapidfuzz import fuzz, process

from core.schemas import AMOUNT_FIELDS, PAYROLL_FIELDS, PayrollRecord, ValidationWarning, parse_amount

MIN_COLUMNS = 3             # a line of fewer cells is not part of a table (titles, sheet and page markers)
HEADER_SEARCH_LINES = 5     # the titles are among the first lines of a block (a title row or two may come before)
SAMPLE_ROWS = 3             # rows shown to the model with the titles
SAMPLE_CELL_CHARS = 60
MIN_SHARE = 0.5             # a mapping is believed when at least this share of the rows it reads look right
ARITHMETIC_TOLERANCE = 0.05
ARITHMETIC_DISCREPANCY_THRESHOLD = 0.05

# Column titles, by the field they hold. Matched after `_key` (case, diacritics, hamza, punctuation and units in brackets
# do not matter) and only as a whole title: "net" is a net salary, "net of tax" is left to the model.
SYNONYMS = {
    "employee_name": ("name", "employee name", "employee", "full name", "staff name", "worker name",
                      "الاسم", "اسم", "اسم الموظف", "الموظف", "اسم العامل", "الاسم الكامل", "اسم الموظفين"),
    "employee_id": ("id", "employee id", "emp id", "emp no", "emp number", "employee no", "employee number",
                    "staff id", "staff no", "code", "employee code",
                    "الرقم الوظيفي", "رقم الموظف", "رقم وظيفي", "الرقم", "كود الموظف", "الكود", "الرقم الوظيفى",
                    "رقم العامل", "كود العامل"),
    "period": ("period", "month", "pay period", "payroll month", "الفترة", "الشهر", "شهر", "فترة الراتب"),
    "basic_salary": ("basic", "basic salary", "basic pay", "base salary", "base pay", "basic sal", "base",
                     "الراتب الاساسي", "الاساسي", "اساسي", "الراتب الأساسي", "راتب اساسي"),
    "allowances": ("allowances", "allowance", "total allowances", "allw", "allow",
                   "البدلات", "بدلات", "اجمالي البدلات", "مجموع البدلات", "بدل", "البدل"),
    "deductions": ("deductions", "deduction", "total deductions", "deduct",
                   "الاستقطاعات", "استقطاعات", "الخصومات", "خصومات",
                   "اجمالي الخصومات", "مجموع الخصومات", "اجمالي الاستقطاعات", "خصم", "الخصم"),
    "net_salary": ("net", "net salary", "net pay", "net amount", "take home", "take home pay",
                   "الصافي", "صافي", "صافي الراتب", "صافي المستحق", "صافي الاجر", "الراتب الصافي", "صافي مستحق"),
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


CANONICAL_PAYROLL_FIELDS = (
    "employee_id",
    "employee_name",
    "basic_salary",
    "allowances",
    "deductions",
    "net_salary",
)


def map_by_fuzzy_headers(
    header: tuple[str, ...] | Sequence[str],
    threshold: float = 82.0,
    canonical_fields: Sequence[str] = CANONICAL_PAYROLL_FIELDS,
) -> Mapping:
    """Fuzzy matching of column titles against canonical payroll entities using RapidFuzz.

    Uses `fuzz.token_set_ratio` with a strict similarity threshold (default 82.0) to match
    variations, typos, and abbreviations across Arabic and English. Employs greedy assignment
    by similarity score so no column is mapped to multiple fields and no canonical field is
    assigned to multiple columns.
    """
    if not header:
        return []

    variant_to_field: dict[str, str] = {}
    field_variants: dict[str, list[str]] = {f: [] for f in canonical_fields}
    for field in canonical_fields:
        if field in SYNONYMS:
            for variant in SYNONYMS[field]:
                k = _key(variant)
                if k:
                    variant_to_field[k] = field
                    if k not in field_variants[field]:
                        field_variants[field].append(k)

    if not variant_to_field:
        return [None] * len(header)

    candidates: list[tuple[int, str, float]] = []
    for col_idx, cell in enumerate(header):
        cleaned = _key(str(cell))
        if not cleaned:
            continue
        # Direct exact match check
        if cleaned in variant_to_field:
            candidates.append((col_idx, variant_to_field[cleaned], 100.0))
            continue
        # Check against each canonical field
        for field in canonical_fields:
            choices = field_variants[field]
            if not choices:
                continue
            res = process.extractOne(
                cleaned,
                choices,
                scorer=fuzz.token_set_ratio,
                score_cutoff=threshold,
            )
            if res is not None:
                candidates.append((col_idx, field, float(res[1])))

    # Greedy assignment: sort primarily by score descending.
    # Tie-breaking: earlier column index first (-col_idx with reverse=True).
    candidates.sort(key=lambda x: (x[2], -x[0]), reverse=True)
    mapping: Mapping = [None] * len(header)
    assigned_cols: set[int] = set()
    assigned_fields: set[str] = set()

    for col_idx, field, score in candidates:
        if col_idx not in assigned_cols and field not in assigned_fields:
            mapping[col_idx] = field
            assigned_cols.add(col_idx)
            assigned_fields.add(field)

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


# ---------------------------------------------------------------------- deterministic data quality checks
def check_arithmetic_discrepancy(
    record: PayrollRecord,
    index: int,
    threshold: float = ARITHMETIC_TOLERANCE,
) -> ValidationWarning | None:
    """Flags arithmetic discrepancies where abs((basic + allowances - deductions) - net) > threshold."""
    if record.basic_salary is None or record.net_salary is None:
        return None
    expected = record.basic_salary + (record.allowances or 0.0) - (record.deductions or 0.0)
    discrepancy = abs(expected - record.net_salary)
    if discrepancy > threshold:
        return ValidationWarning(
            warning_type="arithmetic_discrepancy",
            message=(
                f"Arithmetic mismatch in record {index}: basic ({record.basic_salary}) + "
                f"allowances ({record.allowances or 0.0}) - deductions ({record.deductions or 0.0}) = "
                f"{expected:.2f}, but net salary is {record.net_salary:.2f} (discrepancy: {discrepancy:.2f})"
            ),
            record_index=index,
            field_name="net_salary",
            details={
                "expected": round(expected, 4),
                "actual": round(record.net_salary, 4),
                "discrepancy": round(discrepancy, 4),
            },
        )
    return None


def check_duplicate_ids(records: Sequence[PayrollRecord]) -> list[ValidationWarning]:
    """Scans for repeated non-empty employee_id within the batch/sheet."""
    id_indices: dict[str, list[int]] = {}
    for idx, r in enumerate(records):
        emp_id = (r.employee_id or "").strip()
        if emp_id:
            id_indices.setdefault(emp_id, []).append(idx)

    warnings: list[ValidationWarning] = []
    for emp_id, indices in id_indices.items():
        if len(indices) > 1:
            for idx in indices:
                warnings.append(
                    ValidationWarning(
                        warning_type="duplicate_employee_id",
                        message=f"Duplicate employee ID '{emp_id}' found in records {indices}",
                        record_index=idx,
                        field_name="employee_id",
                        details={"employee_id": emp_id, "duplicate_indices": indices},
                    )
                )
    return warnings


def check_salary_outliers(records: Sequence[PayrollRecord]) -> list[ValidationWarning]:
    """Detects logical anomalies (negative net, non-positive basic) and 3-sigma statistical outliers (for N >= 10)."""
    import math

    warnings: list[ValidationWarning] = []

    # 1. Logical checks per record
    for idx, r in enumerate(records):
        if r.net_salary is not None and r.net_salary < 0:
            warnings.append(
                ValidationWarning(
                    warning_type="negative_net_salary",
                    message=f"Negative net salary ({r.net_salary}) in record {idx}",
                    record_index=idx,
                    field_name="net_salary",
                    details={"net_salary": r.net_salary},
                )
            )
        if r.basic_salary is not None and r.basic_salary <= 0:
            warnings.append(
                ValidationWarning(
                    warning_type="non_positive_basic_salary",
                    message=f"Non-positive basic salary ({r.basic_salary}) in record {idx}",
                    record_index=idx,
                    field_name="basic_salary",
                    details={"basic_salary": r.basic_salary},
                )
            )

    # 2. 3-Sigma statistical check for net_salary (when N >= 10)
    valid_salaries = [(idx, r.net_salary) for idx, r in enumerate(records) if r.net_salary is not None and r.net_salary > 0]
    if len(valid_salaries) >= 10:
        values = [v for _, v in valid_salaries]
        n = len(values)
        mean = sum(values) / n
        variance = sum((x - mean) ** 2 for x in values) / n
        std_dev = math.sqrt(variance)
        if std_dev > 0:
            for idx, val in valid_salaries:
                z_score = abs(val - mean) / std_dev
                if z_score > 3.0:
                    warnings.append(
                        ValidationWarning(
                            warning_type="salary_outlier",
                            message=f"Statistical outlier in net salary ({val}) in record {idx} (z-score: {z_score:.2f} > 3.0)",
                            record_index=idx,
                            field_name="net_salary",
                            details={
                                "value": val,
                                "mean": round(mean, 2),
                                "std_dev": round(std_dev, 2),
                                "z_score": round(z_score, 2),
                            },
                        )
                    )

    return warnings


def run_deterministic_quality_checks(records: Sequence[PayrollRecord]) -> list[ValidationWarning]:
    """Runs all deterministic data quality checks across records and returns flagged warnings."""
    warnings: list[ValidationWarning] = []
    for idx, record in enumerate(records):
        w = check_arithmetic_discrepancy(record, idx, ARITHMETIC_TOLERANCE)
        if w is not None:
            warnings.append(w)
    warnings.extend(check_duplicate_ids(records))
    warnings.extend(check_salary_outliers(records))
    return warnings


validate_payroll_data = run_deterministic_quality_checks


# ---------------------------------------------------------------------- code-first arithmetic & heuristics inference
def _parse_number(val: Any) -> float | None:
    """Parses a cell value to float, handling currencies, commas, trailing minus, parentheses, and spaces."""
    if val is None or isinstance(val, bool):
        return None
    if isinstance(val, (int, float)):
        return float(val)
    text = str(val).strip()
    if not text:
        return None
    if not re.search(r"[0-9٠-٩۰-۹]", text):
        return None
    try:
        res = parse_amount(text)
        if res is not None:
            return res
    except ValueError:
        pass

    t = text.translate(str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹٫", "01234567890123456789."))
    is_neg = False
    if t.startswith("(") and t.endswith(")"):
        is_neg = True
        t = t[1:-1].strip()
    elif t.endswith("-"):
        is_neg = True
        t = t[:-1].strip()
    elif t.startswith("-"):
        is_neg = True
        t = t[1:].strip()

    t = re.sub(r"(?i)^(?:SAR|USD|EUR|EGP|AED|KWD|QAR|BHD|OMR|ر\.?س|ج\.?م|د\.?إ|[\$€£¥₹])\s*", "", t).strip()
    t = re.sub(r"(?i)\s*(?:SAR|USD|EUR|EGP|AED|KWD|QAR|BHD|OMR|ر\.?س|ج\.?م|د\.?إ|[\$€£¥₹])$", "", t).strip()
    t = re.sub(r"[,  ٬]", "", t)

    if re.fullmatch(r"\d+(?:\.\d+)?", t):
        try:
            num = float(t)
            return -num if is_neg else num
        except ValueError:
            return None
    return None


def find_arithmetic_columns(
    table_or_rows: Table | Sequence[Sequence[Any]],
    tolerance: float = ARITHMETIC_TOLERANCE,
) -> dict[str, int] | None:
    """Finds numeric columns satisfying basic + allowances - deductions = net (or partial subsets)."""
    if isinstance(table_or_rows, Table):
        rows = table_or_rows.rows
    else:
        rows = table_or_rows

    if not rows:
        return None

    num_cols = max(len(r) for r in rows) if rows else 0
    if num_cols < 2:
        return None

    col_numbers: list[list[float | None]] = []
    candidate_cols: list[int] = []
    for c in range(num_cols):
        vals = [_parse_number(r[c]) if c < len(r) else None for r in rows]
        valid_count = sum(1 for v in vals if v is not None)
        if valid_count >= len(rows) * MIN_SHARE and valid_count > 0:
            candidate_cols.append(c)
        col_numbers.append(vals)

    if len(candidate_cols) < 2:
        return None

    # 1. 4 columns: basic + allowances - deductions = net
    if len(candidate_cols) >= 4:
        best_cand = None
        best_score = -1
        for b, a, d, n in itertools.permutations(candidate_cols, 4):
            match_count = 0
            valid_count = 0
            for row_idx in range(len(rows)):
                vb = col_numbers[b][row_idx]
                va = col_numbers[a][row_idx]
                vd = col_numbers[d][row_idx]
                vn = col_numbers[n][row_idx]
                if vb is not None and va is not None and vd is not None and vn is not None:
                    valid_count += 1
                    if abs((vb + va - vd) - vn) <= tolerance:
                        match_count += 1
            if valid_count >= len(rows) * MIN_SHARE and match_count >= valid_count * MIN_SHARE:
                mean_b = sum(col_numbers[b][i] for i in range(len(rows)) if col_numbers[b][i] is not None)
                mean_a = sum(col_numbers[a][i] for i in range(len(rows)) if col_numbers[a][i] is not None)
                mean_d = sum(col_numbers[d][i] for i in range(len(rows)) if col_numbers[d][i] is not None)
                mean_n = sum(col_numbers[n][i] for i in range(len(rows)) if col_numbers[n][i] is not None)
                if mean_d < mean_b and mean_d < mean_n and mean_a < mean_b:
                    edge_bonus = 2 if (n == 0 or n == max(candidate_cols)) else 0
                    score = match_count * 10 + edge_bonus
                    if score > best_score:
                        real_b, real_a = (b, a) if mean_b >= mean_a else (a, b)
                        best_score = score
                        best_cand = {"basic_salary": real_b, "allowances": real_a, "deductions": d, "net_salary": n}
        if best_cand is not None:
            return best_cand

    # 2. 3 columns:
    if len(candidate_cols) >= 3:
        best_cand = None
        best_score = -1
        for c1, c2, c3 in itertools.permutations(candidate_cols, 3):
            for is_allowance in (True, False):
                match_count = 0
                valid_count = 0
                for row_idx in range(len(rows)):
                    v1 = col_numbers[c1][row_idx]
                    v2 = col_numbers[c2][row_idx]
                    v3 = col_numbers[c3][row_idx]
                    if v1 is not None and v2 is not None and v3 is not None:
                        valid_count += 1
                        expected = (v1 + v2) if is_allowance else (v1 - v2)
                        if abs(expected - v3) <= tolerance:
                            match_count += 1
                if valid_count >= len(rows) * MIN_SHARE and match_count >= valid_count * MIN_SHARE:
                    mean_1 = sum(col_numbers[c1][i] for i in range(len(rows)) if col_numbers[c1][i] is not None)
                    mean_2 = sum(col_numbers[c2][i] for i in range(len(rows)) if col_numbers[c2][i] is not None)
                    mean_3 = sum(col_numbers[c3][i] for i in range(len(rows)) if col_numbers[c3][i] is not None)
                    if mean_2 < mean_1 and (is_allowance or mean_2 < mean_3):
                        edge_bonus = 2 if (c3 == 0 or c3 == max(candidate_cols)) else 0
                        score = match_count * 10 + edge_bonus
                        if score > best_score:
                            best_score = score
                            if is_allowance:
                                best_cand = {"basic_salary": c1, "allowances": c2, "net_salary": c3}
                            else:
                                best_cand = {"basic_salary": c1, "deductions": c2, "net_salary": c3}
        if best_cand is not None:
            return best_cand

    # 3. 2 columns: basic == net
    for c1, c2 in itertools.combinations(candidate_cols, 2):
        match_count = 0
        valid_count = 0
        for row_idx in range(len(rows)):
            v1 = col_numbers[c1][row_idx]
            v2 = col_numbers[c2][row_idx]
            if v1 is not None and v2 is not None:
                valid_count += 1
                if abs(v1 - v2) <= tolerance:
                    match_count += 1
        if valid_count >= len(rows) * MIN_SHARE and match_count >= valid_count * MIN_SHARE and match_count > 0:
            mean_v = sum(col_numbers[c1][i] for i in range(len(rows)) if col_numbers[c1][i] is not None)
            if mean_v > 0:
                return {"basic_salary": c1, "net_salary": c2}

    return None


def find_name_column(
    table_or_headers: Table | Sequence[str],
    rows_or_exclude: Sequence[Sequence[Any]] | set[int] | None = None,
    exclude_indices: set[int] | None = None,
) -> int | None:
    """Finds the employee_name column using word count, alphabetic density, and uniqueness."""
    if isinstance(table_or_headers, Table):
        headers = table_or_headers.header
        rows = table_or_headers.rows
        exclude = rows_or_exclude if isinstance(rows_or_exclude, (set, frozenset)) else (exclude_indices or set())
    else:
        headers = tuple(table_or_headers)
        rows = rows_or_exclude if isinstance(rows_or_exclude, (list, tuple)) else ()
        exclude = exclude_indices or set()

    if not rows:
        return None

    num_cols = max(len(r) for r in rows)
    best_col = None
    best_score = -1.0

    for c in range(num_cols):
        if c in exclude:
            continue
        cells = [str(r[c]).strip() for r in rows if c < len(r) and str(r[c]).strip()]
        if not cells:
            continue

        num_numeric = sum(1 for cell in cells if _parse_number(cell) is not None)
        if num_numeric / len(cells) >= 0.5:
            continue

        alpha_ratios = []
        word_counts = []
        for cell in cells:
            letters = sum(1 for ch in cell if unicodedata.category(ch).startswith("L"))
            alpha_ratios.append(letters / len(cell) if cell else 0.0)
            words = [w for w in re.split(r"\s+", cell) if re.search(r"[\u0621-\u064Aa-zA-Z]", w)]
            word_counts.append(len(words))

        avg_alpha = sum(alpha_ratios) / len(alpha_ratios) if alpha_ratios else 0.0
        if avg_alpha < 0.3:
            continue

        avg_words = sum(word_counts) / len(word_counts) if word_counts else 0.0
        unique_ratio = len(set(cells)) / len(cells)

        score = avg_words * 3.0 + avg_alpha * 2.0 + unique_ratio * 1.5
        if score > best_score:
            best_score = score
            best_col = c

    return best_col


def find_id_column(
    table_or_headers: Table | Sequence[str],
    rows_or_exclude: Sequence[Sequence[Any]] | set[int] | None = None,
    exclude_indices: set[int] | None = None,
) -> int | None:
    """Finds the employee_id column using uniqueness ratio, code patterns, and non-monetary distribution."""
    if isinstance(table_or_headers, Table):
        headers = table_or_headers.header
        rows = table_or_headers.rows
        exclude = rows_or_exclude if isinstance(rows_or_exclude, (set, frozenset)) else (exclude_indices or set())
    else:
        headers = tuple(table_or_headers)
        rows = rows_or_exclude if isinstance(rows_or_exclude, (list, tuple)) else ()
        exclude = exclude_indices or set()

    if not rows:
        return None

    num_cols = max(len(r) for r in rows)
    best_col = None
    best_score = -1.0

    for c in range(num_cols):
        if c in exclude:
            continue
        cells = [str(r[c]).strip() for r in rows if c < len(r) and str(r[c]).strip()]
        if not cells:
            continue

        unique_ratio = len(set(cells)) / len(cells)
        if unique_ratio < 0.7:
            continue

        avg_words = sum(len(cell.split()) for cell in cells) / len(cells)
        if avg_words > 1.5:
            continue

        is_seq = False
        try:
            int_vals = [int(cell) for cell in cells]
            if len(int_vals) > 1 and all(int_vals[i] == int_vals[0] + i for i in range(len(int_vals))):
                if int_vals[0] in (0, 1):
                    is_seq = True
        except ValueError:
            pass

        has_alphanumeric = any(re.search(r"[A-Za-z\u0621-\u064A]", cell) and re.search(r"\d", cell) for cell in cells)
        has_digits = all(re.search(r"\d", cell) for cell in cells)
        has_decimals = any("." in cell and re.search(r"\.\d{2}", cell) for cell in cells)

        score = unique_ratio * 4.0
        if has_alphanumeric:
            score += 5.0
        elif has_digits:
            score += 3.0
        if is_seq:
            score -= 5.0
        if has_decimals:
            score -= 3.0

        if score > best_score:
            best_score = score
            best_col = c

    return best_col


def infer_mapping_by_arithmetic(
    table_or_headers: Table | Sequence[str],
    rows: Sequence[Sequence[Any]] | None = None,
) -> Mapping | None:
    """Infers table mapping by solving payroll arithmetic and applying name/id heuristics."""
    if isinstance(table_or_headers, Table):
        headers = table_or_headers.header
        table_rows = table_or_headers.rows
        table = table_or_headers
    else:
        headers = tuple(table_or_headers)
        table_rows = tuple(tuple(str(c) for c in r) for r in (rows or []))
        table = Table(headers, table_rows)

    if not table_rows:
        return None

    arithmetic_cols = find_arithmetic_columns(table)
    if not arithmetic_cols:
        return None

    assigned: set[int] = set(arithmetic_cols.values())
    mapping: Mapping = [None] * len(headers)

    for field, idx in arithmetic_cols.items():
        if idx < len(mapping):
            mapping[idx] = field

    name_idx = find_name_column(table, exclude_indices=assigned)
    if name_idx is not None and name_idx < len(mapping):
        mapping[name_idx] = "employee_name"
        assigned.add(name_idx)

    id_idx = find_id_column(table, exclude_indices=assigned)
    if id_idx is not None and id_idx < len(mapping):
        mapping[id_idx] = "employee_id"
        assigned.add(id_idx)

    if not sufficient(mapping):
        return None

    return mapping
