"""Settings read from environment variables. No secret and no provider is fixed in code."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

DEFAULT_MAX_UPLOAD_MB = 20
DEFAULT_LLM_TIMEOUT_SECONDS = 120.0
DEFAULT_LLM_CHUNK_CHARS = 12000
DEFAULT_OCR_LANGUAGES = "ara+eng"
DEFAULT_LEARNING_EXAMPLES = 5
DEFAULT_LEARNING_MAX_DISTANCE = 0.35


@dataclass(frozen=True)
class Settings:
    api_key: str = ""
    storage_dir: Path = Path("storage")
    database_url: str = ""
    max_upload_mb: int = DEFAULT_MAX_UPLOAD_MB
    llm_base_url: str = ""
    llm_model: str = ""
    llm_api_key: str = ""
    llm_timeout_seconds: float = DEFAULT_LLM_TIMEOUT_SECONDS
    llm_chunk_chars: int = DEFAULT_LLM_CHUNK_CHARS
    ocr_languages: str = DEFAULT_OCR_LANGUAGES
    learning_examples: int = DEFAULT_LEARNING_EXAMPLES
    learning_max_distance: float = DEFAULT_LEARNING_MAX_DISTANCE
    table_extraction: bool = True       # read payroll tables by code; off sends every sheet whole to the model

    @property
    def db_url(self) -> str:
        """The original files and the database share `storage_dir`, so one volume holds all the data."""
        return self.database_url or f"sqlite:///{(self.storage_dir / 'app.db').as_posix()}"

    @property
    def chroma_dir(self) -> Path:
        return self.storage_dir / "chroma"

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    @property
    def llm_configured(self) -> bool:
        return bool(self.llm_base_url.strip() and self.llm_model.strip())


def _number(env: Mapping[str, str], name: str, default, cast):
    raw = env.get(name, "").strip()
    if not raw:
        return default
    try:
        return cast(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be a number, got {raw!r}") from exc


def _flag(env: Mapping[str, str], name: str, default: bool) -> bool:
    raw = env.get(name, "").strip().lower()
    return default if not raw else raw not in ("0", "false", "no", "off")


def load_settings(env: Mapping[str, str] | None = None) -> Settings:
    env = os.environ if env is None else env
    return Settings(
        api_key=env.get("API_KEY", "").strip(),
        storage_dir=Path(env.get("STORAGE_DIR", "").strip() or "storage"),
        database_url=env.get("DATABASE_URL", "").strip(),
        max_upload_mb=_number(env, "MAX_UPLOAD_MB", DEFAULT_MAX_UPLOAD_MB, int),
        llm_base_url=env.get("LLM_BASE_URL", "").strip().rstrip("/"),
        llm_model=env.get("LLM_MODEL", "").strip(),
        llm_api_key=env.get("LLM_API_KEY", "").strip(),
        llm_timeout_seconds=_number(env, "LLM_TIMEOUT_SECONDS", DEFAULT_LLM_TIMEOUT_SECONDS, float),
        llm_chunk_chars=_number(env, "LLM_CHUNK_CHARS", DEFAULT_LLM_CHUNK_CHARS, int),
        ocr_languages=env.get("OCR_LANGUAGES", "").strip() or DEFAULT_OCR_LANGUAGES,
        learning_examples=_number(env, "LEARNING_EXAMPLES", DEFAULT_LEARNING_EXAMPLES, int),
        learning_max_distance=_number(env, "LEARNING_MAX_DISTANCE", DEFAULT_LEARNING_MAX_DISTANCE, float),
        table_extraction=_flag(env, "TABLE_EXTRACTION", True),
    )
