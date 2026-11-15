"""Unit tests for PDF parsing: ruled tables, unruled tables, RTL Arabic clustering, and plain text."""
from __future__ import annotations

import io
import os
import tempfile
from pathlib import Path

import pdfplumber
import pymupdf
import pytest

from document_processing import parse_document
from document_processing.pdf_parser import _extract_unruled_tables, _tables_as_text, parse_pdf, plain_letters
from document_processing.table_extractor import build_records, find_tables, map_by_synonyms
from tests import samples

ARABIC_FONT_CANDIDATES = [
    "C:/Windows/Fonts/arial.ttf",
    "C:/Windows/Fonts/tahoma.ttf",
    "C:/Windows/Fonts/seguiemj.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
    "/usr/share/fonts/truetype/noto/NotoSansArabic-Regular.ttf",
]


def _find_arabic_font() -> str | None:
    for path in ARABIC_FONT_CANDIDATES:
        if os.path.exists(path):
            return path
    return None


def make_unruled_pdf(
    rows: list[tuple[Any, ...]],
    x0: float = 40.0,
    y0: float = 60.0,
    col_width: float = 85.0,
    row_height: float = 24.0,
) -> bytes:
    """Builds a synthetic PDF containing tabular text without any vector borders/lines."""
    doc = pymupdf.open()
    page = doc.new_page()
    for r_idx, row in enumerate(rows):
        y = y0 + (r_idx + 1) * row_height - 8
        for c_idx, val in enumerate(row):
            if val is not None and str(val).strip():
                page.insert_text((x0 + c_idx * col_width + 4, y), str(val), fontsize=10)
    return doc.tobytes()


def make_unruled_arabic_pdf(
    rows: list[tuple[str, ...]],
    xs: list[float] | None = None,
    y0: float = 60.0,
    row_height: float = 30.0,
) -> bytes:
    """Builds an unruled Arabic PDF where columns are arranged Right-to-Left."""
    doc = pymupdf.open()
    page = doc.new_page()
    font_file = _find_arabic_font()

    num_cols = len(rows[0])
    if xs is None:
        # Default RTL column coordinates: right to left
        xs = [450.0 - i * 100.0 for i in range(num_cols)]

    if font_file:
        page.insert_font(fontname="arabic_font", fontfile=font_file)
        for r_idx, row in enumerate(rows):
            y = y0 + r_idx * row_height
            for c_idx, val in enumerate(row):
                if val:
                    page.insert_text((xs[c_idx], y), str(val), fontname="arabic_font", fontsize=11)
    else:
        # Fallback using insert_htmlbox which bundles portable Arabic rendering
        for r_idx, row in enumerate(rows):
            y = y0 + r_idx * row_height
            for c_idx, val in enumerate(row):
                if val:
                    x_left = xs[c_idx] - 20
                    x_right = xs[c_idx] + 70
                    page.insert_htmlbox(pymupdf.Rect(x_left, y, x_right, y + 25), f"<p>{val}</p>")

    return doc.tobytes()


# ---------------------------------------------------------------------- Tests
def test_ruled_pdf_table_extracts_cleanly():
    """Ruled tables with vector lines must continue to be detected by pdfplumber's extract_tables."""
    data = samples.pdf_table_bytes()
    with pdfplumber.open(io.BytesIO(data)) as plumber:
        page = plumber.pages[0]
        text = _tables_as_text(page)
        assert text, "Ruled table should produce non-empty text"
        lines = text.splitlines()
        assert len(lines) == 3
        assert lines[0] == "Name | ID | Basic | Allowances | Deductions | Net"
        assert lines[1] == "Ahmed Ali | E001 | 5000 | 500 | 200 | 5300"
        assert lines[2] == "Sara Omar | E002 | 6000 | 0 | 300 | 5700"


def test_unruled_pdf_table_extracts_into_piped_rows(tmp_path):
    """Unruled tables without vector borders must extract into pipe-delimited text via coordinate clustering."""
    rows = [
        ("Name", "ID", "Basic", "Allowances", "Deductions", "Net"),
        ("Ahmed Ali", "E001", "5000", "500", "200", "5300"),
        ("Sara Omar", "E002", "6000", "1000", "300", "6700"),
    ]
    pdf_bytes = make_unruled_pdf(rows)
    path = tmp_path / "unruled.pdf"
    path.write_bytes(pdf_bytes)

    # 1. Direct page table text check
    with pdfplumber.open(path) as plumber:
        page = plumber.pages[0]
        # Standard extract_tables must be empty for unruled tables
        assert page.extract_tables() == []
        extracted = _tables_as_text(page)
        assert extracted, "Unruled table fallback must extract table text"
        lines = extracted.splitlines()
        assert len(lines) == 3
        assert "Name | ID | Basic | Allowances | Deductions | Net" in lines[0]
        assert "Ahmed Ali | E001 | 5000 | 500 | 200 | 5300" in lines[1]
        assert "Sara Omar | E002 | 6000 | 1000 | 300 | 6700" in lines[2]

    # 2. Document parser integration check
    parsed = parse_document(path, "PDF")
    assert parsed.pages == 1
    assert "Ahmed Ali | E001 | 5000 | 500 | 200 | 5300" in parsed.text


def test_unruled_pdf_table_with_blank_cells_preserves_column_alignment(tmp_path):
    """Missing cells in an unruled table must not shift subsequent columns horizontally."""
    rows = [
        ("Name", "ID", "Basic", "Allowances", "Deductions", "Net"),
        ("Ahmed Ali", "E001", "5000", "500", "200", "5300"),
        ("Sara Omar", "E002", "6000", "", "300", "5700"),  # Allowances is blank
    ]
    pdf_bytes = make_unruled_pdf(rows)
    path = tmp_path / "blank_cells.pdf"
    path.write_bytes(pdf_bytes)

    with pdfplumber.open(path) as plumber:
        extracted = _tables_as_text(plumber.pages[0])
        lines = extracted.splitlines()
        assert len(lines) == 3
        sara_row = lines[2].split(" | ")
        assert len(sara_row) == 6
        assert sara_row[0] == "Sara Omar"
        assert sara_row[1] == "E002"
        assert sara_row[2] == "6000"
        assert sara_row[3].strip() == ""  # Allowances remained empty
        assert sara_row[4] == "300"  # Deductions kept in col index 4
        assert sara_row[5] == "5700"  # Net kept in col index 5


def test_unruled_arabic_table_rtl_reversed_clustering(tmp_path):
    """Arabic tables arranged Right-to-Left must order columns in RTL reading order."""
    rows = [
        ("الاسم", "الرقم", "الاساسي", "الصافي"),
        ("أحمد علي", "E001", "5000", "5000"),
        ("سارة عمر", "E002", "6000", "6000"),
    ]
    pdf_bytes = make_unruled_arabic_pdf(rows)
    path = tmp_path / "arabic_unruled.pdf"
    path.write_bytes(pdf_bytes)

    with pdfplumber.open(path) as plumber:
        extracted = _tables_as_text(plumber.pages[0])
        assert extracted, "Arabic unruled table should extract non-empty text"
        lines = extracted.splitlines()
        assert len(lines) == 3

        header_cells = [c.strip() for c in lines[0].split(" | ")]
        assert len(header_cells) == 4
        # Rightmost column (الاسم) must be the first column in extracted output
        assert "الاسم" in header_cells[0] or "اسم" in header_cells[0]
        assert "الصافي" in header_cells[3] or "صافي" in header_cells[3]

        row1_cells = [c.strip() for c in lines[1].split(" | ")]
        assert "E001" in row1_cells[1]
        assert "5000" in row1_cells[2]
        assert "5000" in row1_cells[3]


def test_plain_text_pdf_does_not_generate_false_positive_tables(tmp_path):
    """Continuous text paragraphs must never generate false table lines with '|'."""
    paragraphs = [
        "Human Resources Monthly Administrative Report",
        "This report summarizes internal staff activities during the current operational period.",
        "All departmental teams completed their milestones ahead of schedule with zero safety incidents.",
        "Further operational briefings and reviews are scheduled for the subsequent business quarter.",
    ]
    doc = pymupdf.open()
    page = doc.new_page()
    for idx, line in enumerate(paragraphs):
        page.insert_text((72, 72 + idx * 24), line, fontsize=10)

    path = tmp_path / "free_text.pdf"
    path.write_bytes(doc.tobytes())

    with pdfplumber.open(path) as plumber:
        extracted = _tables_as_text(plumber.pages[0])
        assert extracted == "", f"Plain text should not produce table output, got: {extracted!r}"

    parsed = parse_document(path, "PDF")
    assert "|" not in parsed.text


def test_end_to_end_unruled_table_deterministic_extraction(tmp_path):
    """End-to-end integration: parse_document on unruled PDF yields structured payroll records."""
    rows = [
        ("Name", "ID", "Basic", "Allowances", "Deductions", "Net"),
        ("Ahmed Ali", "E001", "5000", "500", "200", "5300"),
        ("Sara Omar", "E002", "6000", "1000", "300", "6700"),
    ]
    path = tmp_path / "payroll.pdf"
    path.write_bytes(make_unruled_pdf(rows))

    parsed = parse_document(path, "PDF")
    tables = find_tables(parsed.text)
    assert len(tables) == 1, "find_tables should identify the unruled table block"

    table = tables[0]
    assert table.header == ("Name", "ID", "Basic", "Allowances", "Deductions", "Net")

    mapping = map_by_synonyms(table.header)
    assert mapping == ["employee_name", "employee_id", "basic_salary", "allowances", "deductions", "net_salary"]

    records = build_records(table, mapping)
    assert len(records) == 2
    assert records[0].employee_name == "Ahmed Ali"
    assert records[0].employee_id == "E001"
    assert records[0].basic_salary == 5000.0
    assert records[0].allowances == 500.0
    assert records[0].deductions == 200.0
    assert records[0].net_salary == 5300.0


def test_mixed_page_title_notes_and_unruled_table(tmp_path):
    """Header title and footer notes outside the table do not distort column intervals."""
    doc = pymupdf.open()
    page = doc.new_page()

    # Title at top
    page.insert_text((72, 40), "Monthly Payroll Summary Statement - June 2026", fontsize=12)

    # 4-column unruled table in middle
    rows = [
        ("Name", "ID", "Basic", "Net"),
        ("Tariq Aziz", "USR-99", "8000", "8000"),
        ("Mona Saleh", "USR-98", "9500", "9500"),
    ]
    for r_idx, row in enumerate(rows):
        y = 100 + r_idx * 25
        for c_idx, val in enumerate(row):
            page.insert_text((72 + c_idx * 110, y), val, fontsize=10)

    # Footer note at bottom
    page.insert_text((72, 250), "Confidential payroll data. Generated automatically by accounting system.", fontsize=9)

    path = tmp_path / "mixed.pdf"
    path.write_bytes(doc.tobytes())

    with pdfplumber.open(path) as plumber:
        extracted = _tables_as_text(plumber.pages[0])
        lines = extracted.splitlines()
        assert len(lines) == 3
        assert lines[0] == "Name | ID | Basic | Net"
        assert lines[1] == "Tariq Aziz | USR-99 | 8000 | 8000"
        assert lines[2] == "Mona Saleh | USR-98 | 9500 | 9500"


def test_single_line_or_sparse_text_returns_no_table(tmp_path):
    """A document with fewer than min_rows lines or min_columns words returns no table."""
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((100, 100), "Short isolated sentence", fontsize=10)

    path = tmp_path / "sparse.pdf"
    path.write_bytes(doc.tobytes())

    with pdfplumber.open(path) as plumber:
        assert _extract_unruled_tables(plumber.pages[0]) == ""


def test_plain_letters_normalizes_soft_hyphens_and_unicode_dashes():
    """Soft hyphens (\\xad) and typographic dashes must normalize to standard ASCII '-'."""
    assert plain_letters("E\xad101") == "E-101"
    assert plain_letters("EMP\u2010202") == "EMP-202"
    assert plain_letters("PAY\u2013303") == "PAY-303"
    assert plain_letters("TAX\u2212404") == "TAX-404"
    assert plain_letters("أحمد علي") == "أحمد علي"

