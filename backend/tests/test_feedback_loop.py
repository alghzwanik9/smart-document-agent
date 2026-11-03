"""Phase 3 criterion: after a field is corrected, uploading a similar document shows the correction used as an
example in the extraction call; the analytics endpoint reports the average confidence and the corrections."""
from __future__ import annotations

from core.config import Settings
from core.schemas import FieldDraft
from feedback_loop.chroma_db import CorrectionStore
from feedback_loop.learning_agent import LearningAgent
from main import create_app
from tests import samples
from tests.conftest import API_KEY, HEADERS, FakeExtractor, TrigramEmbedding
from tests.test_corrections_api import correct, fields_of, uploaded
from tests.test_documents_api import upload

from fastapi.testclient import TestClient


def corrections(client) -> dict:
    return client.get("/feedback/corrections", headers=HEADERS).json()


# ---------------------------------------------------------------------- recording
def test_a_correction_is_logged_with_what_was_wrong_and_what_is_right(client, learning):
    document_id = uploaded(client)
    name = fields_of(client, document_id)["employee_name"]
    correct(client, document_id, name["id"], "Ahmed M. Ali")

    log = corrections(client)
    assert log["total"] == 1
    row = log["items"][0]
    assert (row["field_id"], row["document_id"], row["field_name"]) == (name["id"], document_id, "employee_name")
    assert (row["original_value"], row["corrected_value"]) == ("Ahmed Ali", "Ahmed M. Ali")
    assert row["correction_date"]
    assert learning.store.count() == 1


def test_correcting_a_field_again_replaces_its_example(client, learning):
    document_id = uploaded(client)
    name = fields_of(client, document_id)["employee_name"]
    correct(client, document_id, name["id"], "First fix")
    correct(client, document_id, name["id"], "Second fix")

    log = corrections(client)
    assert log["total"] == 1 and log["items"][0]["corrected_value"] == "Second fix"
    assert learning.store.count() == 1


def test_putting_the_original_back_removes_the_example(client, learning):
    document_id = uploaded(client)
    name = fields_of(client, document_id)["employee_name"]
    correct(client, document_id, name["id"], "Ahmed M. Ali")
    correct(client, document_id, name["id"], "Ahmed Ali")

    assert corrections(client)["total"] == 0
    assert learning.store.count() == 0


def test_deleting_a_document_takes_its_corrections_with_it(client, learning):
    document_id = uploaded(client)
    kept = uploaded(client, "other.xlsx")
    for target in (document_id, kept):
        correct(client, target, fields_of(client, target)["employee_name"]["id"], f"Fix {target}")
    assert learning.store.count() == 2

    assert client.delete(f"/documents/{document_id}", headers=HEADERS).status_code == 204
    log = corrections(client)
    assert [row["document_id"] for row in log["items"]] == [kept]
    assert learning.store.count() == 1


def test_a_failing_index_never_loses_or_blocks_the_correction(settings, extractor):
    class BrokenStore:
        def __getattr__(self, name):
            raise RuntimeError("index down: Ahmed Ali")

    broken = LearningAgent(BrokenStore(), settings)
    with TestClient(create_app(settings, extractor=extractor, learning=broken)) as client:
        document_id = uploaded(client)
        name = fields_of(client, document_id)["employee_name"]
        assert correct(client, document_id, name["id"], "Ahmed M. Ali").status_code == 200

        log = corrections(client)
        assert log["total"] == 1 and log["items"][0]["corrected_value"] == "Ahmed M. Ali"
        again = upload(client, "next.xlsx", samples.xlsx_bytes())     # extraction goes on with no examples
        assert client.get(f"/documents/{again.json()['document_id']}", headers=HEADERS).json()["status"] == "completed"


def test_the_log_is_newest_first_and_paged(client):
    document_id = uploaded(client)
    by_name = fields_of(client, document_id)
    correct(client, document_id, by_name["employee_name"]["id"], "A")
    correct(client, document_id, by_name["net_salary"]["id"], "6000")

    first = client.get("/feedback/corrections", params={"page_size": 1}, headers=HEADERS).json()
    assert first["total"] == 2 and [row["field_name"] for row in first["items"]] == ["net_salary"]
    second = client.get("/feedback/corrections", params={"page": 2, "page_size": 1}, headers=HEADERS).json()
    assert [row["field_name"] for row in second["items"]] == ["employee_name"]


# ---------------------------------------------------------------------- using the corrections (the criterion)
def test_the_criterion_a_similar_document_gets_the_correction_as_an_example(client, extractor):
    first = uploaded(client)
    correct(client, first, fields_of(client, first)["employee_name"]["id"], "Ahmed M. Ali")
    assert extractor.examples[-1] == []                     # the first extraction had nothing to learn from

    uploaded(client, "july.xlsx")                           # the sheet states "Ahmed Ali" again
    offered = extractor.examples[-1]
    assert [(e.field_name, e.original_value, e.corrected_value) for e in offered] == [
        ("employee_name", "Ahmed Ali", "Ahmed M. Ali")]


def test_an_unrelated_document_gets_no_example(client, extractor):
    first = uploaded(client)
    correct(client, first, fields_of(client, first)["employee_name"]["id"], "Ahmed M. Ali")

    other = [("Item", "Qty"), ("zzzzzz qqqqq", "9999999"), ("vvvvv kkkkk", "8888888")]
    uploaded(client, "other.xlsx", lambda: samples.xlsx_bytes(other))
    assert extractor.examples[-1] == []


def test_the_number_of_examples_is_capped(settings, extractor, tmp_path):
    capped = Settings(**{**settings.__dict__, "learning_examples": 2})
    agent = LearningAgent(CorrectionStore(tmp_path / "chroma", TrigramEmbedding()), capped)
    with TestClient(create_app(capped, extractor=extractor, learning=agent)) as client:
        names = ["Ahmed Ali", "Ahmed Alia", "Ahmed Alii", "Ahmed Aly"]
        document_id = uploaded(client)
        for position, name in enumerate(names):
            agent.store.upsert(f"fb-{position}", "employee_name", name, f"{name} fixed")
        uploaded(client, "again.xlsx")
    assert len(extractor.examples[-1]) == 2


def test_examples_are_nearest_first_and_each_appears_once(learning):
    learning.store.upsert("fb-1", "employee_name", "Sara Omar", "Sara Omar Hassan")
    learning.store.upsert("fb-2", "employee_name", "Ahmed Ali", "Ahmed M. Ali")
    text = "Name ID\nAhmed Ali E001\nAhmed Ali again\nSara Omar E002"
    offered = learning.examples_for(text)
    assert sorted(e.corrected_value for e in offered) == ["Ahmed M. Ali", "Sara Omar Hassan"]


def test_a_long_document_is_sampled_for_the_index_but_not_for_verbatim_matches(learning):
    learning.store.upsert("fb-1", "employee_name", "Ahmed Ali", "Ahmed M. Ali")
    calls = []
    real = learning.store.nearest
    learning.store.nearest = lambda texts, per_text: calls.append(len(texts)) or real(texts, per_text)
    long_sheet = "\n".join(f"row {number} | filler" for number in range(5000)) + "\nAhmed Ali | E001"
    offered = learning.examples_for(long_sheet)
    assert calls == [300]
    assert [e.corrected_value for e in offered] == ["Ahmed M. Ali"]     # found verbatim although it was sampled out


def test_no_examples_when_the_feature_is_switched_off(settings, learning):
    learning.store.upsert("fb-1", "employee_name", "Ahmed Ali", "Ahmed M. Ali")
    off = LearningAgent(learning.store, Settings(**{**settings.__dict__, "learning_examples": 0}))
    assert off.examples_for("Ahmed Ali") == []


# ---------------------------------------------------------------------- analytics
def test_the_summary_counts_documents_fields_confidence_and_corrections(client):
    first = uploaded(client)
    uploaded(client, "march.csv", samples.csv_bytes)
    client.post("/documents/upload", files={"file": ("bad.txt", b"x")}, headers=HEADERS)     # refused, not counted
    correct(client, first, fields_of(client, first)["net_salary"]["id"], "5400")

    summary = client.get("/analytics/summary", headers=HEADERS).json()
    assert summary["documents_total"] == 2
    assert summary["documents_by_type"] == {"XLSX": 1, "CSV": 1}
    assert summary["documents_by_status"] == {"pending": 0, "processing": 0, "completed": 2, "failed": 0}
    assert summary["fields_total"] == 4
    assert abs(summary["average_confidence"] - 0.925) < 1e-9
    assert summary["corrections_total"] == 1
    assert summary["corrected_by_field"] == {"net_salary": 1}


def test_an_empty_system_has_a_summary_of_zeros(client):
    summary = client.get("/analytics/summary", headers=HEADERS).json()
    assert summary["documents_total"] == 0 and summary["average_confidence"] is None
    assert summary["documents_by_status"] == {"pending": 0, "processing": 0, "completed": 0, "failed": 0}
    assert summary["corrections_total"] == 0 and summary["corrected_by_field"] == {}


def test_the_new_endpoints_need_the_key(client):
    for path in ("/feedback/corrections", "/analytics/summary"):
        assert client.get(path).status_code == 401
        assert client.get(path, headers={"X-API-Key": "wrong"}).status_code == 401
