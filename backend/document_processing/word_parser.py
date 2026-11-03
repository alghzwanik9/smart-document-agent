"""Word to text: paragraphs and tables in the order they appear in the document."""
from __future__ import annotations

from pathlib import Path

import docx
from docx.table import Table
from docx.text.paragraph import Paragraph

from document_processing import ParsedDocument, ProcessingError


def parse_word(path: Path) -> ParsedDocument:
    try:
        document = docx.Document(str(path))
        lines = []
        for child in document.element.body.iterchildren():
            if child.tag.endswith("}p"):
                text = Paragraph(child, document).text.strip()
                if text:
                    lines.append(text)
            elif child.tag.endswith("}tbl"):
                for row in Table(child, document).rows:
                    line = " | ".join(cell.text.strip() for cell in row.cells)
                    if line.strip(" |"):
                        lines.append(line)
    except Exception as exc:
        raise ProcessingError(f"The Word file could not be read ({type(exc).__name__})") from exc
    return ParsedDocument(text="\n".join(lines))
