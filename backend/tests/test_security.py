import pytest

from core.security import UploadRejected, safe_filename, validate_upload
from tests import samples

MB = 1024 * 1024


def accepted(name, data):
    return validate_upload(name, data, MB)


@pytest.mark.parametrize("name,data,expected", [
    pytest.param("a.pdf", samples.pdf_bytes(), "PDF", id="pdf"),
    pytest.param("a.docx", samples.docx_bytes(), "DOCX", id="docx"),
    pytest.param("a.xlsx", samples.xlsx_bytes(), "XLSX", id="xlsx"),
    pytest.param("a.csv", samples.csv_bytes(), "CSV", id="csv"),
    pytest.param("UPPER.XLSX", samples.xlsx_bytes(), "XLSX", id="upper-case-extension"),
])
def test_each_supported_type_is_accepted(name, data, expected):
    assert accepted(name, data)[0] == expected


@pytest.mark.parametrize("name,data,status", [
    pytest.param("a.exe", b"MZ....", 415, id="unsupported-extension"),
    pytest.param("noextension", b"abc", 415, id="no-extension"),
    pytest.param("a.pdf", b"", 400, id="empty"),
    pytest.param("a.pdf", b"not a pdf at all", 400, id="pdf-signature-missing"),
    pytest.param("a.docx", samples.xlsx_bytes(), 400, id="docx-that-is-an-xlsx"),
    pytest.param("a.xlsx", samples.docx_bytes(), 400, id="xlsx-that-is-a-docx"),
    pytest.param("a.xlsx", b"plain text", 400, id="xlsx-not-a-zip"),
    pytest.param("a.csv", b"a,b\x00c", 400, id="csv-with-binary"),
    pytest.param("a.pdf", b"%PDF-" + b"0" * (MB + 1), 413, id="too-large"),
])
def test_a_bad_file_is_refused_with_the_right_status(name, data, status):
    with pytest.raises(UploadRejected) as refused:
        accepted(name, data)
    assert refused.value.status_code == status


def test_the_content_decides_not_only_the_name():
    with pytest.raises(UploadRejected):
        accepted("report.pdf", samples.docx_bytes())


@pytest.mark.parametrize("raw,expected", [
    ("../../etc/passwd", "passwd"),
    ("C:\\Users\\x\\salaries.xlsx", "salaries.xlsx"),
    ("bad\x00name\n.csv", "badname.csv"),
    ("", "document"),
    (None, "document"),
    ("a" * 400 + ".pdf", ("a" * 400 + ".pdf")[:255]),
])
def test_safe_filename(raw, expected):
    assert safe_filename(raw) == expected
