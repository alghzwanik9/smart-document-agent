"""Phase 2 criterion: edit a field, export, and the file opens in the same format with the corrected value
while the original in storage is unchanged."""
from __future__ import annotations

import hashlib
import io
from urllib.parse import unquote

import docx
import openpyxl

from core.schemas import FieldDraft
from document_processing import ProcessingError
from tests import samples
from tests.conftest import HEADERS, FakeExtractor
from tests.test_documents_api import upload


def uploaded(client, name="payroll.xlsx", make=samples.xlsx_bytes) -> int:
    return upload(client, name, make()).json()["document_id"]


def fields_of(client, document_id) -> dict[str, dict]:
    rows = client.get(f"/documents/{document_id}/extracted_fields", headers=HEADERS).json()
    return {row["field_name"]: row for row in rows}


def correct(client, document_id, field_id, value):
    return client.put(f"/documents/{document_id}/fields/{field_id}", json={"corrected_value": value}, headers=HEADERS)


def stored_files(settings):
    return [p for p in settings.storage_dir.iterdir() if p.suffix in (".xlsx", ".csv", ".docx", ".pdf")]


# ---------------------------------------------------------------------- PUT
def test_a_correction_is_stored_and_flagged(client):
    document_id = uploaded(client)
    net = fields_of(client, document_id)["net_salary"]

    response = correct(client, document_id, net["id"], "5400")

    assert response.status_code == 200
    body = response.json()
    assert body["corrected_value"] == "5400" and body["is_corrected"] is True and body["original_value"] == "5300"
    assert fields_of(client, document_id)["net_salary"]["corrected_value"] == "5400"


def test_an_amount_is_stored_in_one_spelling(client):
    document_id = uploaded(client)
    net = fields_of(client, document_id)["net_salary"]

    assert correct(client, document_id, net["id"], " ٥٬٤٠٠.٠ ").json()["corrected_value"] == "5400"
    assert correct(client, document_id, net["id"], "5,400.50").json()["corrected_value"] == "5400.5"


def test_text_is_stored_trimmed(client):
    document_id = uploaded(client)
    name = fields_of(client, document_id)["employee_name"]

    assert correct(client, document_id, name["id"], "  Ahmad Ali ").json()["corrected_value"] == "Ahmad Ali"


def test_an_amount_field_refuses_text(client):
    document_id = uploaded(client)
    net = fields_of(client, document_id)["net_salary"]

    assert correct(client, document_id, net["id"], "a lot").status_code == 422
    assert fields_of(client, document_id)["net_salary"]["is_corrected"] is False


def test_putting_the_original_value_back_cancels_the_correction(client):
    document_id = uploaded(client)
    net = fields_of(client, document_id)["net_salary"]
    correct(client, document_id, net["id"], "5400")

    body = correct(client, document_id, net["id"], "5300").json()

    assert body["is_corrected"] is False and body["corrected_value"] is None


def test_a_field_of_another_document_or_a_missing_one_is_not_found(client):
    first, second = uploaded(client), uploaded(client)
    net = fields_of(client, first)["net_salary"]

    assert correct(client, second, net["id"], "1").status_code == 404
    assert correct(client, first, 9999, "1").status_code == 404
    assert correct(client, 9999, net["id"], "1").status_code == 404


def test_a_correction_needs_the_key_and_a_value(client):
    document_id = uploaded(client)
    net = fields_of(client, document_id)["net_salary"]
    path = f"/documents/{document_id}/fields/{net['id']}"

    assert client.put(path, json={"corrected_value": "1"}).status_code == 401
    assert client.put(path, json={}, headers=HEADERS).status_code == 422
    assert client.put(path, json={"corrected_value": "x" * 1000}, headers=HEADERS).status_code == 422


# ---------------------------------------------------------------------- export
def test_the_criterion_xlsx_edit_then_export(client, settings):
    document_id = uploaded(client)
    net = fields_of(client, document_id)["net_salary"]
    before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in stored_files(settings)}
    correct(client, document_id, net["id"], "5400")

    response = client.get(f"/documents/{document_id}/export", headers=HEADERS)

    assert response.status_code == 200
    assert "spreadsheetml" in response.headers["content-type"]
    assert response.headers["content-disposition"].startswith("attachment;")
    assert "x-export-unplaced" not in response.headers
    sheet = openpyxl.load_workbook(io.BytesIO(response.content)).active
    assert sheet["F2"].value == 5400 and sheet["A2"].value == "Ahmed Ali" and sheet["F3"].value == 5700
    after = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in stored_files(settings)}
    assert after == before


def test_the_criterion_docx_edit_then_export(client, settings):
    document_id = uploaded(client, "payroll.docx", samples.docx_bytes)
    name = fields_of(client, document_id)["employee_name"]
    before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in stored_files(settings)}
    correct(client, document_id, name["id"], "Ahmad Ali")

    response = client.get(f"/documents/{document_id}/export", headers=HEADERS)

    assert response.status_code == 200 and "wordprocessingml" in response.headers["content-type"]
    assert docx.Document(io.BytesIO(response.content)).tables[0].cell(1, 0).text == "Ahmad Ali"
    assert {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in stored_files(settings)} == before


def test_csv_and_pdf_export_in_their_own_format(client):
    csv_id = uploaded(client, "payroll.csv", samples.csv_bytes)
    correct(client, csv_id, fields_of(client, csv_id)["net_salary"]["id"], "5400")
    pdf_id = uploaded(client, "payroll.pdf", samples.pdf_bytes)
    correct(client, pdf_id, fields_of(client, pdf_id)["net_salary"]["id"], "5400")

    csv_response = client.get(f"/documents/{csv_id}/export", headers=HEADERS)
    pdf_response = client.get(f"/documents/{pdf_id}/export", headers=HEADERS)

    assert csv_response.headers["content-type"].startswith("text/csv")
    assert "Ahmed Ali,E001,5000,500,200,5400" in csv_response.text
    assert pdf_response.headers["content-type"] == "application/pdf" and pdf_response.content.startswith(b"%PDF-")


def test_the_download_name_is_the_original_name_marked_corrected(client):
    document_id = uploaded(client, "كشف يونيو.xlsx")

    disposition = client.get(f"/documents/{document_id}/export", headers=HEADERS).headers["content-disposition"]

    assert "filename*=UTF-8''" in disposition
    assert unquote(disposition.split("filename*=UTF-8''")[1]) == "كشف يونيو_corrected.xlsx"
    assert disposition.encode("latin-1")        # every header value must survive HTTP


def test_a_correction_with_no_place_in_the_file_is_reported_in_a_header(settings):
    from fastapi.testclient import TestClient
    from main import create_app

    drafts = [FieldDraft(record_index=0, field_name="employee_name", value="Ahmed Ali", confidence=0.9),
              FieldDraft(record_index=0, field_name="net_salary", value="9999", confidence=0.4)]
    with TestClient(create_app(settings, extractor=FakeExtractor(drafts), ocr_page=lambda png: "")) as client:
        document_id = uploaded(client)
        net = fields_of(client, document_id)["net_salary"]
        correct(client, document_id, net["id"], "1")

        response = client.get(f"/documents/{document_id}/export", headers=HEADERS)

    assert response.status_code == 200 and response.headers["x-export-unplaced"] == str(net["id"])


def test_a_format_that_is_not_the_originals_is_refused(client):
    document_id = uploaded(client)

    assert client.get(f"/documents/{document_id}/export?format=docx", headers=HEADERS).status_code == 422
    assert client.get(f"/documents/{document_id}/export?format=xlsx", headers=HEADERS).status_code == 200


def test_a_document_that_is_not_completed_is_not_exported(settings):
    from fastapi.testclient import TestClient
    from main import create_app

    failing = FakeExtractor(error=ProcessingError("The LLM is not configured"))
    with TestClient(create_app(settings, extractor=failing, ocr_page=lambda png: "")) as client:
        document_id = uploaded(client)

        assert client.get(f"/documents/{document_id}/export", headers=HEADERS).status_code == 409


def test_export_needs_the_key_and_an_existing_document(client):
    document_id = uploaded(client)

    assert client.get(f"/documents/{document_id}/export").status_code == 401
    assert client.get("/documents/9999/export", headers=HEADERS).status_code == 404


def test_a_missing_original_file_is_reported(client, settings):
    document_id = uploaded(client)
    for path in stored_files(settings):
        path.unlink()

    assert client.get(f"/documents/{document_id}/export", headers=HEADERS).status_code == 404
