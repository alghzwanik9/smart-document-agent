"""Small real files of every supported type, built in memory for the tests."""
from __future__ import annotations

import io

import docx
import openpyxl
import pymupdf
from PIL import Image

ROWS = [
    ("Name", "ID", "Basic", "Allowances", "Deductions", "Net"),
    ("Ahmed Ali", "E001", 5000, 500, 200, 5300),
    ("Sara Omar", "E002", 6000, 0, 300, 5700),
]


def xlsx_bytes(rows=ROWS) -> bytes:
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "June"
    for row in rows:
        sheet.append(row)
    out = io.BytesIO()
    workbook.save(out)
    return out.getvalue()


def csv_bytes(rows=ROWS, delimiter=",", encoding="utf-8") -> bytes:
    return "\n".join(delimiter.join(str(c) for c in row) for row in rows).encode(encoding)


def docx_bytes(rows=ROWS) -> bytes:
    document = docx.Document()
    document.add_paragraph("Payroll sheet June")
    table = document.add_table(rows=len(rows), cols=len(rows[0]))
    for r, row in enumerate(rows):
        for c, value in enumerate(row):
            table.cell(r, c).text = str(value)
    out = io.BytesIO()
    document.save(out)
    return out.getvalue()


def pdf_bytes(lines=("Payroll sheet June", "Ahmed Ali E001 basic 5000 net 5300")) -> bytes:
    pdf = pymupdf.open()
    page = pdf.new_page()
    for number, line in enumerate(lines):
        page.insert_text((72, 72 + number * 20), line)
    return pdf.tobytes()


def scanned_pdf_bytes() -> bytes:
    """A page that holds only a picture, so it has no text layer and needs OCR."""
    image = Image.new("RGB", (200, 80), "white")
    png = io.BytesIO()
    image.save(png, "PNG")
    pdf = pymupdf.open()
    page = pdf.new_page()
    page.insert_image(pymupdf.Rect(72, 72, 272, 152), stream=png.getvalue())
    return pdf.tobytes()


def arabic_pdf_bytes(name="أحمد عمر", rest="E001 basic 5000 net 5300") -> bytes:
    """A text PDF whose Arabic is shaped, so its text layer holds Arabic presentation forms (as many real PDFs do).
    The name avoids lam: the engine's built-in font maps a joined lam to a wrong character."""
    pdf = pymupdf.open()
    page = pdf.new_page()
    page.insert_htmlbox(pymupdf.Rect(40, 40, 560, 200), f"<p>{name} {rest}</p>")
    return pdf.tobytes()


def pdf_table_bytes(rows=ROWS) -> bytes:
    """A PDF whose payroll is a ruled table, as most exported payroll PDFs are; pdfplumber finds it by its lines."""
    pdf = pymupdf.open()
    page = pdf.new_page()
    x0, y0, width, height = 40, 60, 85, 24
    for r, row in enumerate(rows):
        for c, value in enumerate(row):
            cell = pymupdf.Rect(x0 + c * width, y0 + r * height, x0 + (c + 1) * width, y0 + (r + 1) * height)
            page.draw_rect(cell, width=0.8)
            page.insert_text((cell.x0 + 4, cell.y1 - 8), str(value), fontsize=10)
    return pdf.tobytes()
