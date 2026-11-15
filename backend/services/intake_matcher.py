"""Intake and Matching Engine for Yahya Intelligent Office System (Taif University HR).
Provides:
1. Statutory deadline business days calculation (Sunday-Thursday workweek in Saudi Arabia).
2. Deterministic 3-way routing: NO_MATCH, SIMILAR_FOUND, SAME_PERSON_NEW_TOPIC.
3. RapidFuzz similarity matching on names, topics, references, and monetary amounts.
4. Formatting utilities for PER-xxxx, <DOMAIN>-<YEAR>-<SEQ>, and EV-xxx IDs.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import re
from typing import Sequence

from rapidfuzz import fuzz
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from core.schemas import (
    IntakeEvaluationRequest,
    IntakeEvaluationResult,
    PersonOut,
    SimilarCaseSummary,
)
from database.models import (
    PersonRecord,
    CaseRecord,
    CaseEvent,
    CASE_STATUSES,
    CASE_DOMAINS,
    RELATION_TYPES,
)


def validate_case_status(status: str) -> bool:
    """Validate if status is one of the allowed domain statuses: NEW, ANL, WAI, RDY, CLS, HLD."""
    return status in CASE_STATUSES


def validate_relation_type(relation_type: str) -> bool:
    """Validate if relation type is one of the allowed domain relation types."""
    return relation_type in RELATION_TYPES


def calculate_statutory_priority(
    deadline: datetime | None,
    now: datetime | None = None,
) -> tuple[str, int | None]:
    """Calculate priority and remaining business days under Saudi public sector calendar.
    Workweek: Sunday (6) through Thursday (3). Weekend: Friday (4) and Saturday (5).
    If statutory deadline <= 5 business days: priority P1.
    If 6-15 business days: priority P2.
    If > 15 business days or no deadline: priority P3 (or P2 default).
    """
    if deadline is None:
        return "P2", None

    if now is None:
        now = datetime.now(timezone.utc)

    # Ensure both are comparable dates
    curr_date = now.date() if isinstance(now, datetime) else now
    target_date = deadline.date() if isinstance(deadline, datetime) else deadline

    if target_date <= curr_date:
        return "P1", 0

    business_days = 0
    day_cursor = curr_date + timedelta(days=1)
    while day_cursor <= target_date:
        # In Python weekday(): Monday is 0, Sunday is 6.
        # Saudi public sector work days: Sunday (6), Monday (0), Tuesday (1), Wednesday (2), Thursday (3).
        # Weekend days: Friday (4), Saturday (5).
        if day_cursor.weekday() not in (4, 5):
            business_days += 1
        day_cursor += timedelta(days=1)

    if business_days <= 5:
        return "P1", business_days
    elif business_days <= 15:
        return "P2", business_days
    else:
        return "P3", business_days


def generate_person_id(session: Session) -> str:
    """Generate next sequential person ID: PER-0001, PER-0002..."""
    per_ids = session.scalars(select(PersonRecord.per_id)).all()
    max_seq = 0
    for pid in per_ids:
        m = re.match(r"^PER-(\d+)$", pid)
        if m:
            max_seq = max(max_seq, int(m.group(1)))
    return f"PER-{max_seq + 1:04d}"


def generate_case_id(session: Session, domain: str = "PAY", year: int | None = None) -> str:
    """Generate next sequential case ID: <DOMAIN>-<YEAR>-<SEQ:04d> (e.g. PAY-2026-0001)."""
    if domain not in CASE_DOMAINS:
        domain = "PAY"
    if year is None:
        year = datetime.now(timezone.utc).year

    prefix = f"{domain}-{year}-"
    case_ids = session.scalars(
        select(CaseRecord.case_id).where(CaseRecord.case_id.like(f"{prefix}%"))
    ).all()
    max_seq = 0
    for cid in case_ids:
        m = re.match(rf"^{re.escape(prefix)}(\d+)$", cid)
        if m:
            max_seq = max(max_seq, int(m.group(1)))
    return f"{prefix}{max_seq + 1:04d}"


def generate_event_id(session: Session, case_id: str) -> str:
    """Generate next sequential event ID for a case: EV-001, EV-002..."""
    count = session.scalar(
        select(func.count()).select_from(CaseEvent).where(CaseEvent.case_id == case_id)
    ) or 0
    return f"EV-{count + 1:03d}"


def evaluate_intake(session: Session, request: IntakeEvaluationRequest) -> IntakeEvaluationResult:
    """Deterministic 3-way intake evaluation:
    1. NO_MATCH: Fresh intake, safe to create new PER-xxxx and CASE-xxxx with EV-001.
    2. SIMILAR_FOUND: Existing matching topic, reference, or claim - requires human review.
    3. SAME_PERSON_NEW_TOPIC: Verified existing person with distinct new lawsuit or topic.
    """
    priority, remaining_days = calculate_statutory_priority(request.statutory_deadline)

    # 1. Match Person
    matched_person: PersonRecord | None = None
    req_emp_no = (request.employee_number or "").strip()
    req_nid = (request.national_id or "").strip()
    req_nid_hash = hashlib.sha256(req_nid.encode("utf-8")).hexdigest() if req_nid else None

    if req_emp_no:
        matched_person = session.scalar(
            select(PersonRecord).where(PersonRecord.employee_number == req_emp_no)
        )

    if matched_person is None and req_nid_hash:
        matched_person = session.scalar(
            select(PersonRecord).where(PersonRecord.national_id_hash == req_nid_hash)
        )

    if matched_person is None and request.full_name:
        all_persons = session.scalars(select(PersonRecord)).all()
        best_score = 0.0
        best_candidate: PersonRecord | None = None
        for p in all_persons:
            score = fuzz.token_set_ratio(request.full_name, p.full_name)
            if score > best_score:
                best_score = score
                best_candidate = p
        if best_score >= 85.0 and best_candidate is not None:
            matched_person = best_candidate

    similar_cases: list[SimilarCaseSummary] = []
    clean_ref = (request.reference_number or "").strip()

    # 2. Evaluate Cases
    if matched_person is not None:
        person_cases = session.scalars(
            select(CaseRecord).where(CaseRecord.per_id == matched_person.per_id)
        ).all()

        for case in person_cases:
            matched_fields: list[str] = []
            differences: list[str] = []

            # Check reference number
            if clean_ref and case.reference_number and clean_ref == case.reference_number:
                matched_fields.append("reference_number")

            # Check subject similarity
            subject_score = fuzz.token_set_ratio(request.subject, case.subject)
            if subject_score >= 85.0:
                matched_fields.append("subject")

            # Check monetary amount with topic context
            if request.monetary_amount is not None and case.monetary_amount is not None:
                if abs(request.monetary_amount - case.monetary_amount) < 0.01:
                    if subject_score >= 70.0:
                        matched_fields.append("monetary_amount")

            if matched_fields:
                last_event_desc = case.events[-1].description if case.events else None
                differences.append(f"حالة المعاملة الحالية: {case.status}")
                if case.statutory_deadline != request.statutory_deadline:
                    differences.append("اختلاف في الموعد النظامي")
                similar_cases.append(
                    SimilarCaseSummary(
                        case_id=case.case_id,
                        subject=case.subject,
                        per_id=case.per_id,
                        status=case.status,
                        last_event=last_event_desc,
                        matched_fields=matched_fields,
                        differences=differences,
                    )
                )

        person_out = PersonOut.model_validate(matched_person)
        if similar_cases:
            return IntakeEvaluationResult(
                decision="SIMILAR_FOUND",
                suggested_priority=priority,
                business_days_remaining=remaining_days,
                person=person_out,
                similar_cases=similar_cases,
                reason="تم العثور على معاملات سابقة متطابقة أو متقاربة في الموضوع أو رقم المرجع لنفس الموظف",
            )
        else:
            return IntakeEvaluationResult(
                decision="SAME_PERSON_NEW_TOPIC",
                suggested_priority=priority,
                business_days_remaining=remaining_days,
                person=person_out,
                similar_cases=[],
                reason="الموظف مسجل مسبقاً في النظام ولكن الموضوع يمثل مطالبة أو دعوى جديدة مستقلة",
            )

    # 3. If Person NOT found: check cross-person reference numbers
    if clean_ref:
        cross_cases = session.scalars(
            select(CaseRecord).where(CaseRecord.reference_number == clean_ref)
        ).all()
        if cross_cases:
            for c in cross_cases:
                last_event_desc = c.events[-1].description if c.events else None
                similar_cases.append(
                    SimilarCaseSummary(
                        case_id=c.case_id,
                        subject=c.subject,
                        per_id=c.per_id,
                        status=c.status,
                        last_event=last_event_desc,
                        matched_fields=["reference_number"],
                        differences=[f"مرتبطة بملف الموظف {c.per_id}"],
                    )
                )
            return IntakeEvaluationResult(
                decision="SIMILAR_FOUND",
                suggested_priority=priority,
                business_days_remaining=remaining_days,
                person=None,
                similar_cases=similar_cases,
                reason="رقم المرجع أو خطاب القيد مسجل مسبقاً في النظام لمعاملة أخرى",
            )

    # Completely new intake
    return IntakeEvaluationResult(
        decision="NO_MATCH",
        suggested_priority=priority,
        business_days_remaining=remaining_days,
        person=None,
        similar_cases=[],
        reason="معاملة جديدة كلياً لا تطابق أي سجل سابق، آمنة للقيد الفوري",
    )
