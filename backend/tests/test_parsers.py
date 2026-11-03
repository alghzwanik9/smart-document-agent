import pytest

from document_processing import ProcessingError, parse_document
from tests import samples


def write(tmp_path, name, data):
    path = tmp_path / name
    path.write_bytes(data)
    return path


def test_xlsx_rows_become_lines(tmp_path):
    parsed = parse_document(write(tmp_path, "a.xlsx", samples.xlsx_bytes()), "XLSX")
    assert "--- sheet: June ---" in parsed.text
    assert "Ahmed Ali | E001 | 5000 | 500 | 200 | 5300" in parsed.text
    assert parsed.pages == 1


def test_xlsx_skips_empty_rows(tmp_path):
    rows = [("Name", "Net"), (None, None), ("Sara", 5700)]
    parsed = parse_document(write(tmp_path, "a.xlsx", samples.xlsx_bytes(rows)), "XLSX")
    assert parsed.text.splitlines() == ["--- sheet: June ---", "Name | Net", "Sara | 5700"]


def test_csv_with_a_semicolon_delimiter(tmp_path):
    parsed = parse_document(write(tmp_path, "a.csv", samples.csv_bytes(delimiter=";")), "CSV")
    assert "Ahmed Ali | E001 | 5000 | 500 | 200 | 5300" in parsed.text


def test_csv_in_the_windows_arabic_encoding(tmp_path):
    rows = [("الاسم", "الصافي"), ("أحمد", 5300)]
    parsed = parse_document(write(tmp_path, "a.csv", samples.csv_bytes(rows, encoding="cp1256")), "CSV")
    assert "أحمد | 5300" in parsed.text


def test_docx_paragraphs_and_tables_in_order(tmp_path):
    lines = parse_document(write(tmp_path, "a.docx", samples.docx_bytes()), "DOCX").text.splitlines()
    assert lines[0] == "Payroll sheet June"
    assert "Ahmed Ali | E001 | 5000 | 500 | 200 | 5300" in lines


def test_pdf_text_layer(tmp_path):
    parsed = parse_document(write(tmp_path, "a.pdf", samples.pdf_bytes()), "PDF")
    assert "Ahmed Ali E001 basic 5000 net 5300" in parsed.text
    assert parsed.pages == 1 and parsed.ocr_pages == 0


def test_pdf_arabic_presentation_forms_become_plain_letters(tmp_path):
    path = tmp_path / "a.pdf"
    path.write_bytes(samples.arabic_pdf_bytes())

    text = parse_document(path, "PDF").text

    assert "أحمد عمر" in text
    assert not any("ﭐ" <= ch <= "﻿" for ch in text)


def test_scanned_pdf_page_goes_through_ocr(tmp_path):
    seen = []

    def ocr(png: bytes) -> str:
        seen.append(png[:4])
        return "text read by ocr"

    parsed = parse_document(write(tmp_path, "scan.pdf", samples.scanned_pdf_bytes()), "PDF", ocr)
    assert seen == [b"\x89PNG"]            # the page was rendered to a PNG image
    assert "text read by ocr" in parsed.text and parsed.ocr_pages == 1


def test_scanned_pdf_without_ocr_says_so(tmp_path):
    with pytest.raises(ProcessingError, match="scan"):
        parse_document(write(tmp_path, "scan.pdf", samples.scanned_pdf_bytes()), "PDF", None)


def test_a_corrupt_file_fails_cleanly_without_leaking_content(tmp_path):
    with pytest.raises(ProcessingError) as failed:
        parse_document(write(tmp_path, "a.xlsx", b"PK\x03\x04 broken secret-salary-data"), "XLSX")
    assert "secret-salary-data" not in str(failed.value)


def test_an_unsupported_type_is_refused(tmp_path):
    with pytest.raises(ProcessingError):
        parse_document(tmp_path / "x", "EXE")
