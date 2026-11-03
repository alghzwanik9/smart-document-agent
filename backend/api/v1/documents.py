"""Document endpoints: upload (processed in the background), list, details, extracted fields, correct a field
(each correction is also recorded as a learning example), export with the corrections, delete."""
from __future__ import annotations

import logging
import re
import uuid
from pathlib import Path
from typing import Iterator
from urllib.parse import quote

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, Response, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from core.schemas import (DocumentOut, DocumentPage, ExtractedFieldOut, FieldCorrection, UploadAccepted,
                          format_amount, parse_amount)
from core.security import UploadRejected, require_api_key, safe_filename, validate_upload
from database.models import Document, ExtractedField
from document_processing import ProcessingError, parse_document
from document_processing.exporter import ExportError, export_document
from document_processing.llm_extractor import NUMERIC_FIELDS

log = logging.getLogger("api.documents")

MAX_PAGE_SIZE = 100
router = APIRouter(dependencies=[Depends(require_api_key)])


def get_session(request: Request) -> Iterator[Session]:
    session = request.app.state.db.session()
    try:
        yield session
    finally:
        session.close()


def _stored_file(settings, stored_path: str) -> Path | None:
    """The original file inside the storage folder, or None if the name would lead anywhere else."""
    root = settings.storage_dir.resolve()
    path = (root / stored_path).resolve()
    return path if path.parent == root else None


def _get_or_404(session: Session, document_id: int) -> Document:
    document = session.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return document


# ---------------------------------------------------------------------- background processing
def process_document(state, document_id: int) -> None:
    """Reads the stored file, extracts the fields and records the outcome. Never raises: a failure is a status."""
    session = state.db.session()
    try:
        document = session.get(Document, document_id)
        if document is None:
            return
        document.status = "processing"
        session.commit()
        try:
            path = _stored_file(state.settings, document.stored_path)
            if path is None or not path.is_file():
                raise ProcessingError("The stored file is missing")
            parsed = parse_document(path, document.file_type, state.ocr_page)
            drafts = state.extractor.extract(parsed.text, state.learning.examples_for, state.layouts)
            if not drafts:
                raise ProcessingError("No payroll record was found in the document")
            session.add_all(
                ExtractedField(
                    document_id=document.id, record_index=draft.record_index, field_name=draft.field_name,
                    original_value=draft.value, confidence=draft.confidence,
                    extraction_model_version=state.settings.llm_model or None,
                )
                for draft in drafts
            )
            document.status, document.error_message = "completed", None
        except ProcessingError as exc:
            session.rollback()
            _mark_failed(session, document_id, str(exc))
            return
        except Exception as exc:   # the message carries the type only: it must never carry document text
            log.error("Processing document %s failed: %s", document_id, type(exc).__name__)
            session.rollback()
            _mark_failed(session, document_id, f"Processing failed unexpectedly ({type(exc).__name__})")
            return
        session.commit()
    finally:
        session.close()


def _mark_failed(session: Session, document_id: int, message: str) -> None:
    document = session.get(Document, document_id)
    if document is not None:    # it may have been deleted while it was being processed
        document.status, document.error_message = "failed", message
        session.commit()


# ---------------------------------------------------------------------- endpoints
@router.post("/documents/upload", status_code=202, response_model=UploadAccepted)
def upload_document(request: Request, background: BackgroundTasks, file: UploadFile,
                    session: Session = Depends(get_session)) -> UploadAccepted:
    settings = request.app.state.settings
    data = file.file.read(settings.max_upload_bytes + 1)
    try:
        file_type, extension = validate_upload(file.filename or "", data, settings.max_upload_bytes)
    except UploadRejected as rejected:
        raise HTTPException(status_code=rejected.status_code, detail=rejected.message) from rejected

    stored_name = f"{uuid.uuid4().hex}{extension}"
    stored = settings.storage_dir / stored_name
    stored.write_bytes(data)
    try:
        document = Document(filename=safe_filename(file.filename), file_type=file_type,
                            file_size=len(data), stored_path=stored_name, status="pending")
        session.add(document)
        session.commit()
    except Exception:
        stored.unlink(missing_ok=True)
        raise
    background.add_task(process_document, request.app.state, document.id)
    return UploadAccepted(document_id=document.id, status=document.status)


@router.get("/documents", response_model=DocumentPage)
def list_documents(page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=MAX_PAGE_SIZE),
                   session: Session = Depends(get_session)) -> DocumentPage:
    total = session.scalar(select(func.count()).select_from(Document)) or 0
    rows = session.scalars(
        select(Document).order_by(Document.id.desc()).offset((page - 1) * page_size).limit(page_size)
    ).all()
    return DocumentPage(items=[DocumentOut.model_validate(r) for r in rows], total=total,
                        page=page, page_size=page_size)


@router.get("/documents/{document_id}", response_model=DocumentOut)
def get_document(document_id: int, session: Session = Depends(get_session)) -> Document:
    return _get_or_404(session, document_id)


@router.get("/documents/{document_id}/extracted_fields", response_model=list[ExtractedFieldOut])
def get_extracted_fields(document_id: int, session: Session = Depends(get_session)) -> list[ExtractedField]:
    return _get_or_404(session, document_id).fields


@router.put("/documents/{document_id}/fields/{field_id}", response_model=ExtractedFieldOut)
def correct_field(document_id: int, field_id: int, body: FieldCorrection, request: Request,
                  session: Session = Depends(get_session)) -> ExtractedField:
    field = session.get(ExtractedField, field_id)
    if field is None or field.document_id != document_id:
        raise HTTPException(status_code=404, detail="Field not found")
    value = body.corrected_value.strip()
    if field.field_name in NUMERIC_FIELDS and value:
        try:
            amount = parse_amount(value)
        except ValueError:
            amount = None
        if amount is None:
            raise HTTPException(status_code=422, detail=f"{field.field_name} must be a number")
        value = format_amount(amount)
    learning = request.app.state.learning
    if value == (field.original_value or ""):       # the original put back: nothing is corrected any more
        field.corrected_value, field.is_corrected = None, False
        learning.forget_field(session, field.id)
    else:
        field.corrected_value, field.is_corrected = value, True
        learning.record(session, field)
    session.commit()
    return field


@router.get("/documents/{document_id}/export")
def export_corrected(document_id: int, request: Request, format: str | None = Query(None),
                     session: Session = Depends(get_session)) -> Response:
    document = _get_or_404(session, document_id)
    if document.status != "completed":
        raise HTTPException(status_code=409, detail="The document has not been processed successfully")
    path = _stored_file(request.app.state.settings, document.stored_path)
    if path is None or not path.is_file():
        raise HTTPException(status_code=404, detail="The original file is missing")
    try:
        result = export_document(path, document.file_type, document.fields, format)
    except ExportError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    headers = {"Content-Disposition": _attachment(f"{Path(document.filename).stem}_corrected.{result.extension}")}
    if result.unplaced:
        headers["X-Export-Unplaced"] = ",".join(str(field_id) for field_id in result.unplaced)
    return Response(content=result.data, media_type=result.media_type, headers=headers)


def _attachment(filename: str) -> str:
    """A Content-Disposition value; the UTF-8 form carries Arabic names, the ASCII one is for old clients."""
    ascii_name = re.sub(r'[^A-Za-z0-9._-]', "_", filename)
    return f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(filename)}"


@router.delete("/documents/{document_id}", status_code=204)
def delete_document(document_id: int, request: Request, session: Session = Depends(get_session)) -> None:
    document = _get_or_404(session, document_id)
    path = _stored_file(request.app.state.settings, document.stored_path)
    request.app.state.learning.forget_document(session, document.id)
    session.delete(document)
    session.commit()
    if path is not None:
        path.unlink(missing_ok=True)
