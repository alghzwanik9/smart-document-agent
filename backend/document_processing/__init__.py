"""Reading uploaded documents into plain text. `parse_document` picks the parser by file type."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

OcrPage = Callable[[bytes], str]   # PNG bytes of one page -> its text


class ProcessingError(Exception):
    """A failure whose message is safe to store in `documents.error_message` and show to the user."""


@dataclass
class ParsedDocument:
    text: str
    pages: int = 0          # PDF pages, or sheets for Excel; 0 when the format has no such notion
    ocr_pages: int = 0      # scanned PDF pages that were read by OCR


def parse_document(path: Path, file_type: str, ocr_page: OcrPage | None = None) -> ParsedDocument:
    # Imported here so the heavy libraries load only when a document of that type arrives.
    if file_type == "PDF":
        from document_processing.pdf_parser import parse_pdf
        return parse_pdf(path, ocr_page)
    if file_type in ("XLSX", "CSV"):
        from document_processing.excel_parser import parse_excel
        return parse_excel(path, file_type)
    if file_type == "DOCX":
        from document_processing.word_parser import parse_word
        return parse_word(path)
    raise ProcessingError(f"Unsupported file type: {file_type}")
