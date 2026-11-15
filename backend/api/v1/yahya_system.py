"""Yahya Intelligent Office System API Router (Taif University HR).
Protected by X-API-Key authentication.
Provides:
- POST /yahya/intake/evaluate (deterministic intake routing)
- POST /yahya/cases (case registration with initial EV-001)
- GET /yahya/cases/{case_id} (case details with events and relations)
- POST /yahya/cases/{case_id}/events (append-only event addition)
- POST /yahya/cases/{case_id}/relations (case relationships)
- GET /yahya/search (hierarchical tree search PER -> CASE -> EV)
- GET /yahya/sync-export (append-only sync summary in JSON or Markdown)
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from typing import Iterator, Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload

from core.schemas import (
    CaseCreateRequest,
    CaseDetailOut,
    CaseEventCreateRequest,
    CaseEventOut,
    CaseOut,
    CaseRelationCreateRequest,
    CaseRelationOut,
    IntakeEvaluationRequest,
    IntakeEvaluationResult,
    PersonOut,
    YahyaHierarchyOut,
)
from core.security import require_api_key
from database.models import (
    CaseEvent,
    CaseRecord,
    CaseRelation,
    PersonRecord,
)
from services.intake_matcher import (
    evaluate_intake,
    generate_case_id,
    generate_event_id,
    generate_person_id,
    validate_case_status,
    validate_relation_type,
)

router = APIRouter(dependencies=[Depends(require_api_key)])


def get_session(request: Request) -> Iterator[Session]:
    session = request.app.state.db.session()
    try:
        yield session
    finally:
        session.close()


@router.post("/intake/evaluate", response_model=IntakeEvaluationResult)
def evaluate_intake_endpoint(
    body: IntakeEvaluationRequest,
    session: Session = Depends(get_session),
) -> IntakeEvaluationResult:
    """Evaluate intake data against existing records and return deterministic routing."""
    return evaluate_intake(session, body)


@router.post("/cases", status_code=201, response_model=CaseOut)
def create_case_endpoint(
    body: CaseCreateRequest,
    session: Session = Depends(get_session),
) -> CaseRecord:
    """Register a new case under an existing or new person record, with initial EV-001 event."""
    per_id = body.per_id
    if per_id:
        person = session.get(PersonRecord, per_id)
        if person is None:
            raise HTTPException(status_code=404, detail="Person record not found")
    else:
        # Check if person already exists by employee_number, national_id, or name
        eval_res = evaluate_intake(
            session,
            IntakeEvaluationRequest(
                employee_number=body.employee_number,
                full_name=body.full_name or "موظف غير مسمى",
                national_id=body.national_id,
                subject=body.subject,
                reference_number=body.reference_number,
                monetary_amount=body.monetary_amount,
                domain=body.domain,
            ),
        )
        if eval_res.person is not None:
            per_id = eval_res.person.per_id
        else:
            # Create new person
            per_id = generate_person_id(session)
            nid_hash = (
                hashlib.sha256(body.national_id.strip().encode("utf-8")).hexdigest()
                if body.national_id and body.national_id.strip()
                else None
            )
            person = PersonRecord(
                per_id=per_id,
                employee_number=body.employee_number.strip() if body.employee_number else None,
                full_name=(body.full_name or "موظف جديد").strip(),
                national_id_hash=nid_hash,
            )
            session.add(person)
            session.flush()

    case_id = generate_case_id(session, domain=body.domain)
    case = CaseRecord(
        case_id=case_id,
        per_id=per_id,
        subject=body.subject.strip(),
        domain=body.domain,
        status="NEW",
        priority=body.priority,
        statutory_deadline=body.statutory_deadline,
        reference_number=body.reference_number.strip() if body.reference_number else None,
        monetary_amount=body.monetary_amount,
        document_id=body.document_id,
    )
    session.add(case)
    session.flush()

    # Create initial EV-001 event
    initial_desc = body.initial_event_description or "تسجيل وقيد المعاملة في نظام يحيى الذكي"
    initial_event = CaseEvent(
        case_id=case_id,
        ev_id="EV-001",
        event_type="INTAKE",
        description=initial_desc,
        new_value="NEW",
        reason="قيد المعاملة الواردة",
    )
    session.add(initial_event)
    session.commit()
    session.refresh(case)
    return case


@router.get("/cases/{case_id}", response_model=CaseDetailOut)
def get_case_detail(
    case_id: str,
    session: Session = Depends(get_session),
) -> CaseDetailOut:
    """Retrieve full case details, history of events, and relations."""
    case = session.scalar(
        select(CaseRecord)
        .options(
            joinedload(CaseRecord.person),
            joinedload(CaseRecord.events),
            joinedload(CaseRecord.outgoing_relations),
            joinedload(CaseRecord.incoming_relations),
        )
        .where(CaseRecord.case_id == case_id)
    )
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")
    return CaseDetailOut.model_validate(case)


@router.post("/cases/{case_id}/events", status_code=201, response_model=CaseEventOut)
def add_case_event(
    case_id: str,
    body: CaseEventCreateRequest,
    session: Session = Depends(get_session),
) -> CaseEvent:
    """Append a new sequential event (EV-xxx) to an existing case."""
    case = session.get(CaseRecord, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")

    ev_id = generate_event_id(session, case_id)
    event = CaseEvent(
        case_id=case_id,
        ev_id=ev_id,
        event_type=body.event_type,
        description=body.description,
        old_value=body.old_value,
        new_value=body.new_value,
        reason=body.reason,
    )
    session.add(event)
    session.commit()
    session.refresh(event)
    return event


@router.post("/cases/{case_id}/relations", status_code=201, response_model=CaseRelationOut)
def add_case_relation(
    case_id: str,
    body: CaseRelationCreateRequest,
    session: Session = Depends(get_session),
) -> CaseRelation:
    """Create a domain relation between two cases."""
    if not validate_relation_type(body.relation_type):
        raise HTTPException(
            status_code=422,
            detail=f"Invalid relation_type. Allowed: {sorted(list(validate_relation_type.__globals__['RELATION_TYPES']))}",
        )

    source = session.get(CaseRecord, case_id)
    target = session.get(CaseRecord, body.target_case_id)
    if source is None or target is None:
        raise HTTPException(status_code=404, detail="Source or target case not found")

    relation = CaseRelation(
        source_case_id=case_id,
        target_case_id=body.target_case_id,
        relation_type=body.relation_type,
    )
    session.add(relation)
    session.commit()
    session.refresh(relation)
    return relation


@router.get("/search", response_model=list[YahyaHierarchyOut])
def search_hierarchy(
    q: str = Query(..., min_length=1),
    session: Session = Depends(get_session),
) -> list[YahyaHierarchyOut]:
    """Search by employee name, employee number, PER-xxxx, case_id, or reference number,
    and return the full hierarchical PER -> CASE -> EV tree.
    """
    term = f"%{q.strip()}%"

    # Match persons directly
    matched_person_ids = set(
        session.scalars(
            select(PersonRecord.per_id).where(
                or_(
                    PersonRecord.full_name.ilike(term),
                    PersonRecord.employee_number.ilike(term),
                    PersonRecord.per_id.ilike(term),
                )
            )
        ).all()
    )

    # Match cases and get their person IDs
    case_person_ids = session.scalars(
        select(CaseRecord.per_id).where(
            or_(
                CaseRecord.case_id.ilike(term),
                CaseRecord.subject.ilike(term),
                CaseRecord.reference_number.ilike(term),
            )
        )
    ).all()
    matched_person_ids.update(case_person_ids)

    if not matched_person_ids:
        return []

    persons = session.scalars(
        select(PersonRecord)
        .options(
            joinedload(PersonRecord.cases).joinedload(CaseRecord.events),
            joinedload(PersonRecord.cases).joinedload(CaseRecord.outgoing_relations),
            joinedload(PersonRecord.cases).joinedload(CaseRecord.incoming_relations),
        )
        .where(PersonRecord.per_id.in_(matched_person_ids))
    ).unique().all()

    result = []
    for p in persons:
        cases_out = [CaseDetailOut.model_validate(c) for c in p.cases]
        result.append(
            YahyaHierarchyOut(
                per_id=p.per_id,
                employee_number=p.employee_number,
                full_name=p.full_name,
                created_at=p.created_at,
                cases=cases_out,
            )
        )
    return result


@router.get("/sync-export")
def sync_export(
    format: Literal["json", "markdown"] = Query("json"),
    session: Session = Depends(get_session),
) -> Response:
    """Export the entire append-only registry and audit trail in JSON or Markdown format."""
    persons = session.scalars(
        select(PersonRecord)
        .options(
            joinedload(PersonRecord.cases).joinedload(CaseRecord.events),
            joinedload(PersonRecord.cases).joinedload(CaseRecord.outgoing_relations),
        )
    ).unique().all()

    all_cases = session.scalars(
        select(CaseRecord).options(joinedload(CaseRecord.events))
    ).unique().all()

    exported_at = datetime.now(timezone.utc).isoformat()

    if format == "json":
        data = {
            "exported_at": exported_at,
            "system": "Yahya Intelligent Office System — Taif University HR",
            "persons_count": len(persons),
            "cases_count": len(all_cases),
            "persons": [
                {
                    "per_id": p.per_id,
                    "employee_number": p.employee_number,
                    "full_name": p.full_name,
                    "created_at": p.created_at.isoformat(),
                    "cases": [
                        {
                            "case_id": c.case_id,
                            "subject": c.subject,
                            "domain": c.domain,
                            "status": c.status,
                            "priority": c.priority,
                            "statutory_deadline": c.statutory_deadline.isoformat() if c.statutory_deadline else None,
                            "reference_number": c.reference_number,
                            "monetary_amount": c.monetary_amount,
                            "events": [
                                {
                                    "ev_id": e.ev_id,
                                    "event_type": e.event_type,
                                    "description": e.description,
                                    "old_value": e.old_value,
                                    "new_value": e.new_value,
                                    "reason": e.reason,
                                    "created_at": e.created_at.isoformat(),
                                }
                                for e in c.events
                            ],
                        }
                        for c in p.cases
                    ],
                }
                for p in persons
            ],
            "cases": [
                {
                    "case_id": c.case_id,
                    "per_id": c.per_id,
                    "subject": c.subject,
                    "status": c.status,
                    "priority": c.priority,
                    "events_count": len(c.events),
                }
                for c in all_cases
            ],
        }
        return Response(content=__import__("json").dumps(data, ensure_ascii=False, indent=2), media_type="application/json")

    # Format Markdown
    lines = [
        "# سجل نظام يحيى الذكي للإدارة — جامعة الطائف",
        f"**تاريخ التصدير**: {exported_at}",
        f"**إجمالي ملفات الموظفين (PER)**: {len(persons)}",
        f"**إجمالي المعاملات المقيدة (CASE)**: {len(all_cases)}",
        "",
        "---",
        "",
    ]
    for p in persons:
        lines.append(f"## ملف الموظف: {p.full_name} (`{p.per_id}`)")
        lines.append(f"- **الرقم الوظيفي**: {p.employee_number or 'غير مسجل'}")
        lines.append(f"- **تاريخ التسجيل**: {p.created_at.strftime('%Y-%m-%d %H:%M:%S UTC')}")
        lines.append(f"- **عدد المعاملات**: {len(p.cases)}")
        lines.append("")
        for c in p.cases:
            lines.append(f"### معاملة: `{c.case_id}` — {c.subject}")
            lines.append(f"- **النطاق**: {c.domain} | **الحالة**: {c.status} | **الأولوية**: {c.priority}")
            if c.reference_number:
                lines.append(f"- **رقم المرجع**: {c.reference_number}")
            if c.monetary_amount is not None:
                lines.append(f"- **المبلغ المالي**: {c.monetary_amount:,.2f} ريال")
            lines.append("")
            lines.append("#### سجل الأحداث والتدقيق (Append-Only Events):")
            lines.append("| المعرف | النوع | البيان | القيمة السابقة | القيمة الجديدة | السبب | التاريخ |")
            lines.append("|---|---|---|---|---|---|---|")
            for e in c.events:
                old_v = e.old_value or "-"
                new_v = e.new_value or "-"
                reason = e.reason or "-"
                lines.append(
                    f"| `{e.ev_id}` | {e.event_type} | {e.description} | {old_v} | {new_v} | {reason} | {e.created_at.strftime('%Y-%m-%d %H:%M')} |"
                )
            lines.append("")
        lines.append("---")
        lines.append("")

    md_text = "\n".join(lines)
    return Response(content=md_text, media_type="text/markdown; charset=utf-8")
