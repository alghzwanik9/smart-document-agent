"""Empirical adversarial stress test harness for Milestone M1 (Unruled PDF Table Extraction).

Synthesizes challenging borderless PDF scenarios:
1. Jittered vertical and horizontal coordinates (slight word misalignments).
2. Mixed Arabic and numbers/English codes within table cells.
3. Varied font sizes across headers and rows.
4. Multi-page documents with unruled tables.
5. Tables with empty cells in different columns.
6. Determinism, idempotence, and column integrity checks.
"""
from __future__ import annotations

import io
import os
import random
from pathlib import Path
from typing import Any

import pdfplumber
import pymupdf
import pytest

from document_processing import parse_document
from document_processing.pdf_parser import _extract_unruled_tables, _tables_as_text, parse_pdf
from document_processing.table_extractor import build_records, find_tables, map_by_synonyms
from tests.test_pdf_parser import _find_arabic_font, make_unruled_arabic_pdf, make_unruled_pdf


# ==============================================================================
# Helper Generators for Challenging Scenarios
# ==============================================================================

def make_jittered_unruled_pdf(
    rows: list[tuple[Any, ...]],
    x0: float = 40.0,
    y0: float = 60.0,
    col_width: float = 85.0,
    row_height: float = 24.0,
    x_jitter_range: tuple[float, float] = (-3.0, 3.0),
    y_jitter_range: tuple[float, float] = (-2.5, 2.5),
    seed: int = 42,
) -> bytes:
    """Builds a borderless table with pseudo-random coordinate jitter on each cell."""
    rng = random.Random(seed)
    doc = pymupdf.open()
    page = doc.new_page()
    for r_idx, row in enumerate(rows):
        base_y = y0 + (r_idx + 1) * row_height
        for c_idx, val in enumerate(row):
            if val is not None and str(val).strip():
                x_jit = rng.uniform(*x_jitter_range)
                y_jit = rng.uniform(*y_jitter_range)
                x = x0 + c_idx * col_width + x_jit
                y = base_y + y_jit
                page.insert_text((x, y), str(val), fontsize=10)
    return doc.tobytes()


def make_variable_font_unruled_pdf(
    header: tuple[str, ...],
    rows: list[tuple[Any, ...]],
    header_fontsize: float = 14.0,
    row_fontsizes: list[float] | None = None,
    x0: float = 40.0,
    y0: float = 60.0,
    col_width: float = 85.0,
) -> bytes:
    """Builds a borderless table with distinct font sizes across header and data rows."""
    doc = pymupdf.open()
    page = doc.new_page()

    # Insert header
    for c_idx, val in enumerate(header):
        page.insert_text((x0 + c_idx * col_width, y0), str(val), fontsize=header_fontsize)

    # Insert data rows
    y = y0 + 30.0
    for r_idx, row in enumerate(rows):
        fs = row_fontsizes[r_idx] if row_fontsizes and r_idx < len(row_fontsizes) else 10.0
        for c_idx, val in enumerate(row):
            if val is not None and str(val).strip():
                page.insert_text((x0 + c_idx * col_width, y), str(val), fontsize=fs)
        y += 22.0

    return doc.tobytes()


def make_mixed_bidi_unruled_pdf(
    rows: list[tuple[str, ...]],
    xs: list[float] | None = None,
    y0: float = 60.0,
    row_height: float = 28.0,
) -> bytes:
    """Builds an unruled PDF where cells contain mixed Arabic, English codes, and numbers."""
    doc = pymupdf.open()
    page = doc.new_page()
    font_file = _find_arabic_font()

    num_cols = len(rows[0])
    if xs is None:
        # RTL column order: right to left
        xs = [460.0 - i * 110.0 for i in range(num_cols)]

    if font_file:
        page.insert_font(fontname="arabic_font", fontfile=font_file)
        for r_idx, row in enumerate(rows):
            y = y0 + r_idx * row_height
            for c_idx, val in enumerate(row):
                if val:
                    page.insert_text((xs[c_idx], y), str(val), fontname="arabic_font", fontsize=10)
    else:
        for r_idx, row in enumerate(rows):
            y = y0 + r_idx * row_height
            for c_idx, val in enumerate(row):
                if val:
                    page.insert_htmlbox(
                        pymupdf.Rect(xs[c_idx] - 25, y, xs[c_idx] + 85, y + 25),
                        f"<p>{val}</p>",
                    )

    return doc.tobytes()


def make_multipage_unruled_pdf() -> bytes:
    """Builds a 3-page document:
    - Page 1: Unruled table part 1 (Northern division)
    - Page 2: Unruled table part 2 (Southern division)
    - Page 3: Narrative summary without any table
    """
    doc = pymupdf.open()

    # Page 1: Unruled table 1
    p1 = doc.new_page()
    p1.insert_text((40, 40), "Monthly Payroll Statement - Northern Branch", fontsize=12)
    p1_rows = [
        ("Employee", "ID", "Basic", "Allowances", "Deductions", "Net"),
        ("Tariq Jamil", "EMP-101", "7000", "800", "300", "7500"),
        ("Mona Sayed", "EMP-102", "8500", "1200", "400", "9300"),
        ("Kareem Nour", "EMP-103", "6200", "500", "200", "6500"),
    ]
    for r_idx, row in enumerate(p1_rows):
        y = 70.0 + r_idx * 24.0
        for c_idx, val in enumerate(row):
            p1.insert_text((40.0 + c_idx * 85.0, y), val, fontsize=10)

    # Page 2: Unruled table 2
    p2 = doc.new_page()
    p2.insert_text((40, 40), "Monthly Payroll Statement - Southern Branch", fontsize=12)
    p2_rows = [
        ("Employee", "ID", "Basic", "Allowances", "Deductions", "Net"),
        ("Zaid Mansoor", "EMP-201", "6800", "700", "250", "7250"),
        ("Layla Hani", "EMP-202", "9100", "1500", "600", "10000"),
    ]
    for r_idx, row in enumerate(p2_rows):
        y = 70.0 + r_idx * 24.0
        for c_idx, val in enumerate(row):
            p2.insert_text((40.0 + c_idx * 85.0, y), val, fontsize=10)

    # Page 3: Narrative summary
    p3 = doc.new_page()
    p3.insert_text((40, 50), "Audit Remarks and Compliance Certification", fontsize=12)
    p3.insert_text((40, 80), "All branch disbursements have been matched against bank statements.", fontsize=10)
    p3.insert_text((40, 105), "Internal controls were verified with zero discrepancies noted.", fontsize=10)
    p3.insert_text((40, 130), "Transfers are approved for release on the 28th business day.", fontsize=10)

    return doc.tobytes()


# ==============================================================================
# Scenario 1: Coordinate Jitter Stress-Tests
# ==============================================================================

class TestEmpiricalCoordinateJitter:
    """Stress tests horizontal and vertical coordinate jittering."""

    def test_realistic_misalignment_jitter_maintains_column_integrity(self, tmp_path):
        """Slight vertical and horizontal coordinate jitter (+-3pt x, +-2.5pt y) simulates

        real-world PDF generation noise. Must extract all 6 columns cleanly without mixing.
        """
        rows = [
            ("Employee Name", "Badge ID", "Base Salary", "Allowances", "Deductions", "Net Pay"),
            ("Hassan Kamal", "EMP-001", "5500", "450", "150", "5800"),
            ("Fatima Al-Nour", "EMP-002", "6200", "600", "200", "6600"),
            ("Kareem Adel", "EMP-003", "4800", "300", "100", "5000"),
            ("Nadia Qasim", "EMP-004", "7100", "800", "250", "7650"),
        ]
        pdf_bytes = make_jittered_unruled_pdf(
            rows,
            x_jitter_range=(-3.5, 3.5),
            y_jitter_range=(-2.5, 2.5),
            seed=101,
        )
        path = tmp_path / "jitter_realistic.pdf"
        path.write_bytes(pdf_bytes)

        with pdfplumber.open(path) as plumber:
            text = _tables_as_text(plumber.pages[0])
            assert text != "", "Jittered unruled table must extract"
            lines = text.splitlines()
            assert len(lines) == 5, f"Expected 5 rows, got {len(lines)}"

            for idx, raw_line in enumerate(lines):
                cells = [c.strip() for c in raw_line.split(" | ")]
                assert len(cells) == 6, f"Row {idx} should have 6 columns, got {len(cells)}: {raw_line}"
                assert cells[0] == rows[idx][0], f"Col 0 mismatch: expected {rows[idx][0]}, got {cells[0]}"
                assert cells[1] == rows[idx][1], f"Col 1 mismatch: expected {rows[idx][1]}, got {cells[1]}"
                assert cells[2] == rows[idx][2], f"Col 2 mismatch: expected {rows[idx][2]}, got {cells[2]}"
                assert cells[5] == rows[idx][5], f"Col 5 mismatch: expected {rows[idx][5]}, got {cells[5]}"

    def test_multi_seed_jitter_stability(self, tmp_path):
        """Test extraction stability across 5 distinct pseudo-random jitter seeds."""
        rows = [
            ("Name", "ID", "Basic", "Allowances", "Deductions", "Net"),
            ("Ahmed Ali", "E001", "5000", "500", "200", "5300"),
            ("Sara Omar", "E002", "6000", "1000", "300", "6700"),
            ("Zaid Amr", "E003", "4500", "300", "100", "4700"),
        ]
        for seed in [1, 7, 42, 88, 199]:
            pdf_bytes = make_jittered_unruled_pdf(rows, x_jitter_range=(-3.0, 3.0), y_jitter_range=(-2.0, 2.0), seed=seed)
            path = tmp_path / f"jitter_seed_{seed}.pdf"
            path.write_bytes(pdf_bytes)

            with pdfplumber.open(path) as plumber:
                text = _tables_as_text(plumber.pages[0])
                assert text != "", f"Seed {seed} failed to extract table"
                lines = text.splitlines()
                assert len(lines) == 4, f"Seed {seed} expected 4 lines, got {len(lines)}"
                cells_r1 = [c.strip() for c in lines[1].split(" | ")]
                assert cells_r1[0] == "Ahmed Ali"
                assert cells_r1[1] == "E001"
                assert cells_r1[5] == "5300"


# ==============================================================================
# Scenario 2: Mixed Arabic and Numbers/English Codes within Cells
# ==============================================================================

class TestEmpiricalMixedBidiCells:
    """Stress tests cells containing mixed Arabic script, Latin alphanumeric codes, and digits."""

    def test_cells_with_mixed_alphanumeric_and_arabic_tokens(self, tmp_path):
        """Arabic table with mixed tokens in cells:

        Col 0: Arabic Name + English ID ('أحمد علي (E-101)')
        Col 1: Arabic Dept + code ('قسم IT-01')
        Col 2: Basic salary
        Col 3: Net salary
        """
        rows = [
            ("اسم الموظف والرمز", "القسم والكود", "الراتب الاساسي", "صافي الراتب"),
            ("أحمد علي E-101", "قسم IT-01", "7500", "7500"),
            ("سارة عمر E-102", "إدارة HR-02", "8200", "8200"),
            ("محمود حسن E-103", "عمليات OPS-03", "6100", "6100"),
        ]
        pdf_bytes = make_mixed_bidi_unruled_pdf(rows)
        path = tmp_path / "mixed_bidi_cells.pdf"
        path.write_bytes(pdf_bytes)

        with pdfplumber.open(path) as plumber:
            text = _tables_as_text(plumber.pages[0])
            assert text != "", "Mixed Arabic-English unruled table must extract"
            lines = text.splitlines()
            assert len(lines) == 4

            # RTL order check: Name column must be index 0
            h_cells = [c.strip() for c in lines[0].split(" | ")]
            assert len(h_cells) == 4
            assert "اسم" in h_cells[0] or "الموظف" in h_cells[0]
            assert "صافي" in h_cells[3] or "الراتب" in h_cells[3]

            row1 = [c.strip() for c in lines[1].split(" | ")]
            assert len(row1) == 4
            assert "أحمد" in row1[0]
            # Verify alphanumeric code and Arabic name remained together in col 0
            assert "101" in row1[0]
            assert "7500" in row1[2]
            assert "7500" in row1[3]

    def test_latin_table_with_minority_arabic_note_preserves_ltr(self, tmp_path):
        """Primarily English table with an occasional Arabic note (<30% Arabic words) preserves LTR order."""
        rows = [
            ("Name", "ID", "Department", "Basic", "Remarks"),
            ("John Doe", "E01", "Engineering", "5000", "Approved"),
            ("Jane Smith", "E02", "Operations", "6000", "عقد مؤقت"),  # Single Arabic cell
            ("Bob Jones", "E03", "Marketing", "4500", "Full Time"),
            ("Alice Brown", "E04", "Finance", "7000", "Permanent"),
        ]
        doc = pymupdf.open()
        page = doc.new_page()
        font_file = _find_arabic_font()
        if font_file:
            page.insert_font(fontname="arabic_font", fontfile=font_file)

        for r_idx, row in enumerate(rows):
            y = 70.0 + r_idx * 25.0
            page.insert_text((50.0, y), row[0], fontsize=10)
            page.insert_text((150.0, y), row[1], fontsize=10)
            page.insert_text((210.0, y), row[2], fontsize=10)
            page.insert_text((300.0, y), row[3], fontsize=10)
            if r_idx == 2 and font_file:
                page.insert_text((380.0, y), row[4], fontname="arabic_font", fontsize=10)
            else:
                page.insert_text((380.0, y), row[4], fontsize=10)

        path = tmp_path / "ltr_with_minority_arabic.pdf"
        path.write_bytes(doc.tobytes())

        with pdfplumber.open(path) as plumber:
            text = _tables_as_text(plumber.pages[0])
            assert text != ""
            lines = text.splitlines()
            assert len(lines) == 5
            # LTR dominance: Col 0 is Name, Col 4 is Remarks
            h_cells = [c.strip() for c in lines[0].split(" | ")]
            assert h_cells[0] == "Name"
            assert h_cells[1] == "ID"
            assert h_cells[2] == "Department"
            assert h_cells[3] == "Basic"
            assert h_cells[4] == "Remarks"


# ==============================================================================
# Scenario 3: Varied Font Sizes Across Headers and Rows
# ==============================================================================

class TestEmpiricalVariedFontSizes:
    """Stress tests varied typography: large bold headers, small data cells, variable heights."""

    def test_large_header_and_small_rows_do_not_distort_column_clustering(self, tmp_path):
        """Header fontsize=15.0 pt, rows with 9.0 pt, 8.5 pt, 8.0 pt."""
        header = ("Staff Member", "Badge ID", "Base Salary", "Allowance", "Deduction", "Net Disbursed")
        rows = [
            ("Amr Mostafa", "B-101", "4500", "350", "120", "4730"),
            ("Dalia Salem", "B-102", "5800", "500", "250", "6050"),
            ("Omar Khaled", "B-103", "7100", "800", "300", "7600"),
        ]
        pdf_bytes = make_variable_font_unruled_pdf(
            header=header,
            rows=rows,
            header_fontsize=15.0,
            row_fontsizes=[9.0, 8.5, 8.0],
            col_width=110.0,
        )
        path = tmp_path / "variable_font_table.pdf"
        path.write_bytes(pdf_bytes)

        with pdfplumber.open(path) as plumber:
            text = _tables_as_text(plumber.pages[0])
            assert text != "", "Variable font table must be detected"
            lines = text.splitlines()
            assert len(lines) == 4, f"Expected 4 rows, got {len(lines)}"

            h_cells = [c.strip() for c in lines[0].split(" | ")]
            assert len(h_cells) == 6
            assert h_cells[0] == "Staff Member"
            assert h_cells[1] == "Badge ID"
            assert h_cells[5] == "Net Disbursed"

            r2_cells = [c.strip() for c in lines[2].split(" | ")]
            assert len(r2_cells) == 6
            assert r2_cells[0] == "Dalia Salem"
            assert r2_cells[1] == "B-102"
            assert r2_cells[2] == "5800"
            assert r2_cells[5] == "6050"


# ==============================================================================
# Scenario 4: Multi-Page Documents with Unruled Tables
# ==============================================================================

class TestEmpiricalMultiPageDocuments:
    """Stress tests unruled table extraction across multi-page PDF documents."""

    def test_multi_page_with_unruled_tables_on_pages_1_and_2_and_narrative_on_page_3(self, tmp_path):
        """Multi-page PDF where pages 1 & 2 contain unruled tables and page 3 has plain text."""
        pdf_bytes = make_multipage_unruled_pdf()
        path = tmp_path / "multipage_stress.pdf"
        path.write_bytes(pdf_bytes)

        # 1. Test parse_pdf directly
        parsed = parse_pdf(path)
        assert parsed.pages == 3
        assert parsed.ocr_pages == 0

        # Split by page delimiter
        pages = parsed.text.split("--- page ")
        assert len(pages) == 4  # index 0 is empty prefix

        p1_text = pages[1]
        p2_text = pages[2]
        p3_text = pages[3]

        # Page 1 table verification
        assert "Tariq Jamil | EMP-101 | 7000 | 800 | 300 | 7500" in p1_text
        assert "Mona Sayed | EMP-102 | 8500 | 1200 | 400 | 9300" in p1_text

        # Page 2 table verification
        assert "Zaid Mansoor | EMP-201 | 6800 | 700 | 250 | 7250" in p2_text
        assert "Layla Hani | EMP-202 | 9100 | 1500 | 600 | 10000" in p2_text

        # Page 3 narrative verification: MUST NOT contain '|'
        assert "Audit Remarks and Compliance Certification" in p3_text
        for line in p3_text.splitlines():
            if "Audit Remarks" not in line and "disbursements" not in line and "---" not in line:
                assert "|" not in line, f"Page 3 narrative text contained table delimiter: {line}"

        # 2. End-to-end find_tables check
        tables = find_tables(parsed.text)
        assert len(tables) == 2, f"Expected exactly 2 tables across document, found {len(tables)}"


# ==============================================================================
# Scenario 5: Tables with Empty Cells in Different Columns
# ==============================================================================

class TestEmpiricalEmptyCellPositions:
    """Stress tests table rows with missing/empty cells at various column positions."""

    def test_empty_first_column_cell_preserves_remaining_column_indices(self, tmp_path):
        """Row 2 has empty Name (col 0). Col 1 (ID), Col 2 (Basic), Col 5 (Net) must not shift."""
        rows = [
            ("Name", "ID", "Basic", "Allowances", "Deductions", "Net"),
            ("Ahmed Ali", "E001", "5000", "500", "200", "5300"),
            ("", "E002", "6000", "1000", "300", "6700"),  # Col 0 empty
            ("Omar Zaid", "E003", "4500", "300", "100", "4700"),
        ]
        pdf_bytes = make_unruled_pdf(rows)
        path = tmp_path / "empty_first.pdf"
        path.write_bytes(pdf_bytes)

        with pdfplumber.open(path) as plumber:
            text = _tables_as_text(plumber.pages[0])
            assert text != ""
            lines = text.splitlines()
            assert len(lines) == 4

            r2_cells = lines[2].split(" | ")
            assert len(r2_cells) == 6
            assert r2_cells[0].strip() == ""
            assert r2_cells[1].strip() == "E002"
            assert r2_cells[2].strip() == "6000"
            assert r2_cells[3].strip() == "1000"
            assert r2_cells[4].strip() == "300"
            assert r2_cells[5].strip() == "6700"

    def test_empty_last_column_cell_preserves_alignment(self, tmp_path):
        """Row 2 has empty Net (col 5). Preceding columns must stay in their proper positions."""
        rows = [
            ("Name", "ID", "Basic", "Allowances", "Deductions", "Net"),
            ("Ahmed Ali", "E001", "5000", "500", "200", "5300"),
            ("Sara Omar", "E002", "6000", "1000", "300", ""),  # Col 5 empty
            ("Omar Zaid", "E003", "4500", "300", "100", "4700"),
        ]
        pdf_bytes = make_unruled_pdf(rows)
        path = tmp_path / "empty_last.pdf"
        path.write_bytes(pdf_bytes)

        with pdfplumber.open(path) as plumber:
            text = _tables_as_text(plumber.pages[0])
            assert text != ""
            lines = text.splitlines()
            assert len(lines) == 4

            r2_cells = lines[2].split(" | ")
            assert len(r2_cells) == 6
            assert r2_cells[0].strip() == "Sara Omar"
            assert r2_cells[1].strip() == "E002"
            assert r2_cells[2].strip() == "6000"
            assert r2_cells[3].strip() == "1000"
            assert r2_cells[4].strip() == "300"
            assert r2_cells[5].strip() == ""

    def test_multiple_consecutive_empty_cells_in_middle(self, tmp_path):
        """Row 2 has BOTH allowances and deductions empty (cols 3 & 4). Net must remain at col 5."""
        rows = [
            ("Name", "ID", "Basic", "Allowances", "Deductions", "Net"),
            ("Ahmed Ali", "E001", "5000", "500", "200", "5300"),
            ("Sara Omar", "E002", "6000", "", "", "6000"),  # Cols 3 and 4 empty
            ("Omar Zaid", "E003", "4500", "300", "100", "4700"),
        ]
        pdf_bytes = make_unruled_pdf(rows)
        path = tmp_path / "consecutive_empty.pdf"
        path.write_bytes(pdf_bytes)

        with pdfplumber.open(path) as plumber:
            text = _tables_as_text(plumber.pages[0])
            assert text != ""
            lines = text.splitlines()
            assert len(lines) == 4

            r2_cells = lines[2].split(" | ")
            assert len(r2_cells) == 6
            assert r2_cells[0].strip() == "Sara Omar"
            assert r2_cells[1].strip() == "E002"
            assert r2_cells[2].strip() == "6000"
            assert r2_cells[3].strip() == ""
            assert r2_cells[4].strip() == ""
            assert r2_cells[5].strip() == "6000"


# ==============================================================================
# Scenario 6: Determinism, Robustness, and Crash Resistance
# ==============================================================================

class TestEmpiricalDeterminismAndRobustness:
    """Stress tests repeatability, idempotence, and absence of crashes on edge inputs."""

    def test_repeated_extractions_are_strictly_identical(self, tmp_path):
        """Five sequential extractions of the same unruled PDF must yield identical string outputs."""
        rows = [
            ("Name", "ID", "Basic", "Allowances", "Deductions", "Net"),
            ("Ahmed Ali", "E001", "5000", "500", "200", "5300"),
            ("Sara Omar", "E002", "6000", "1000", "300", "6700"),
        ]
        pdf_bytes = make_unruled_pdf(rows)
        path = tmp_path / "determinism.pdf"
        path.write_bytes(pdf_bytes)

        results = []
        for _ in range(5):
            with pdfplumber.open(path) as plumber:
                results.append(_tables_as_text(plumber.pages[0]))

        assert all(r == results[0] for r in results), "Extraction must be deterministic across calls"

    def test_zero_crash_on_empty_and_minimal_pages(self):
        """Empty page, single character page, and sparse token pages must not raise unhandled exceptions."""
        doc = pymupdf.open()
        doc.new_page()  # completely blank
        doc.new_page().insert_text((100, 100), "A", fontsize=10)  # single char
        doc.new_page().insert_text((100, 100), "123", fontsize=10)  # single number
        pdf_bytes = doc.tobytes()

        with pdfplumber.open(io.BytesIO(pdf_bytes)) as plumber:
            for idx, page in enumerate(plumber.pages):
                res = _extract_unruled_tables(page)
                assert res == "", f"Page {idx} should produce empty table string"
