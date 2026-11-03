"""The exporter puts corrected values back into a copy of the original file, in the original format."""
from __future__ import annotations

import io
import unicodedata
from itertools import count
from types import SimpleNamespace

import docx
import openpyxl
import pymupdf
import pytest
from openpyxl.styles import Font

from document_processing.exporter import ExportError, export_document
from tests import samples

_ids = count(1)


def field(record, name, original, corrected=None):
    return SimpleNamespace(id=next(_ids), record_index=record, field_name=name, original_value=original,
                           corrected_value=corrected, is_corrected=corrected is not None)


def fields_of_sample(**corrected):
    """Both employees of `samples.ROWS`, with `corrected` replacing a value: {"0.net_salary": "5400"}."""
    originals = {
        0: {"employee_name": "Ahmed Ali", "employee_id": "E001", "basic_salary": "5000", "allowances": "500",
            "deductions": "200", "net_salary": "5300"},
        1: {"employee_name": "Sara Omar", "employee_id": "E002", "basic_salary": "6000", "allowances": "0",
            "deductions": "300", "net_salary": "5700"},
    }
    return [field(r, name, value, corrected.get(f"{r}.{name}"))
            for r, values in originals.items() for name, value in values.items()]


def write(tmp_path, name, data) -> object:
    path = tmp_path / name
    path.write_bytes(data)
    return path


# ---------------------------------------------------------------------- xlsx
def test_xlsx_corrected_amount_is_written_as_a_number_and_nothing_else_changes(tmp_path):
    path = write(tmp_path, "p.xlsx", samples.xlsx_bytes())
    result = export_document(path, "XLSX", fields_of_sample(**{"0.net_salary": "5400"}))

    sheet = openpyxl.load_workbook(io.BytesIO(result.data)).active
    assert sheet["F2"].value == 5400 and isinstance(sheet["F2"].value, int)
    changed = [c.coordinate for row in sheet.iter_rows() for c in row
               if c.value != openpyxl.load_workbook(path).active[c.coordinate].value]
    assert changed == ["F2"]
    assert result.unplaced == []
    assert result.extension == "xlsx" and "spreadsheetml" in result.media_type


def test_xlsx_keeps_styles_and_number_formats(tmp_path):
    workbook = openpyxl.load_workbook(io.BytesIO(samples.xlsx_bytes()))
    sheet = workbook.active
    sheet["A1"].font = Font(bold=True)
    sheet["F2"].number_format = "#,##0.00"
    out = io.BytesIO()
    workbook.save(out)
    path = write(tmp_path, "p.xlsx", out.getvalue())

    result = export_document(path, "XLSX", fields_of_sample(**{"0.net_salary": "5400"}))

    exported = openpyxl.load_workbook(io.BytesIO(result.data)).active
    assert exported["A1"].font.bold is True
    assert exported["F2"].number_format == "#,##0.00" and exported["F2"].value == 5400


def test_xlsx_the_same_value_in_two_rows_is_corrected_in_the_right_row(tmp_path):
    rows = [samples.ROWS[0], ("Ahmed Ali", "E001", 5000, 500, 200, 5300), ("Sara Omar", "E002", 6000, 0, 300, 5300)]
    path = write(tmp_path, "p.xlsx", samples.xlsx_bytes(rows))
    fields = [field(0, "employee_name", "Ahmed Ali"), field(0, "net_salary", "5300"),
              field(1, "employee_name", "Sara Omar"), field(1, "net_salary", "5300", "5350")]

    result = export_document(path, "XLSX", fields)

    sheet = openpyxl.load_workbook(io.BytesIO(result.data)).active
    assert [sheet[f"F{n}"].value for n in (2, 3)] == [5300, 5350]


def test_xlsx_an_amount_written_with_other_digits_is_still_found(tmp_path):
    rows = [samples.ROWS[0], ("أحمد علي", "E001", "٥٬٠٠٠", 500, 200, "5300")]
    path = write(tmp_path, "p.xlsx", samples.xlsx_bytes(rows))
    fields = [field(0, "employee_name", "أحمد علي"), field(0, "basic_salary", "5000", "5100")]

    result = export_document(path, "XLSX", fields)

    assert openpyxl.load_workbook(io.BytesIO(result.data)).active["C2"].value == 5100
    assert result.unplaced == []


def test_xlsx_formulas_stay_formulas(tmp_path):
    workbook = openpyxl.load_workbook(io.BytesIO(samples.xlsx_bytes()))
    workbook.active["F2"] = "=C2+D2-E2"
    out = io.BytesIO()
    workbook.save(out)
    path = write(tmp_path, "p.xlsx", out.getvalue())

    result = export_document(path, "XLSX", fields_of_sample(**{"0.employee_name": "Ahmad Ali"}))

    sheet = openpyxl.load_workbook(io.BytesIO(result.data)).active
    assert sheet["F2"].value == "=C2+D2-E2" and sheet["A2"].value == "Ahmad Ali"


def test_a_correction_that_cannot_be_placed_is_reported_not_guessed(tmp_path):
    path = write(tmp_path, "p.xlsx", samples.xlsx_bytes())
    missing = field(0, "net_salary", "9999", "1")
    ambiguous_pair = [field(1, "allowances", "0"), field(1, "deductions", "0", "10")]   # two cells hold "0"
    fields = [field(0, "employee_name", "Ahmed Ali"), missing, field(1, "employee_name", "Sara Omar"),
              *ambiguous_pair]

    result = export_document(path, "XLSX", fields)

    assert sorted(result.unplaced) == sorted([missing.id, ambiguous_pair[1].id])
    sheet = openpyxl.load_workbook(io.BytesIO(result.data)).active
    assert [c.value for c in sheet[3]] == list(samples.ROWS[2])


def test_a_correction_for_a_value_the_sheet_never_had_is_reported(tmp_path):
    path = write(tmp_path, "p.xlsx", samples.xlsx_bytes())
    never_read = field(0, "currency", None, "SAR")

    result = export_document(path, "XLSX", [field(0, "employee_name", "Ahmed Ali"), never_read])

    assert result.unplaced == [never_read.id]


def test_an_export_without_corrections_is_the_same_content(tmp_path):
    path = write(tmp_path, "p.xlsx", samples.xlsx_bytes())

    result = export_document(path, "XLSX", fields_of_sample())

    exported = openpyxl.load_workbook(io.BytesIO(result.data)).active
    assert [[c.value for c in row] for row in exported.iter_rows()] == [list(r) for r in samples.ROWS]


# ---------------------------------------------------------------------- csv
def test_csv_keeps_its_encoding_and_delimiter(tmp_path):
    rows = [samples.ROWS[0], ("أحمد علي", "E001", 5000, 500, 200, 5300)]
    path = write(tmp_path, "p.csv", samples.csv_bytes(rows, delimiter=";", encoding="cp1256"))
    fields = [field(0, "employee_name", "أحمد علي"), field(0, "net_salary", "5300", "5400")]

    result = export_document(path, "CSV", fields)

    lines = result.data.decode("cp1256").splitlines()
    assert lines[1] == "أحمد علي;E001;5000;500;200;5400"
    assert result.extension == "csv" and result.media_type.startswith("text/csv")


def test_csv_a_correction_the_old_encoding_cannot_hold_falls_back_to_utf8(tmp_path):
    path = write(tmp_path, "p.csv", samples.csv_bytes(encoding="cp1256"))

    result = export_document(path, "CSV", fields_of_sample(**{"0.employee_name": "Åsa 😀"}))

    assert "Åsa 😀" in result.data.decode("utf-8-sig")


# ---------------------------------------------------------------------- docx
def test_docx_corrected_cell_keeps_its_formatting(tmp_path):
    document = docx.Document(io.BytesIO(samples.docx_bytes()))
    document.tables[0].cell(1, 5).paragraphs[0].runs[0].bold = True
    out = io.BytesIO()
    document.save(out)
    path = write(tmp_path, "p.docx", out.getvalue())

    result = export_document(path, "DOCX", fields_of_sample(**{"0.net_salary": "5400"}))

    table = docx.Document(io.BytesIO(result.data)).tables[0]
    cell = table.cell(1, 5)
    assert cell.text == "5400" and cell.paragraphs[0].runs[0].bold is True
    assert table.cell(2, 5).text == "5700" and table.cell(0, 0).text == "Name"
    assert result.extension == "docx" and "wordprocessingml" in result.media_type


def test_docx_text_outside_a_table_is_not_guessed(tmp_path):
    document = docx.Document()
    document.add_paragraph("Employee Ahmed Ali net 5300")
    out = io.BytesIO()
    document.save(out)
    path = write(tmp_path, "p.docx", out.getvalue())
    net = field(0, "net_salary", "5300", "5400")

    result = export_document(path, "DOCX", [field(0, "employee_name", "Ahmed Ali"), net])

    assert result.unplaced == [net.id]
    assert docx.Document(io.BytesIO(result.data)).paragraphs[0].text == "Employee Ahmed Ali net 5300"


# ---------------------------------------------------------------------- pdf
def pdf_text(data: bytes) -> str:
    with pymupdf.open(stream=data, filetype="pdf") as pdf:
        return "\n".join(page.get_text() for page in pdf)


def test_pdf_the_old_value_is_removed_and_the_corrected_one_shown(tmp_path):
    path = write(tmp_path, "p.pdf", samples.pdf_bytes())
    fields = [field(0, "employee_name", "Ahmed Ali"), field(0, "basic_salary", "5000", "5100"),
              field(0, "net_salary", "5300")]

    result = export_document(path, "PDF", fields)

    text = pdf_text(result.data)
    assert "5100" in text and "5000" not in text and "5300" in text and "Ahmed Ali" in text
    assert result.unplaced == [] and result.extension == "pdf" and result.media_type == "application/pdf"


def test_pdf_a_multi_word_value_is_corrected(tmp_path):
    path = write(tmp_path, "p.pdf", samples.pdf_bytes())

    result = export_document(path, "PDF", [field(0, "employee_name", "Ahmed Ali", "Ahmad Ali"),
                                           field(0, "net_salary", "5300")])

    text = pdf_text(result.data)
    assert "Ahmad Ali" in text and "Ahmed Ali" not in text


def test_pdf_a_scanned_page_has_nothing_to_place_a_value_on(tmp_path):
    path = write(tmp_path, "scan.pdf", samples.scanned_pdf_bytes())
    net = field(0, "net_salary", "5300", "5400")

    result = export_document(path, "PDF", [net])

    assert result.unplaced == [net.id]


def test_pdf_an_arabic_value_stored_as_plain_letters_is_found_among_presentation_forms(tmp_path):
    path = write(tmp_path, "a.pdf", samples.arabic_pdf_bytes())
    fields = [field(0, "employee_name", "أحمد عمر", "أحمد سعد"), field(0, "basic_salary", "5000")]

    result = export_document(path, "PDF", fields)

    assert result.unplaced == []
    text = unicodedata.normalize("NFKC", pdf_text(result.data))
    assert "أحمد سعد" in text and "أحمد عمر" not in text


# ---------------------------------------------------------------------- formats
@pytest.mark.parametrize("file_type,fmt", [("XLSX", "docx"), ("DOCX", "xlsx"), ("PDF", "xlsx"), ("CSV", "pdf")])
def test_a_format_that_is_not_the_originals_is_refused(tmp_path, file_type, fmt):
    path = write(tmp_path, "p.xlsx", samples.xlsx_bytes())
    with pytest.raises(ExportError):
        export_document(path, file_type, [], fmt)


def test_the_original_format_can_be_named(tmp_path):
    path = write(tmp_path, "p.xlsx", samples.xlsx_bytes())
    assert export_document(path, "XLSX", [], "xlsx").extension == "xlsx"
