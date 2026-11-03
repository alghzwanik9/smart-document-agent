"""PDF to text: PyMuPDF for the text and for rendering scanned pages, pdfplumber for the tables."""
from __future__ import annotations

import unicodedata
from pathlib import Path

import pdfplumber
import pymupdf

from document_processing import OcrPage, ParsedDocument, ProcessingError

MIN_TEXT_CHARS = 20     # a page with less text than this is an image of a page
OCR_DPI = 200


def parse_pdf(path: Path, ocr_page: OcrPage | None = None) -> ParsedDocument:
    parts: list[str] = []
    scanned = 0
    try:
        with pymupdf.open(path) as pdf, pdfplumber.open(path) as plumber:
            for number, (page, table_page) in enumerate(zip(pdf, plumber.pages), start=1):
                text = plain_letters(page.get_text()).strip()
                tables = ""
                if len(text) < MIN_TEXT_CHARS:
                    if ocr_page is None:
                        raise ProcessingError(f"Page {number} is a scan and no OCR is available")
                    text = ocr_page(page.get_pixmap(dpi=OCR_DPI).tobytes("png"))
                    scanned += 1
                else:
                    tables = _tables_as_text(table_page)
                parts.append(f"--- page {number} ---\n{text}" + (f"\n{tables}" if tables else ""))
            pages = pdf.page_count
    except ProcessingError:
        raise
    except Exception as exc:    # a corrupt, encrypted or truncated file: the message never carries its content
        raise ProcessingError(f"The PDF could not be read ({type(exc).__name__})") from exc
    return ParsedDocument(text="\n".join(parts), pages=pages, ocr_pages=scanned)


def plain_letters(text: str) -> str:
    """Many PDFs store Arabic as shaped glyphs (presentation forms); NFKC turns them back into the plain letters
    a person and the model read, so a name is stored as a name."""
    return unicodedata.normalize("NFKC", text)


def _tables_as_text(page) -> str:
    rows = []
    for table in page.extract_tables():
        rows.extend(" | ".join(plain_letters((cell or "").strip()) for cell in row) for row in table)
    return "\n".join(rows)
