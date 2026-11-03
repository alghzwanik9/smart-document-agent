"""One summary of the documents, the extracted fields and the corrections."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from api.v1.documents import get_session
from core.schemas import AnalyticsSummary
from core.security import require_api_key
from database.models import STATUSES, Document, ExtractedField, FeedbackLoop

router = APIRouter(dependencies=[Depends(require_api_key)])


def _counts(session: Session, column) -> dict[str, int]:
    return {key: count for key, count in session.execute(select(column, func.count()).group_by(column)).all()}


@router.get("/analytics/summary", response_model=AnalyticsSummary)
def summary(session: Session = Depends(get_session)) -> AnalyticsSummary:
    by_status = _counts(session, Document.status)
    by_type = _counts(session, Document.file_type)
    return AnalyticsSummary(
        documents_total=sum(by_type.values()),
        documents_by_type=by_type,
        documents_by_status={status: by_status.get(status, 0) for status in STATUSES},
        fields_total=session.scalar(select(func.count()).select_from(ExtractedField)) or 0,
        average_confidence=session.scalar(select(func.avg(ExtractedField.confidence))),
        corrections_total=session.scalar(select(func.count()).select_from(FeedbackLoop)) or 0,
        corrected_by_field=_counts(session, FeedbackLoop.field_name),
    )
