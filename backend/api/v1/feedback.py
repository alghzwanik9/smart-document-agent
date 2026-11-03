"""The log of the user's corrections, newest first."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from api.v1.documents import MAX_PAGE_SIZE, get_session
from core.schemas import CorrectionOut, CorrectionPage
from core.security import require_api_key
from database.models import FeedbackLoop

router = APIRouter(dependencies=[Depends(require_api_key)])


@router.get("/feedback/corrections", response_model=CorrectionPage)
def list_corrections(page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=MAX_PAGE_SIZE),
                     session: Session = Depends(get_session)) -> CorrectionPage:
    total = session.scalar(select(func.count()).select_from(FeedbackLoop)) or 0
    rows = session.scalars(
        select(FeedbackLoop).order_by(FeedbackLoop.id.desc()).offset((page - 1) * page_size).limit(page_size)
    ).all()
    return CorrectionPage(items=[CorrectionOut.model_validate(r) for r in rows], total=total,
                          page=page, page_size=page_size)
