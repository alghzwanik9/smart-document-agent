"""The single-user access key and the checks every uploaded file passes before it is stored."""
from __future__ import annotations

import hmac
import io
import os
import re
import zipfile

from fastapi import Header, HTTPException, Request

# extension -> (file type stored in `documents.file_type`, member that proves a zip is really that format)
ALLOWED_TYPES = {
    ".pdf": ("PDF", None),
    ".docx": ("DOCX", "word/document.xml"),
    ".xlsx": ("XLSX", "xl/workbook.xml"),
    ".csv": ("CSV", None),
}
PDF_SIGNATURE = b"%PDF-"
CSV_SNIFF_BYTES = 4096
MAX_FILENAME_CHARS = 255
_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")


class UploadRejected(Exception):
    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.message = message


def require_api_key(request: Request, x_api_key: str | None = Header(default=None)) -> None:
    """Every endpoint but `/health` asks for `X-API-Key`; with no key configured nothing is let through."""
    expected = request.app.state.settings.api_key
    if not expected:
        raise HTTPException(status_code=503, detail="API_KEY is not configured on the server")
    if x_api_key is None or not hmac.compare_digest(x_api_key.encode(), expected.encode()):
        raise HTTPException(status_code=401, detail="Missing or invalid X-API-Key")


def safe_filename(name: str | None) -> str:
    """The name as the user knows it, for display only; the stored file gets a random name."""
    base = os.path.basename((name or "").replace("\\", "/"))
    return _CONTROL_CHARS.sub("", base).strip()[:MAX_FILENAME_CHARS] or "document"


def validate_upload(filename: str, data: bytes, max_bytes: int) -> tuple[str, str]:
    """Returns (file type, extension) or raises UploadRejected. Extension, signature and size are all checked."""
    extension = os.path.splitext(filename or "")[1].lower()
    if extension not in ALLOWED_TYPES:
        raise UploadRejected(415, f"Unsupported file type {extension or '(none)'}; allowed: pdf, docx, xlsx, csv")
    if not data:
        raise UploadRejected(400, "The file is empty")
    if len(data) > max_bytes:
        raise UploadRejected(413, f"The file is larger than the {max_bytes // (1024 * 1024)} MB limit")

    file_type, marker = ALLOWED_TYPES[extension]
    if extension == ".pdf":
        ok = data.startswith(PDF_SIGNATURE)
    elif marker:
        ok = _is_zip_with(data, marker)
    else:
        ok = b"\x00" not in data[:CSV_SNIFF_BYTES]
    if not ok:
        raise UploadRejected(400, f"The file content does not match its {extension} extension")
    return file_type, extension


def _is_zip_with(data: bytes, member: str) -> bool:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            return member in archive.namelist()
    except zipfile.BadZipFile:
        return False
