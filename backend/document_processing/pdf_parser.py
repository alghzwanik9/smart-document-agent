"""PDF to text: PyMuPDF for the text and for rendering scanned pages, pdfplumber for the tables."""
from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import Any

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
    a person and the model read, so a name is stored as a name. Soft hyphens and non-standard dashes are normalized to '-'."""
    normalized = unicodedata.normalize("NFKC", text)
    return re.sub(r"[\xad\u2010-\u2015\u2212\ufe63\uff0d]", "-", normalized)


def _tables_as_text(page) -> str:
    rows = []
    for table in page.extract_tables():
        for row in table:
            cleaned = [plain_letters((cell or "").strip()) for cell in row]
            if any(cleaned):
                rows.append(" | ".join(cleaned))
    if rows:
        return "\n".join(rows)
    return _extract_unruled_tables(page)


def _extract_unruled_tables(page, min_columns: int = 3, min_rows: int = 2) -> str:
    words = page.extract_words()
    if not words or len(words) < min_columns * min_rows:
        return ""

    arabic_pattern = re.compile(r"[\u0600-\u06FF\u0750-\u077F\uFB50-\uFDFF\uFE70-\uFEFC]")

    total_chars = sum(len(w["text"]) for w in words)
    total_width = sum(w["x1"] - w["x0"] for w in words)
    avg_char_w = (total_width / total_chars) if total_chars > 0 else 5.0
    avg_char_h = (sum(w["height"] for w in words) / len(words)) if words else 10.0

    word_gap_tol = max(5.0, min(12.0, avg_char_w * 2.0))
    line_y_tol = max(6.0, min(9.0, avg_char_h * 0.7))

    # 1. Group words into lines by vertical coordinate
    lines: list[dict[str, Any]] = []
    for w in sorted(words, key=lambda w: (w["top"], w["x0"])):
        placed = False
        for l in lines:
            if abs(l["top"] - w["top"]) <= line_y_tol:
                l["words"].append(w)
                l["top"] = (l["top"] * (len(l["words"]) - 1) + w["top"]) / len(l["words"])
                placed = True
                break
        if not placed:
            lines.append({"top": w["top"], "words": [w]})

    lines.sort(key=lambda l: l["top"])

    # 2. Cluster words into phrases/cells on each line
    candidate_lines: list[dict[str, Any]] = []
    for l in lines:
        ws = sorted(l["words"], key=lambda w: w["x0"])
        cells: list[list[dict[str, Any]]] = []
        curr = [ws[0]]
        for w in ws[1:]:
            if w["x0"] - curr[-1]["x1"] <= word_gap_tol:
                curr.append(w)
            else:
                cells.append(curr)
                curr = [w]
        cells.append(curr)

        phrases: list[dict[str, Any]] = []
        for c in cells:
            is_cell_rtl = any(w.get("direction") == "rtl" for w in c) or any(
                bool(arabic_pattern.search(w["text"])) for w in c
            )
            c_sorted = sorted(c, key=lambda w: w["x0"], reverse=is_cell_rtl)
            raw_text = " ".join(plain_letters(w["text"]) for w in c_sorted).strip()
            phrases.append({
                "text": raw_text,
                "x0": c[0]["x0"],
                "x1": c[-1]["x1"],
                "direction": "rtl" if is_cell_rtl else "ltr",
            })

        if len(phrases) >= 2:
            candidate_lines.append({"top": l["top"], "phrases": phrases})

    if len(candidate_lines) < min_rows:
        return ""

    # Filter candidate lines to find grid lines with sufficient columns (Multi-Row Grid Requirement)
    grid_lines = [l for l in candidate_lines if len(l["phrases"]) >= min_columns]
    if len(grid_lines) < min_rows:
        return ""

    # Narrative Text Density Filtering: reject multi-column prose articles
    all_grid_phrases = [p for l in grid_lines for p in l["phrases"]]
    if all_grid_phrases:
        avg_words_per_phrase = sum(len(p["text"].split()) for p in all_grid_phrases) / len(all_grid_phrases)
        if avg_words_per_phrase > 6.0:
            return ""

    # Reject numbered/bullet lists where column 0 consists of list markers and descriptions are prose sentences
    if all(re.match(r"^\s*(\d+[\.\)]|[-*•–—])\s*$", l["phrases"][0]["text"]) for l in grid_lines):
        if any(len(p["text"].split()) >= 6 for l in grid_lines for p in l["phrases"]):
            return ""

    # Table-Local Reading Direction: determine is_rtl from grid lines / header line phrases
    header_phrases = grid_lines[0]["phrases"]
    header_alpha = [p for p in header_phrases if re.search(r"[^\W\d_]", p["text"])]
    header_arabic = sum(1 for p in header_alpha if bool(arabic_pattern.search(p["text"])))

    is_rtl = False
    if header_alpha and header_arabic > 0:
        rightmost_header_phrase = max(header_phrases, key=lambda p: p["x0"])
        if header_arabic >= len(header_alpha) / 2 or bool(arabic_pattern.search(rightmost_header_phrase["text"])):
            is_rtl = True
    elif any(p.get("direction") == "rtl" for p in header_phrases):
        is_rtl = True
    else:
        rightmost_phrases = [max(l["phrases"], key=lambda p: p["x0"]) for l in grid_lines]
        arabic_rightmost = sum(1 for p in rightmost_phrases if arabic_pattern.search(p["text"]))
        if arabic_rightmost > len(grid_lines) / 2:
            is_rtl = True

    # Adaptive inter-column gap tolerance
    all_gaps: list[float] = []
    for l in grid_lines:
        ps = l["phrases"]
        for i in range(len(ps) - 1):
            gap = ps[i + 1]["x0"] - ps[i]["x1"]
            if gap > 0:
                all_gaps.append(gap)
    min_inter_col_gap = min(all_gaps) if all_gaps else (avg_char_w * 2.5)
    col_gap_tol = max(3.0, min(8.0, min_inter_col_gap * 0.4))

    # Cluster column bounding intervals
    all_spans = sorted([[p["x0"], p["x1"]] for l in grid_lines for p in l["phrases"]], key=lambda x: x[0])
    cols: list[list[float]] = []
    for s in all_spans:
        if not cols:
            cols.append(s[:])
        else:
            if s[0] <= cols[-1][1] + col_gap_tol:
                cols[-1][1] = max(cols[-1][1], s[1])
            else:
                cols.append(s[:])

    if len(cols) < min_columns:
        return ""

    # For RTL Arabic documents, sort columns Right-to-Left (reversed x-clustering)
    if is_rtl:
        cols.sort(key=lambda c: c[0], reverse=True)

    # Project each candidate line into the discovered column grid with distance & overlap bounds
    table_rows: list[str] = []
    min_populated = min(min_columns, len(cols) - 1)
    max_snap_dist = col_gap_tol * 1.5

    for l in candidate_lines:
        row = [""] * len(cols)
        for p in l["phrases"]:
            best_col = -1
            best_score = -1e9
            for c_idx, c in enumerate(cols):
                c_min, c_max = min(c[0], c[1]), max(c[0], c[1])
                overlap = max(0.0, min(p["x1"], c_max) - max(p["x0"], c_min))
                if overlap > 0:
                    score = overlap
                else:
                    dist = max(0.0, c_min - p["x1"], p["x0"] - c_max)
                    if dist <= max_snap_dist:
                        score = -dist
                    else:
                        continue
                if score > best_score:
                    best_score = score
                    best_col = c_idx
            if best_col >= 0:
                if row[best_col]:
                    row[best_col] += " " + p["text"]
                else:
                    row[best_col] = p["text"]

        if sum(1 for cell in row if cell.strip()) >= min_populated:
            table_rows.append(" | ".join(row))

    return "\n".join(table_rows) if len(table_rows) >= min_rows else ""

