"""HTTP client for the backend. Every request carries the `X-API-Key` header."""
from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from urllib.parse import unquote

import httpx

DEFAULT_API_URL = "http://localhost:8000"
TIMEOUT_SECONDS = 60.0


class ApiError(Exception):
    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status = status
        self.detail = detail


class Unreachable(ApiError):
    def __init__(self, url: str):
        super().__init__(0, url)
        self.url = url


class ApiClient:
    def __init__(self, base_url: str, api_key: str, client: httpx.Client | None = None):
        self.base_url = base_url.rstrip("/")
        self._client = client or httpx.Client(timeout=TIMEOUT_SECONDS)
        self._headers = {"X-API-Key": api_key}

    @property
    def has_key(self) -> bool:
        return bool(self._headers["X-API-Key"])

    @classmethod
    def from_environment(cls) -> "ApiClient":
        return cls(os.environ.get("API_URL", DEFAULT_API_URL), os.environ.get("API_KEY", ""))

    def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        try:
            response = self._client.request(method, f"{self.base_url}{path}", headers=self._headers, **kwargs)
        except httpx.TransportError as exc:
            raise Unreachable(self.base_url) from exc
        if response.is_error:
            try:
                detail = response.json().get("detail", response.text)
            except ValueError:
                detail = response.text
            raise ApiError(response.status_code, detail if isinstance(detail, str) else str(detail))
        return response

    def upload(self, filename: str, data: bytes) -> dict:
        return self._request("POST", "/documents/upload", files={"file": (filename, data)}).json()

    def list_documents(self, page: int = 1, page_size: int = 10) -> dict:
        return self._request("GET", "/documents", params={"page": page, "page_size": page_size}).json()

    def get_document(self, document_id: int) -> dict:
        return self._request("GET", f"/documents/{document_id}").json()

    def delete_document(self, document_id: int) -> None:
        self._request("DELETE", f"/documents/{document_id}")

    def get_fields(self, document_id: int) -> list[dict]:
        return self._request("GET", f"/documents/{document_id}/extracted_fields").json()

    def update_field(self, document_id: int, field_id: int, value: str) -> dict:
        return self._request("PUT", f"/documents/{document_id}/fields/{field_id}",
                             json={"corrected_value": value}).json()

    def analytics_summary(self) -> dict:
        return self._request("GET", "/analytics/summary").json()

    def list_corrections(self, page: int = 1, page_size: int = 10) -> dict:
        return self._request("GET", "/feedback/corrections", params={"page": page, "page_size": page_size}).json()

    def export(self, document_id: int) -> "Export":
        response = self._request("GET", f"/documents/{document_id}/export")
        unplaced = response.headers.get("X-Export-Unplaced", "")
        return Export(content=response.content, filename=_download_name(response.headers.get("Content-Disposition", "")),
                      media_type=response.headers.get("Content-Type", "application/octet-stream"),
                      unplaced=[int(item) for item in unplaced.split(",") if item.strip().isdigit()])


@dataclass
class Export:
    content: bytes
    filename: str
    media_type: str
    unplaced: list[int]     # ids of corrected fields the backend could not find in the file


def _download_name(disposition: str) -> str:
    """The UTF-8 file name of a Content-Disposition header, which carries Arabic names."""
    for part in disposition.split(";"):
        part = part.strip()
        if part.startswith("filename*=UTF-8''"):
            return unquote(part[len("filename*=UTF-8''"):])
    return "export"


@lru_cache(maxsize=1)
def shared_client() -> ApiClient:
    """One client for every page of the running app."""
    return ApiClient.from_environment()
