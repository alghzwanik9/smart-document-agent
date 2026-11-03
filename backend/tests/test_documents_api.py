import pytest

from core.schemas import FieldDraft
from document_processing import ProcessingError
from tests import samples
from tests.conftest import HEADERS, FakeExtractor

FILES = {
    "xlsx": ("payroll.xlsx", samples.xlsx_bytes),
    "csv": ("payroll.csv", samples.csv_bytes),
    "docx": ("payroll.docx", samples.docx_bytes),
    "pdf-text": ("payroll.pdf", samples.pdf_bytes),
    "pdf-scanned": ("scan.pdf", samples.scanned_pdf_bytes),
}


def upload(client, name, data, headers=HEADERS):
    return client.post("/documents/upload", files={"file": (name, data)}, headers=headers)


# ---------------------------------------------------------------------- access key
def test_health_needs_no_key(client):
    assert client.get("/health").json() == {"status": "ok"}


@pytest.mark.parametrize("path", ["/documents", "/documents/1", "/documents/1/extracted_fields"])
def test_every_other_get_endpoint_refuses_a_missing_or_wrong_key(client, path):
    assert client.get(path).status_code == 401
    assert client.get(path, headers={"X-API-Key": "wrong"}).status_code == 401


def test_upload_and_delete_refuse_a_missing_key(client):
    assert upload(client, "a.csv", samples.csv_bytes(), headers={}).status_code == 401
    assert client.delete("/documents/1").status_code == 401


def test_a_server_without_an_api_key_lets_nothing_through(settings, extractor):
    from dataclasses import replace
    from fastapi.testclient import TestClient
    from main import create_app

    with TestClient(create_app(replace(settings, api_key=""), extractor=extractor)) as open_client:
        assert open_client.get("/documents", headers=HEADERS).status_code == 503


# ---------------------------------------------------------------------- the phase 1 criterion
@pytest.mark.parametrize("name,make", FILES.values(), ids=FILES.keys())
def test_a_file_of_each_type_ends_completed_with_stored_fields(client, name, make):
    accepted = upload(client, name, make())
    assert accepted.status_code == 202
    body = accepted.json()
    assert body["status"] == "pending"

    document = client.get(f"/documents/{body['document_id']}", headers=HEADERS).json()
    assert document["status"] == "completed" and document["error_message"] is None
    stored = client.get(f"/documents/{body['document_id']}/extracted_fields", headers=HEADERS).json()
    assert {f["field_name"] for f in stored} == {"employee_name", "net_salary"}
    assert all(f["original_value"] and 0 <= f["confidence"] <= 1 for f in stored)
    assert all(f["is_corrected"] is False and f["corrected_value"] is None for f in stored)
    assert all(f["extraction_model_version"] == "test-model" for f in stored)


def test_the_extractor_receives_the_text_of_the_document(client, extractor):
    upload(client, "payroll.xlsx", samples.xlsx_bytes())
    assert "Ahmed Ali | E001 | 5000 | 500 | 200 | 5300" in extractor.texts[0]


def test_a_scanned_pdf_is_read_through_ocr(client, extractor):
    upload(client, "scan.pdf", samples.scanned_pdf_bytes())
    assert "scanned text" in extractor.texts[0]


@pytest.mark.parametrize("name,data,status", [
    pytest.param("virus.exe", b"MZ", 415, id="unsupported-type"),
    pytest.param("fake.pdf", b"not a pdf", 400, id="wrong-signature"),
    pytest.param("big.pdf", b"%PDF-" + b"0" * (1024 * 1024 + 1), 413, id="over-the-limit"),
    pytest.param("empty.csv", b"", 400, id="empty"),
])
def test_an_unacceptable_file_is_refused_and_leaves_no_trace(client, settings, name, data, status):
    assert upload(client, name, data).status_code == status
    assert client.get("/documents", headers=HEADERS).json()["total"] == 0
    assert list(settings.storage_dir.glob("*.pdf")) + list(settings.storage_dir.glob("*.exe")) == []


# ---------------------------------------------------------------------- the original file
def test_the_original_is_stored_under_a_random_name_and_never_changed(client, settings):
    data = samples.xlsx_bytes()
    upload(client, "../../evil name.xlsx", data)
    stored = [p for p in settings.storage_dir.iterdir() if p.suffix == ".xlsx"]
    assert len(stored) == 1 and "evil" not in stored[0].name
    assert stored[0].read_bytes() == data
    listed = client.get("/documents", headers=HEADERS).json()["items"][0]
    assert listed["filename"] == "evil name.xlsx" and "stored_path" not in listed


# ---------------------------------------------------------------------- failures are statuses
@pytest.mark.parametrize("error,expected", [
    pytest.param(ProcessingError("The LLM is not configured"), "The LLM is not configured", id="known"),
    pytest.param(ValueError("secret salary text Ahmed 5000"), "ValueError", id="unexpected"),
])
def test_a_failed_extraction_is_recorded_without_stopping_the_service(settings, error, expected):
    from fastapi.testclient import TestClient
    from main import create_app

    app = create_app(settings, extractor=FakeExtractor(error=error), ocr_page=lambda png: "")
    with TestClient(app) as client:
        document_id = upload(client, "a.csv", samples.csv_bytes()).json()["document_id"]
        document = client.get(f"/documents/{document_id}", headers=HEADERS).json()
        assert document["status"] == "failed"
        assert expected in document["error_message"] and "secret" not in document["error_message"]
        assert client.get("/health").status_code == 200
        assert client.get(f"/documents/{document_id}/extracted_fields", headers=HEADERS).json() == []


def test_a_document_with_no_record_fails_instead_of_completing_empty(settings):
    from fastapi.testclient import TestClient
    from main import create_app

    with TestClient(create_app(settings, extractor=FakeExtractor(drafts=[]))) as client:
        document_id = upload(client, "a.csv", samples.csv_bytes()).json()["document_id"]
        document = client.get(f"/documents/{document_id}", headers=HEADERS).json()
        assert document["status"] == "failed" and "No payroll record" in document["error_message"]


def test_bytes_that_only_look_like_a_workbook_are_refused_at_upload(client):
    broken = b"PK\x03\x04" + b"\x00" * 30 + b"xl/workbook.xml"     # carries the member name but is no real zip
    assert upload(client, "a.xlsx", broken).status_code == 400


def test_a_failed_document_can_be_uploaded_again(client, extractor):
    extractor.error = ProcessingError("provider down")
    first = upload(client, "a.csv", samples.csv_bytes()).json()["document_id"]
    extractor.error = None
    second = upload(client, "a.csv", samples.csv_bytes()).json()["document_id"]
    statuses = {i: client.get(f"/documents/{i}", headers=HEADERS).json()["status"] for i in (first, second)}
    assert statuses == {first: "failed", second: "completed"}


# ---------------------------------------------------------------------- list, details, delete
def test_the_list_is_paged_newest_first(client):
    ids = [upload(client, f"d{n}.csv", samples.csv_bytes()).json()["document_id"] for n in range(5)]
    page = client.get("/documents", params={"page": 1, "page_size": 2}, headers=HEADERS).json()
    assert page["total"] == 5 and page["page"] == 1 and page["page_size"] == 2
    assert [d["id"] for d in page["items"]] == [ids[4], ids[3]]
    last = client.get("/documents", params={"page": 3, "page_size": 2}, headers=HEADERS).json()
    assert [d["id"] for d in last["items"]] == [ids[0]]


@pytest.mark.parametrize("params", [{"page": 0}, {"page_size": 0}, {"page_size": 101}])
def test_paging_limits_are_enforced(client, params):
    assert client.get("/documents", params=params, headers=HEADERS).status_code == 422


def test_an_unknown_document_is_a_404(client):
    for path in ("/documents/999", "/documents/999/extracted_fields"):
        assert client.get(path, headers=HEADERS).status_code == 404
    assert client.delete("/documents/999", headers=HEADERS).status_code == 404


def test_delete_removes_the_document_its_fields_and_the_original_file(client, settings):
    document_id = upload(client, "a.xlsx", samples.xlsx_bytes()).json()["document_id"]
    assert any(settings.storage_dir.glob("*.xlsx"))

    assert client.delete(f"/documents/{document_id}", headers=HEADERS).status_code == 204

    assert client.get(f"/documents/{document_id}", headers=HEADERS).status_code == 404
    assert not any(settings.storage_dir.glob("*.xlsx"))
    from sqlalchemy import func, select
    from database.models import ExtractedField
    with client.app.state.db.session() as session:
        assert session.scalar(select(func.count()).select_from(ExtractedField)) == 0


def test_delete_still_works_when_the_original_is_already_gone(client, settings):
    document_id = upload(client, "a.xlsx", samples.xlsx_bytes()).json()["document_id"]
    for path in settings.storage_dir.glob("*.xlsx"):
        path.unlink()
    assert client.delete(f"/documents/{document_id}", headers=HEADERS).status_code == 204


def test_records_of_one_document_keep_their_record_index(settings):
    from fastapi.testclient import TestClient
    from main import create_app

    drafts = [FieldDraft(record_index=i, field_name="employee_name", value=f"Emp {i}", confidence=0.9) for i in (0, 1, 2)]
    with TestClient(create_app(settings, extractor=FakeExtractor(drafts=drafts))) as client:
        document_id = upload(client, "a.csv", samples.csv_bytes()).json()["document_id"]
        stored = client.get(f"/documents/{document_id}/extracted_fields", headers=HEADERS).json()
        assert [(f["record_index"], f["original_value"]) for f in stored] == [(0, "Emp 0"), (1, "Emp 1"), (2, "Emp 2")]
