from __future__ import annotations

import zlib

import pytest
from fastapi.testclient import TestClient

from chromadb.api.types import Documents, EmbeddingFunction, Embeddings

from core.config import Settings
from core.schemas import FieldDraft
from feedback_loop.chroma_db import CorrectionStore
from feedback_loop.learning_agent import LearningAgent
from main import create_app

API_KEY = "test-key"
HEADERS = {"X-API-Key": API_KEY}


class FakeExtractor:
    """Stands in for the LLM: returns fixed drafts, or raises what it was given."""

    def __init__(self, drafts=None, error: Exception | None = None):
        self.drafts = drafts if drafts is not None else [
            FieldDraft(record_index=0, field_name="employee_name", value="Ahmed Ali", confidence=0.9),
            FieldDraft(record_index=0, field_name="net_salary", value="5300", confidence=0.95),
        ]
        self.error = error
        self.texts: list[str] = []
        self.examples: list[list] = []      # what the learning agent offered for each call

    def extract(self, text: str, examples_for=None, layouts=None):
        self.texts.append(text)
        self.examples.append(list(examples_for(text)) if examples_for else [])
        if self.error:
            raise self.error
        return self.drafts


class TrigramEmbedding(EmbeddingFunction[Documents]):
    """A local stand-in for the ONNX model: texts sharing letter triples get close vectors, and nothing is downloaded."""

    DIMENSIONS = 128

    def __init__(self) -> None:
        pass

    def __call__(self, input: Documents) -> Embeddings:
        vectors = []
        for text in input:
            vector = [0.0] * self.DIMENSIONS
            padded = f"  {text.lower()}  "
            for i in range(len(padded) - 2):
                vector[zlib.crc32(padded[i:i + 3].encode()) % self.DIMENSIONS] += 1.0
            norm = sum(v * v for v in vector) ** 0.5 or 1.0
            vectors.append([v / norm for v in vector])
        return vectors

    @staticmethod
    def name() -> str:
        return "test-trigram"

    def get_config(self) -> dict:
        return {}

    @staticmethod
    def build_from_config(config: dict) -> "TrigramEmbedding":
        return TrigramEmbedding()


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(api_key=API_KEY, storage_dir=tmp_path / "storage", llm_base_url="http://llm.test/v1",
                    llm_model="test-model", max_upload_mb=1)


@pytest.fixture
def extractor() -> FakeExtractor:
    return FakeExtractor()


@pytest.fixture
def learning(settings) -> LearningAgent:
    return LearningAgent(CorrectionStore(settings.chroma_dir, TrigramEmbedding()), settings)


@pytest.fixture
def client(settings, extractor, learning):
    app = create_app(settings, extractor=extractor, ocr_page=lambda png: "scanned text", learning=learning)
    with TestClient(app) as test_client:    # the context runs the lifespan: storage folder and tables
        yield test_client
