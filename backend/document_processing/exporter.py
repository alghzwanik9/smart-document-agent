"""Puts corrected values back into a copy of the original file, in the original format.

Every format is read as rows of slots (a spreadsheet row, a Word table row, a line of a PDF page). A record is
matched to the row that holds the most of its extracted values, then each corrected value replaces the slot that held
its original value. A correction whose slot is not one and only one is reported, never guessed.
"""
from __future__ import annotations

import csv
import io
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence

from core.schemas import parse_amount
from document_processing.excel_parser import cell_text, read_csv
from document_processing.llm_extractor import NUMERIC_FIELDS

# file type -> (export format, media type)
FORMATS = {
    "XLSX": ("xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
    "CSV": ("csv", "text/csv; charset=utf-8"),
    "DOCX": ("docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
    "PDF": ("pdf", "application/pdf"),
}
PDF_NGRAM = 4              # the longest run of words on one line that can be one value ("Ahmed Ali Hassan Omar")
ARABIC_RANGE = range(0x0600, 0x0700)


class ExportError(Exception):
    """The export cannot be made; the message is safe to show the user."""


@dataclass
class ExportResult:
    data: bytes
    media_type: str
    extension: str
    unplaced: list[int]     # ids of corrected fields whose place in the file was not found


@dataclass(frozen=True)
class Slot:
    text: str                               # what the file holds there, whitespace collapsed
    amount: str | None                      # the same as a canonical number, when it reads as one
    write: Callable[[str, bool], None]      # (corrected value, whether the field is an amount)


Row = list[Slot]


def export_document(path: Path, file_type: str, fields: Sequence, fmt: str | None = None) -> ExportResult:
    """`fields` are `extracted_fields` rows (id, record_index, field_name, original_value, corrected_value,
    is_corrected). The file at `path` is only read."""
    if file_type not in FORMATS:
        raise ExportError(f"Unsupported file type: {file_type}")
    native, media_type = FORMATS[file_type]
    if fmt is not None and fmt.lower() != native:
        raise ExportError(f"A {file_type} document is exported as {native}, not {fmt}")
    build = {"XLSX": _export_xlsx, "CSV": _export_csv, "DOCX": _export_docx, "PDF": _export_pdf}[file_type]
    try:
        data, unplaced = build(path, list(fields))
    except ExportError:
        raise
    except Exception as exc:
        raise ExportError(f"The file could not be exported ({type(exc).__name__})") from exc
    return ExportResult(data=data, media_type=media_type, extension=native, unplaced=unplaced)


# ---------------------------------------------------------------------- matching
def _collapse(text: str) -> str:
    """Whitespace collapsed and Arabic presentation forms made plain, as the parser stored the values."""
    return " ".join(unicodedata.normalize("NFKC", text).split())


def _canonical_amount(text: str) -> str | None:
    try:
        number = parse_amount(text)
    except ValueError:
        return None
    return None if number is None else repr(float(number))


def _slot(text: str, write: Callable[[str, bool], None]) -> Slot:
    text = _collapse(text)
    return Slot(text=text, amount=_canonical_amount(text), write=write)


def _probe(field) -> tuple[str, str] | None:
    """What to look for in a row to find the place of a field's original value."""
    original = field.original_value
    if original is None or not original.strip():
        return None
    if field.field_name in NUMERIC_FIELDS:
        amount = _canonical_amount(original)
        if amount is not None:
            return "a", amount
    return "t", _collapse(original)


def _holds(slot: Slot, probe: tuple[str, str]) -> bool:
    return slot.amount == probe[1] if probe[0] == "a" else slot.text == probe[1]


def place_corrections(rows: list[Row], fields: list) -> list[int]:
    """Writes every corrected field into its slot and returns the ids of those it could not place."""
    index: dict[tuple[str, str], set[int]] = defaultdict(set)
    for number, row in enumerate(rows):
        for slot in row:
            index[("t", slot.text)].add(number)
            if slot.amount is not None:
                index[("a", slot.amount)].add(number)

    records: dict[int, list] = defaultdict(list)
    for item in fields:
        records[item.record_index].append(item)

    unplaced: list[int] = []
    claimed: set[int] = set()
    for _, record in sorted(records.items()):
        probes = {item.id: _probe(item) for item in record}
        score: Counter[int] = Counter()
        for probe in {p for p in probes.values() if p is not None}:
            score.update(index.get(probe, set()) - claimed)
        wanted = [item for item in record if item.is_corrected]
        if not score:
            unplaced.extend(item.id for item in wanted)
            continue
        row_number = max(score, key=lambda number: (score[number], -number))
        claimed.add(row_number)
        row = rows[row_number]

        by_probe: dict[tuple[str, str], list] = defaultdict(list)
        for item in record:
            if probes[item.id] is not None:
                by_probe[probes[item.id]].append(item)
        for item in wanted:
            probe = probes[item.id]
            slots = [] if probe is None else [slot for slot in row if _holds(slot, probe)]
            if probe is None or len(by_probe[probe]) > 1 or len(slots) != 1:
                unplaced.append(item.id)
            else:
                slots[0].write(item.corrected_value or "", item.field_name in NUMERIC_FIELDS)
    return unplaced


# ---------------------------------------------------------------------- xlsx
def _export_xlsx(path: Path, fields: list) -> tuple[bytes, list[int]]:
    import openpyxl

    values = openpyxl.load_workbook(path, data_only=True)       # what the extractor saw: cached results of formulas
    workbook = openpyxl.load_workbook(path)                     # what is written back: formulas and styles intact
    rows: list[Row] = []
    for sheet in workbook.worksheets:
        shown = values[sheet.title]
        for cells in sheet.iter_rows():
            row = []
            for cell in cells:
                text = cell_text(shown[cell.coordinate].value)
                if text:
                    row.append(_slot(text, _xlsx_writer(cell)))
            if row:
                rows.append(row)
    unplaced = place_corrections(rows, fields)
    out = io.BytesIO()
    workbook.save(out)
    return out.getvalue(), unplaced


def _xlsx_writer(cell) -> Callable[[str, bool], None]:
    def write(value: str, amount: bool) -> None:
        number = parse_amount(value) if amount and _canonical_amount(value) is not None else None
        if number is not None:
            cell.value = int(number) if number.is_integer() else number
        else:
            cell.value = value or None
    return write


# ---------------------------------------------------------------------- csv
def _export_csv(path: Path, fields: list) -> tuple[bytes, list[int]]:
    table, encoding, dialect = read_csv(path)
    rows: list[Row] = []
    for line in table:
        row = [_slot(value, _csv_writer(line, column)) for column, value in enumerate(line) if value.strip()]
        if row:
            rows.append(row)
    unplaced = place_corrections(rows, fields)
    out = io.StringIO()
    csv.writer(out, dialect).writerows(table)
    text = out.getvalue()
    try:
        return text.encode(encoding), unplaced
    except UnicodeEncodeError:      # a corrected value the old encoding cannot hold: UTF-8 opens in Excel and everywhere
        return text.encode("utf-8-sig"), unplaced


def _csv_writer(line: list[str], column: int) -> Callable[[str, bool], None]:
    def write(value: str, amount: bool) -> None:
        line[column] = value
    return write


# ---------------------------------------------------------------------- docx
def _export_docx(path: Path, fields: list) -> tuple[bytes, list[int]]:
    import docx

    document = docx.Document(str(path))
    rows: list[Row] = []
    for table in document.tables:
        for table_row in table.rows:
            seen: set[int] = set()      # a merged cell is returned once per column it spans
            row = []
            for cell in table_row.cells:
                if id(cell._tc) in seen or not cell.text.strip():
                    continue
                seen.add(id(cell._tc))
                row.append(_slot(cell.text, _docx_writer(cell)))
            if row:
                rows.append(row)
    unplaced = place_corrections(rows, fields)
    out = io.BytesIO()
    document.save(out)
    return out.getvalue(), unplaced


def _docx_writer(cell) -> Callable[[str, bool], None]:
    def write(value: str, amount: bool) -> None:
        first, *others = cell.paragraphs
        for paragraph in others:
            paragraph._p.getparent().remove(paragraph._p)
        runs = first.runs
        if not runs:
            first.add_run(value)
            return
        runs[0].text = value                # the first run carries the cell's font, size and weight
        for run in runs[1:]:
            run._r.getparent().remove(run._r)
    return write


# ---------------------------------------------------------------------- pdf (best effort)
def _export_pdf(path: Path, fields: list) -> tuple[bytes, list[int]]:
    import pymupdf

    edits: list[tuple[int, "pymupdf.Rect", str]] = []
    with pymupdf.open(path) as pdf:
        rows: list[Row] = []
        for page in pdf:
            for line in _pdf_lines(page.get_text("words")):
                rows.append(_pdf_slots(page.number, line, edits))
        unplaced = place_corrections([row for row in rows if row], fields)
        for page_number, group in _group_by_page(edits).items():
            page = pdf[page_number]
            for rect, _ in group:
                page.add_redact_annot(rect, fill=(1, 1, 1))     # removes the old text itself, not only hides it
            page.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_NONE)
            for rect, value in group:
                _draw_value(page, rect, value)
        return pdf.tobytes(garbage=3, deflate=True), unplaced


def _group_by_page(edits) -> dict[int, list]:
    grouped: dict[int, list] = defaultdict(list)
    for page_number, rect, value in edits:
        grouped[page_number].append((rect, value))
    return grouped


def _pdf_lines(words: list) -> list[list]:
    """Words grouped into visual lines (same height on the page), each line ordered from left to right."""
    lines: list[list] = []
    for word in sorted(words, key=lambda w: (w[1] + w[3]) / 2):
        middle, height = (word[1] + word[3]) / 2, word[3] - word[1]
        if lines and abs(middle - lines[-1][0]) <= 0.6 * height:
            lines[-1][1].append(word)
        else:
            lines.append([middle, [word]])
    return [sorted(words_of_line, key=lambda w: w[0]) for _, words_of_line in lines]


def _pdf_slots(page_number: int, line: list, edits: list) -> Row:
    """Each word and each run of neighbouring words is a slot, read in both directions for right-to-left text."""
    import pymupdf

    slots: Row = []
    for start in range(len(line)):
        for length in range(1, min(PDF_NGRAM, len(line) - start) + 1):
            chunk = line[start:start + length]
            rect = pymupdf.Rect(chunk[0][:4])
            for word in chunk[1:]:
                rect |= pymupdf.Rect(word[:4])
            writer = _pdf_writer(page_number, rect, edits)
            slots.append(_slot(" ".join(w[4] for w in chunk), writer))
            if length > 1:
                slots.append(_slot(" ".join(w[4] for w in reversed(chunk)), writer))
    return slots


def _pdf_writer(page_number: int, rect, edits: list) -> Callable[[str, bool], None]:
    def write(value: str, amount: bool) -> None:
        edits.append((page_number, rect, value))
    return write


def _draw_value(page, rect, value: str) -> None:
    from html import escape

    rtl = any(ord(ch) in ARABIC_RANGE for ch in value)
    direction, align = ("rtl", "right") if rtl else ("ltr", "left")
    page.insert_htmlbox(rect + (-1, -1, 1, 1), f'<div dir="{direction}" style="text-align:{align}">{escape(value)}</div>',
                        css=f"* {{ font-size: {rect.height * 0.8:.1f}px; line-height: 1; }}", scale_low=0.3)
