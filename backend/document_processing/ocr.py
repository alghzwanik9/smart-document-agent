"""OCR for scanned PDF pages through Tesseract."""
from __future__ import annotations

import io

from document_processing import OcrPage, ProcessingError


class OcrUnavailable(ProcessingError):
    pass


def make_ocr(languages: str) -> OcrPage:
    """A function that reads one page image. Tesseract is looked up on first use, not at startup,
    so the service runs (and reads digital files) on a machine without it."""

    def ocr_page(png: bytes) -> str:
        import pytesseract
        from PIL import Image

        try:
            return pytesseract.image_to_string(Image.open(io.BytesIO(png)), lang=languages).strip()
        except pytesseract.TesseractNotFoundError as exc:
            raise OcrUnavailable("Tesseract is not installed, so scanned pages cannot be read") from exc
        except pytesseract.TesseractError as exc:
            raise OcrUnavailable(f"Tesseract could not read the page (language pack {languages} installed?)") from exc

    return ocr_page
