"""Unit and integration tests for Yahya Intelligent Office System (Taif University HR Domain Layer).
Tests verify:
1. ID formatting and domain constraints (PER-0001, PAY-2026-0001, EV-001, valid statuses/relations).
2. Intake deterministic routing (NO_MATCH, SIMILAR_FOUND, SAME_PERSON_NEW_TOPIC).
3. P1 priority calculation for statutory deadlines <= 5 business days.
4. Rule 7: Append-only audit trail (CaseEvent) created upon document field corrections.
5. API endpoints (/yahya/intake/evaluate, /yahya/cases, /yahya/search, /yahya/sync-export).
6. Security: API key enforcement across all Yahya endpoints.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import pytest
from sqlalchemy import select

from core.schemas import (
    IntakeEvaluationRequest,
    CaseCreateRequest,
    CaseEventCreateRequest,
    CaseRelationCreateRequest,
)
from database.models import (
    PersonRecord,
    CaseRecord,
    CaseEvent,
    CaseRelation,
    CASE_STATUSES,
    CASE_DOMAINS,
    RELATION_TYPES,
)
from tests.conftest import HEADERS
from tests.test_corrections_api import uploaded, fields_of, correct


# ---------------------------------------------------------------------- 1. ID Formatting & Constraints
def test_id_formatting_and_domain_constraints(client):
    # Verify constants
    assert "NEW" in CASE_STATUSES
    assert "CLS" in CASE_STATUSES
    assert "PAY" in CASE_DOMAINS
    assert "REL-SAME-PERSON" in RELATION_TYPES
    assert "REL-PARENT" in RELATION_TYPES

    # Verify model creation and formatting
    app = client.app
    with app.state.db.session() as session:
        # Create PersonRecord
        nid = "1098765432"
        nid_hash = hashlib.sha256(nid.encode("utf-8")).hexdigest()
        person = PersonRecord(
            per_id="PER-0001",
            employee_number="EMP-1001",
            full_name="د. يحيى بن محمد الغامدي",
            national_id_hash=nid_hash,
        )
        session.add(person)
        session.commit()

        # Create CaseRecord
        case = CaseRecord(
            case_id="PAY-2026-0001",
            per_id="PER-0001",
            subject="صرف بدل سكن استثنائي لأعضاء هيئة التدريس",
            domain="PAY",
            status="NEW",
            priority="P1",
            reference_number="TU-HR-2026-441",
            monetary_amount=18500.0,
        )
        session.add(case)
        session.commit()

        # Create CaseEvent
        event = CaseEvent(
            case_id="PAY-2026-0001",
            ev_id="EV-001",
            event_type="INTAKE",
            description="قيد المعاملة لأول مرة في النظام",
            old_value=None,
            new_value="NEW",
            reason="ورود المعاملة من عمادة الموارد البشرية",
        )
        session.add(event)
        session.commit()

        # Query back and verify relations
        saved_case = session.get(CaseRecord, "PAY-2026-0001")
        assert saved_case is not None
        assert saved_case.per_id == "PER-0001"
        assert saved_case.person.full_name == "د. يحيى بن محمد الغامدي"
        assert len(saved_case.events) == 1
        assert saved_case.events[0].ev_id == "EV-001"
        assert saved_case.events[0].event_type == "INTAKE"

        # Verify national ID hash is NOT the case ID or per_id
        assert saved_case.case_id.startswith("PAY-2026-")
        assert saved_case.person.per_id.startswith("PER-")
        assert saved_case.person.national_id_hash == nid_hash
        assert nid not in saved_case.case_id


def test_invalid_status_and_relation_rejection(client):
    from services.intake_matcher import validate_case_status, validate_relation_type

    assert validate_case_status("NEW") is True
    assert validate_case_status("INVALID_STATUS") is False

    assert validate_relation_type("REL-PARENT") is True
    assert validate_relation_type("INVALID_REL") is False


# ---------------------------------------------------------------------- 2. Intake Deterministic Routing
def test_intake_routing_no_match(client):
    """A new employee and unprecedented subject returns NO_MATCH."""
    from services.intake_matcher import evaluate_intake

    app = client.app
    with app.state.db.session() as session:
        req = IntakeEvaluationRequest(
            employee_number="EMP-9999",
            full_name="سالم عبد الله الشهراني",
            national_id="1011223344",
            subject="طلب بدل تدريب خارجي للموظفين الإداريين",
            reference_number="REF-9999",
            monetary_amount=7500.0,
            domain="PAY",
        )
        result = evaluate_intake(session, req)
        assert result.decision == "NO_MATCH"
        assert result.person is None
        assert len(result.similar_cases) == 0


def test_intake_routing_similar_found_by_reference_and_subject(client):
    """Matching reference number or high topic similarity halts auto-registration (SIMILAR_FOUND)."""
    from services.intake_matcher import evaluate_intake

    app = client.app
    with app.state.db.session() as session:
        # Pre-seed a person and case
        person = PersonRecord(
            per_id="PER-0010",
            employee_number="EMP-2002",
            full_name="فهد عبد العزيز العتيبي",
            national_id_hash=hashlib.sha256("1022334455".encode()).hexdigest(),
        )
        session.add(person)
        case = CaseRecord(
            case_id="PAY-2026-0010",
            per_id="PER-0010",
            subject="تظلم من قرار حسم بدل النقل والمواصلات لعام 1447",
            domain="PAY",
            status="ANL",
            priority="P2",
            reference_number="REF-CASE-8821",
            monetary_amount=1200.0,
        )
        session.add(case)
        session.commit()

        # Case A: Same reference number from same employee
        req1 = IntakeEvaluationRequest(
            employee_number="EMP-2002",
            full_name="فهد عبد العزيز العتيبي",
            subject="متابعة تظلم حسم بدل النقل",
            reference_number="REF-CASE-8821",
            monetary_amount=1200.0,
        )
        res1 = evaluate_intake(session, req1)
        assert res1.decision == "SIMILAR_FOUND"
        assert len(res1.similar_cases) >= 1
        assert res1.similar_cases[0].case_id == "PAY-2026-0010"
        assert "reference_number" in res1.similar_cases[0].matched_fields

        # Case B: High topic similarity (subject fuzzy ratio >= 85)
        req2 = IntakeEvaluationRequest(
            employee_number="EMP-2002",
            full_name="فهد عبد العزيز العتيبي",
            subject="تظلم بخصوص قرار حسم بدل النقل والمواصلات لعام 1447",
            reference_number="REF-NEW-99",
            monetary_amount=1200.0,
        )
        res2 = evaluate_intake(session, req2)
        assert res2.decision == "SIMILAR_FOUND"
        assert "subject" in res2.similar_cases[0].matched_fields


def test_intake_routing_same_person_new_topic(client):
    """Existing employee with completely distinct topic returns SAME_PERSON_NEW_TOPIC."""
    from services.intake_matcher import evaluate_intake

    app = client.app
    with app.state.db.session() as session:
        person = PersonRecord(
            per_id="PER-0020",
            employee_number="EMP-3003",
            full_name="د. نورة بنت خالد المطيري",
            national_id_hash=hashlib.sha256("1033445566".encode()).hexdigest(),
        )
        session.add(person)
        case = CaseRecord(
            case_id="LEG-2026-0020",
            per_id="PER-0020",
            subject="دعوى قضائية أمام المحكمة الإدارية بشأن الترقية الاستثنائية",
            domain="LEG",
            status="ANL",
            priority="P1",
            reference_number="COURT-1447-01",
        )
        session.add(case)
        session.commit()

        # Intake request: Same employee number, but totally different claim (Housing Allowance)
        req = IntakeEvaluationRequest(
            employee_number="EMP-3003",
            full_name="د. نورة بنت خالد المطيري",
            subject="طلب صرف علاوة التميز البحثي السنوية",
            reference_number="RESEARCH-2026-55",
            domain="PAY",
        )
        res = evaluate_intake(session, req)
        assert res.decision == "SAME_PERSON_NEW_TOPIC"
        assert res.person is not None
        assert res.person.per_id == "PER-0020"
        assert len(res.similar_cases) == 0


# ---------------------------------------------------------------------- 3. Statutory Deadline & Priority P1
def test_priority_p1_statutory_deadline_calculation():
    from services.intake_matcher import calculate_statutory_priority

    now = datetime.now(timezone.utc)
    # Deadline in 3 calendar days (within 5 Saudi business days) -> P1
    deadline_urgent = now + timedelta(days=3)
    prio_urgent, days_remaining = calculate_statutory_priority(deadline_urgent, now=now)
    assert prio_urgent == "P1"
    assert days_remaining <= 5

    # Deadline in 25 calendar days -> P2 / P3
    deadline_relaxed = now + timedelta(days=25)
    prio_relaxed, days_relaxed = calculate_statutory_priority(deadline_relaxed, now=now)
    assert prio_relaxed in ("P2", "P3")
    assert days_relaxed > 5


# ---------------------------------------------------------------------- 4. Rule 7 Append-Only Audit Trail
def test_rule_7_append_only_event_on_field_correction(client):
    """Updating an extracted field in a document linked to a CaseRecord automatically appends a CaseEvent."""
    document_id = uploaded(client)
    fields = fields_of(client, document_id)
    net_field = fields["net_salary"]

    app = client.app
    with app.state.db.session() as session:
        # Create person and link document to case
        person = PersonRecord(
            per_id="PER-0050",
            employee_number="EMP-5005",
            full_name="أحمد علي محمد",
        )
        session.add(person)
        case = CaseRecord(
            case_id="PAY-2026-0050",
            per_id="PER-0050",
            subject="تدقيق مسير رواتب منتدبي الجامعة",
            domain="PAY",
            status="ANL",
            document_id=document_id,
        )
        session.add(case)
        # Initial intake event
        session.add(CaseEvent(
            case_id="PAY-2026-0050",
            ev_id="EV-001",
            event_type="INTAKE",
            description="تسجيل المعاملة وربط المستند",
        ))
        session.commit()

    # Perform field correction via PUT /documents/{id}/fields/{field_id} with reason
    resp = client.put(
        f"/documents/{document_id}/fields/{net_field['id']}",
        json={"corrected_value": "6200", "reason": "تصحيح صافي الراتب بعد مراجعة المسير اليدوي"},
        headers=HEADERS,
    )
    assert resp.status_code == 200
    assert resp.json()["corrected_value"] == "6200"

    # Verify that CaseEvent EV-002 was automatically created on PAY-2026-0050
    with app.state.db.session() as session:
        events = session.scalars(
            select(CaseEvent).where(CaseEvent.case_id == "PAY-2026-0050").order_by(CaseEvent.id)
        ).all()
        assert len(events) == 2
        ev2 = events[1]
        assert ev2.ev_id == "EV-002"
        assert ev2.event_type == "FIELD_UPDATE"
        assert ev2.new_value == "6200"
        assert ev2.old_value == "5300"
        assert "تصحيح صافي الراتب" in ev2.reason


# ---------------------------------------------------------------------- 5. API Endpoints
def test_yahya_api_security_enforcement(client):
    """All Yahya endpoints reject requests missing or providing wrong API key."""
    routes = [
        ("POST", "/yahya/intake/evaluate", {}),
        ("POST", "/yahya/cases", {}),
        ("GET", "/yahya/cases/PAY-2026-0001", None),
        ("GET", "/yahya/search?q=test", None),
        ("GET", "/yahya/sync-export", None),
    ]
    for method, path, payload in routes:
        if method == "POST":
            assert client.post(path, json=payload).status_code == 401
            assert client.post(path, json=payload, headers={"X-API-Key": "wrong"}).status_code == 401
        elif method == "GET":
            assert client.get(path).status_code == 401
            assert client.get(path, headers={"X-API-Key": "wrong"}).status_code == 401


def test_yahya_intake_evaluate_and_create_case_api(client):
    """End-to-end API: evaluate intake, commit case, inspect detail."""
    # 1. Evaluate Intake via API
    eval_payload = {
        "employee_number": "EMP-7700",
        "full_name": "سعد بن ناصر الدوسري",
        "national_id": "1099887766",
        "subject": "صرف مكافأة تميز أعضاء هيئة التدريس",
        "domain": "PAY",
        "statutory_deadline": (datetime.now(timezone.utc) + timedelta(days=2)).isoformat(),
        "monetary_amount": 15000.0,
    }
    eval_resp = client.post("/yahya/intake/evaluate", json=eval_payload, headers=HEADERS)
    assert eval_resp.status_code == 200
    eval_data = eval_resp.json()
    assert eval_data["decision"] == "NO_MATCH"
    assert eval_data["suggested_priority"] == "P1"

    # 2. Commit New Case via API
    create_payload = {
        "employee_number": "EMP-7700",
        "full_name": "سعد بن ناصر الدوسري",
        "national_id": "1099887766",
        "subject": "صرف مكافأة تميز أعضاء هيئة التدريس",
        "domain": "PAY",
        "priority": eval_data["suggested_priority"],
        "statutory_deadline": eval_payload["statutory_deadline"],
        "monetary_amount": 15000.0,
    }
    create_resp = client.post("/yahya/cases", json=create_payload, headers=HEADERS)
    assert create_resp.status_code == 201
    case_data = create_resp.json()
    assert case_data["case_id"].startswith("PAY-")
    assert case_data["per_id"].startswith("PER-")
    assert case_data["priority"] == "P1"
    assert case_data["status"] == "NEW"

    case_id = case_data["case_id"]

    # 3. Retrieve Case Detail with Events
    detail_resp = client.get(f"/yahya/cases/{case_id}", headers=HEADERS)
    assert detail_resp.status_code == 200
    detail = detail_resp.json()
    assert detail["case_id"] == case_id
    assert len(detail["events"]) == 1
    assert detail["events"][0]["ev_id"] == "EV-001"
    assert detail["events"][0]["event_type"] == "INTAKE"


def test_yahya_search_hierarchy_and_sync_export_api(client):
    """Test searching hierarchy (PER -> CASE -> EV) and sync export in JSON & Markdown."""
    # Create a person and case first
    create_payload = {
        "employee_number": "EMP-8800",
        "full_name": "مشاعل عبد الله الحارثي",
        "subject": "استحقاق إجازة مرافقة مبتعث خارجية",
        "domain": "LEG",
        "priority": "P2",
    }
    res = client.post("/yahya/cases", json=create_payload, headers=HEADERS)
    assert res.status_code == 201
    case_id = res.json()["case_id"]
    per_id = res.json()["per_id"]

    # Search by employee name
    search_resp = client.get("/yahya/search?q=مشاعل", headers=HEADERS)
    assert search_resp.status_code == 200
    results = search_resp.json()
    assert len(results) >= 1
    person_entry = next((r for r in results if r["per_id"] == per_id), None)
    assert person_entry is not None
    assert person_entry["full_name"] == "مشاعل عبد الله الحارثي"
    assert len(person_entry["cases"]) >= 1
    assert person_entry["cases"][0]["case_id"] == case_id
    assert len(person_entry["cases"][0]["events"]) >= 1

    # Search by case_id
    search_case = client.get(f"/yahya/search?q={case_id}", headers=HEADERS)
    assert search_case.status_code == 200
    assert any(r["per_id"] == per_id for r in search_case.json())

    # Sync Export JSON
    sync_json_resp = client.get("/yahya/sync-export?format=json", headers=HEADERS)
    assert sync_json_resp.status_code == 200
    sync_json = sync_json_resp.json()
    assert "persons" in sync_json
    assert "cases" in sync_json
    assert "exported_at" in sync_json

    # Sync Export Markdown
    sync_md_resp = client.get("/yahya/sync-export?format=markdown", headers=HEADERS)
    assert sync_md_resp.status_code == 200
    assert sync_md_resp.headers["content-type"].startswith("text/markdown")
    md_content = sync_md_resp.text
    assert "# سجل نظام يحيى الذكي للإدارة" in md_content
    assert case_id in md_content
