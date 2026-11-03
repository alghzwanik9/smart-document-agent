"""Excel and CSV to text, one line per non-empty row with the cells joined by ' | '."""
from __future__ import annotations

import codecs
import csv
import io
from datetime import date, datetime
from pathlib import Path

import openpyxl

from document_processing import ParsedDocument, ProcessingError

CSV_ENCODINGS = ("utf-8-sig", "cp1256")   # Arabic files from Excel on Windows are often cp1256
CSV_DELIMITERS = ",;\t|"


def parse_excel(path: Path, file_type: str) -> ParsedDocument:
    try:
        return _parse_csv(path) if file_type == "CSV" else _parse_xlsx(path)
    except ProcessingError:
        raise
    except Exception as exc:
        raise ProcessingError(f"The file could not be read ({type(exc).__name__})") from exc


def cell_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _row_line(cells) -> str:
    values = [cell_text(c) for c in cells]
    return " | ".join(values) if any(values) else ""


def _parse_xlsx(path: Path) -> ParsedDocument:
    workbook = openpyxl.load_workbook(path, data_only=True, read_only=True)
    try:
        parts = []
        for sheet in workbook.worksheets:
            lines = [line for line in (_row_line(row) for row in sheet.iter_rows(values_only=True)) if line]
            parts.append(f"--- sheet: {sheet.title} ---\n" + "\n".join(lines))
        return ParsedDocument(text="\n".join(parts), pages=len(workbook.worksheets))
    finally:
        workbook.close()


def read_csv(path: Path) -> tuple[list[list[str]], str, type[csv.Dialect]]:
    """The rows of a CSV file with the encoding and dialect it was read with, so an export can write it back the same."""
    raw = path.read_bytes()
    encoding = next((enc for enc in CSV_ENCODINGS if _decodes(raw, enc)), "latin-1")
    if encoding == "utf-8-sig" and not raw.startswith(codecs.BOM_UTF8):
        encoding = "utf-8"
    text = raw.decode(encoding)
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=CSV_DELIMITERS)
    except csv.Error:
        dialect = csv.excel
    return list(csv.reader(io.StringIO(text), dialect)), encoding, dialect


def _parse_csv(path: Path) -> ParsedDocument:
    rows, _, _ = read_csv(path)
    lines = [line for line in (_row_line(row) for row in rows) if line]
    return ParsedDocument(text="\n".join(lines), pages=0)


def _decodes(raw: bytes, encoding: str) -> bool:
    try:
        raw.decode(encoding)
        return True
    except UnicodeDecodeError:
        return False
