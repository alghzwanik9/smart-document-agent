"""Adversarial stress-testing harness for Milestone M1 (Unruled PDF Table Extraction).
Empirical verification of boundary cases, false positives, ruled table preservation,
and Arabic RTL orientation.
"""
from __future__ import annotations

import io
import os
from pathlib import Path
from typing import Any

import pdfplumber
import pymupdf
import pytest

from document_processing import parse_document
from document_processing.pdf_parser import _extract_unruled_tables, _tables_as_text, parse_pdf
from document_processing.table_extractor import build_records, find_tables, map_by_synonyms
from tests import samples
from tests.test_pdf_parser import _find_arabic_font, make_unruled_arabic_pdf, make_unruled_pdf


# ==============================================================================
# 1. Non-Tabular Documents: False Positive Resistance
# ==============================================================================

def test_adversarial_free_text_paragraphs_with_justified_wide_spacing(tmp_path):
    """Paragraphs with justified or uneven inter-word spacing must not be split into table columns."""
    doc = pymupdf.open()
    page = doc.new_page()

    lines = [
        "In  accordance  with  company  regulations  and  standard  operating  procedures.",
        "The   quarterly   financial   performance   evaluation   remains   under   review.",
        "Executive   leadership   confirmed   all   budgetary   allocations   are   finalized.",
        "Staff   members   are   encouraged   to   submit   travel   expenses   promptly.",
    ]
    for i, line in enumerate(lines):
        page.insert_text((50, 80 + i * 25), line, fontsize=10)

    path = tmp_path / "justified_text.pdf"
    path.write_bytes(doc.tobytes())

    with pdfplumber.open(path) as plumber:
        extracted = _tables_as_text(plumber.pages[0])
        assert extracted == "", f"Expected empty table text, got: {extracted!r}"


def test_adversarial_invoice_scattered_metadata_2col(tmp_path):
    """Invoices with 2 key-value pairs per line must not produce phantom tables."""
    doc = pymupdf.open()
    page = doc.new_page()

    metadata_lines = [
        ("Invoice Number: INV-2026-0042", 50, "Date: 2026-11-10", 380),
        ("Customer ID: CUST-9901", 50, "Due Date: 2026-12-10", 380),
        ("Purchase Order: PO-5521", 50, "Payment Method: Wire Transfer", 380),
        ("Billing Contact: John Doe", 50, "Currency: USD", 380),
    ]
    for y_idx, (left_text, left_x, right_text, right_x) in enumerate(metadata_lines):
        y = 60 + y_idx * 25
        page.insert_text((left_x, y), left_text, fontsize=10)
        page.insert_text((right_x, y), right_text, fontsize=10)

    path = tmp_path / "invoice_metadata_2col.pdf"
    path.write_bytes(doc.tobytes())

    with pdfplumber.open(path) as plumber:
        extracted = _tables_as_text(plumber.pages[0])
        assert extracted == "", f"Scattered 2-item metadata should not produce table, got: {extracted!r}"


def test_adversarial_staggered_3col_metadata_without_grid_alignment(tmp_path):
    """Invoices where line 1 has 3 metadata items and line 2 has 2 metadata items
    at staggered coordinates must NOT produce a phantom 3-column table.
    """
    doc = pymupdf.open()
    page = doc.new_page()

    page.insert_text((50, 50), "Vendor: Global Solutions Corp", fontsize=9)
    page.insert_text((240, 50), "Tax ID: 123-456-789", fontsize=9)
    page.insert_text((420, 50), "Invoice: #99281", fontsize=9)

    page.insert_text((50, 75), "Client: Standard Systems Ltd", fontsize=9)
    page.insert_text((350, 75), "Terms: Net 30 Days", fontsize=9)

    page.insert_text((50, 100), "Project: Implementation Phase 4 Deployment Review", fontsize=9)

    path = tmp_path / "staggered_metadata.pdf"
    path.write_bytes(doc.tobytes())

    with pdfplumber.open(path) as plumber:
        extracted = _tables_as_text(plumber.pages[0])
        assert extracted == "", f"Staggered non-grid metadata should not produce table, got: {extracted!r}"


test_adversarial_invoice_scattered_staggered_metadata_produces_phantom_table = (
    test_adversarial_staggered_3col_metadata_without_grid_alignment
)


def test_adversarial_three_column_article_resistance(tmp_path):
    """3-column prose/narrative articles must not be extracted as tables."""
    doc = pymupdf.open()
    page = doc.new_page()

    c1 = [
        "First column introduction detailing comprehensive company operational background information.",
        "Second row continuing operational developments and strategic management updates here.",
        "Third row updating quarterly organizational status and executive planning reports.",
    ]
    c2 = [
        "Middle column economic news analysis across diverse national commercial sectors.",
        "Domestic market growth expanded significantly during the previous financial quarter.",
        "Financial equities reached highest historic peak recorded in modern trading.",
    ]
    c3 = [
        "Right column weather conditions in Riyadh central administrative province today.",
        "Moderate temperature forecasted throughout the coming weekend holiday period.",
        "Precipitation patterns recorded in northern agricultural district territory.",
    ]

    for i in range(3):
        y = 60 + i * 25
        page.insert_text((50, y), c1[i], fontsize=9)
        page.insert_text((220, y), c2[i], fontsize=9)
        page.insert_text((400, y), c3[i], fontsize=9)

    path = tmp_path / "three_column_article.pdf"
    path.write_bytes(doc.tobytes())

    with pdfplumber.open(path) as plumber:
        extracted = _tables_as_text(plumber.pages[0])
        assert extracted == "", f"3-column prose article should not produce table, got: {extracted!r}"


test_adversarial_three_column_article_produces_phantom_table = test_adversarial_three_column_article_resistance


def test_adversarial_three_part_bullet_list_resistance(tmp_path):
    """3-part bullet lists (bullet, title, description) must not produce tables."""
    doc = pymupdf.open()
    page = doc.new_page()

    page.insert_text((50, 50), "1.", fontsize=10)
    page.insert_text((80, 50), "Introduction", fontsize=10)
    page.insert_text((200, 50), "This section explains the overview of project architecture and design.", fontsize=10)

    page.insert_text((50, 80), "2.", fontsize=10)
    page.insert_text((80, 80), "Methodology", fontsize=10)
    page.insert_text((200, 80), "This section details the empirical testing harness and verification plan.", fontsize=10)

    path = tmp_path / "numbered_list.pdf"
    path.write_bytes(doc.tobytes())

    with pdfplumber.open(path) as plumber:
        extracted = _tables_as_text(plumber.pages[0])
        assert extracted == "", f"Numbered list should not produce table, got: {extracted!r}"


test_adversarial_three_part_bullet_list_produces_phantom_table = test_adversarial_three_part_bullet_list_resistance


def test_adversarial_bullet_list_resistance_2part(tmp_path):
    """2-part bullet lists (bullet + text) correctly do not produce tables."""
    doc = pymupdf.open()
    page = doc.new_page()

    bullet_items = [
        "1. Executive Overview and Background Documentation for Phase 4.",
        "2. Deterministic Quality Assurance and Anomaly Detection Rules.",
        "3. Integration Testing and Regression Verification on Endpoints.",
        "4. Deployment Packaging with Docker Compose and Containerization.",
    ]
    for i, item in enumerate(bullet_items):
        page.insert_text((60, 80 + i * 30), item, fontsize=10)

    path = tmp_path / "bullet_list.pdf"
    path.write_bytes(doc.tobytes())

    with pdfplumber.open(path) as plumber:
        extracted = _tables_as_text(plumber.pages[0])
        assert extracted == "", f"Bullet list should not produce table, got: {extracted!r}"


def test_adversarial_two_column_article_layout(tmp_path):
    """Two-column narrative text correctly returns empty table."""
    doc = pymupdf.open()
    page = doc.new_page()

    col1 = ["First column of text.", "Sentence of news.", "Economic situation."]
    col2 = ["Second column technology.", "Artificial intelligence.", "Deterministic algorithms."]

    for i in range(3):
        y = 60 + i * 20
        page.insert_text((50, y), col1[i], fontsize=9)
        page.insert_text((300, y), col2[i], fontsize=9)

    path = tmp_path / "two_column_article.pdf"
    path.write_bytes(doc.tobytes())

    with pdfplumber.open(path) as plumber:
        extracted = _tables_as_text(plumber.pages[0])
        assert extracted == ""


# ==============================================================================
# 2. Ruled Table Preservation: Regression Resistance
# ==============================================================================

def test_adversarial_ruled_table_preservation():
    """Ruled table with vector lines extracts cleanly via extract_tables()."""
    data = samples.pdf_table_bytes()
    with pdfplumber.open(io.BytesIO(data)) as plumber:
        page = plumber.pages[0]
        assert len(page.extract_tables()) >= 1
        text = _tables_as_text(page)
        assert "Ahmed Ali" in text
        assert "5000" in text


# ==============================================================================
# 3. Arabic RTL Orientation & Direction Detection Vulnerabilities
# ==============================================================================

def test_adversarial_arabic_unruled_pure_arabic_works(tmp_path):
    """Pure Arabic RTL table extracts columns Right-to-Left (Col 0 = الاسم)."""
    rows = [
        ("الاسم", "الرقم", "الاساسي", "الصافي"),
        ("محمد المنصور", "101", "12000", "12000"),
        ("فاطمة الزهراء", "102", "15000", "15000"),
    ]
    xs = [450.0, 330.0, 210.0, 90.0]
    path = tmp_path / "pure_arabic.pdf"
    path.write_bytes(make_unruled_arabic_pdf(rows, xs=xs))

    with pdfplumber.open(path) as plumber:
        extracted = _tables_as_text(plumber.pages[0])
        assert extracted
        header_cells = extracted.splitlines()[0].split(" | ")
        assert "الاسم" in header_cells[0]
        assert "الصافي" in header_cells[3]


def test_adversarial_arabic_table_with_english_names_preserves_rtl(tmp_path):
    """Arabic RTL table with English/multinational employee names must preserve RTL orientation (Col 0 = الاسم)."""
    doc = pymupdf.open()
    page = doc.new_page()
    font_file = _find_arabic_font()
    if font_file:
        page.insert_font(fontname="f", fontfile=font_file)

    header = ["الاسم", "الرقم", "الاساسي", "الصافي"]
    xs = [450.0, 330.0, 210.0, 90.0]
    for c, val in enumerate(header):
        page.insert_text((xs[c], 60), val, fontname="f" if font_file else None, fontsize=10)

    # 4 rows of English employee names
    data = [
        ("John Smith Doe", "E001", "5000", "5000"),
        ("David James Brown", "E002", "6000", "6000"),
        ("Michael George White", "E003", "7000", "7000"),
        ("Robert William Clark", "E004", "8000", "8000"),
    ]
    for r, row in enumerate(data):
        y = 90 + r * 25
        for c, val in enumerate(row):
            page.insert_text((xs[c], y), val, fontsize=10)

    path = tmp_path / "arabic_with_english_names.pdf"
    path.write_bytes(doc.tobytes())

    with pdfplumber.open(path) as plumber:
        extracted = _tables_as_text(plumber.pages[0])
        assert extracted, "Arabic table with English names must extract"
        header_first_cell = extracted.splitlines()[0].split(" | ")[0]
        assert header_first_cell == "الاسم", f"Expected RTL header 'الاسم' at Col 0, got {header_first_cell!r}"
        header_last_cell = extracted.splitlines()[0].split(" | ")[3]
        assert header_last_cell == "الصافي", f"Expected RTL header 'الصافي' at Col 3, got {header_last_cell!r}"


test_adversarial_arabic_table_with_english_names_inverts_to_ltr = (
    test_adversarial_arabic_table_with_english_names_preserves_rtl
)


def test_adversarial_english_table_with_arabic_footnote_preserves_ltr(tmp_path):
    """Standard English LTR table on a page with an Arabic footnote must preserve LTR orientation (Col 0 = Name)."""
    doc = pymupdf.open()
    page = doc.new_page()
    font_file = _find_arabic_font()
    if font_file:
        page.insert_font(fontname="f", fontfile=font_file)

    # English table laid out Left-to-Right: Name, ID, Basic, Net
    rows = [
        ("Name", "ID", "Basic", "Net"),
        ("John", "E1", "5000", "5000"),
        ("Mary", "E2", "6000", "6000"),
    ]
    for r, row in enumerate(rows):
        y = 60 + r * 25
        for c, val in enumerate(row):
            page.insert_text((50 + c * 100, y), val, fontsize=10)

    # Arabic footnote at bottom (10 Arabic words)
    arabic_note = "ملاحظات هامة جدا هذا المستند سري للغاية ومخصص لقسم الموارد البشرية فقط"
    page.insert_text((50, 200), arabic_note, fontname="f" if font_file else None, fontsize=10)

    path = tmp_path / "english_table_arabic_note.pdf"
    path.write_bytes(doc.tobytes())

    with pdfplumber.open(path) as plumber:
        extracted = _tables_as_text(plumber.pages[0])
        assert extracted, "English table must extract"
        header_first_cell = extracted.splitlines()[0].split(" | ")[0]
        assert header_first_cell == "Name", f"Expected LTR header 'Name' at Col 0, got {header_first_cell!r}"
        header_last_cell = extracted.splitlines()[0].split(" | ")[3]
        assert header_last_cell == "Net", f"Expected LTR header 'Net' at Col 3, got {header_last_cell!r}"


test_adversarial_english_table_with_arabic_footnote_inverts_to_rtl = (
    test_adversarial_english_table_with_arabic_footnote_preserves_ltr
)
