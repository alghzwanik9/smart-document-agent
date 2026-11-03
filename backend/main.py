"""Entry point: `uvicorn main:app` from the backend folder."""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from api.v1 import analytics, documents, feedback
from core.config import Settings, load_settings
from database.connection import Database
from document_processing.layout_store import LayoutStore
from document_processing.llm_extractor import LLMExtractor
from document_processing.ocr import make_ocr
from feedback_loop.chroma_db import CorrectionStore
from feedback_loop.learning_agent import LearningAgent


def create_app(settings: Settings | None = None, extractor=None, ocr_page=None, learning=None,
               layouts=None) -> FastAPI:
    """`extractor`, `ocr_page`, `learning` and `layouts` can be replaced (tests do); by default they come from the settings."""
    settings = settings or load_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        settings.storage_dir.mkdir(parents=True, exist_ok=True)
        app.state.db = Database(settings.db_url)
        app.state.db.create_tables()
        app.state.layouts = layouts or LayoutStore(app.state.db)
        yield
        app.state.db.dispose()

    app = FastAPI(title="Smart Document Agent", lifespan=lifespan)
    app.state.settings = settings
    app.state.extractor = extractor or LLMExtractor(settings)
    app.state.ocr_page = ocr_page or make_ocr(settings.ocr_languages)
    app.state.learning = learning or LearningAgent(CorrectionStore(settings.chroma_dir), settings)
    app.include_router(documents.router)
    app.include_router(feedback.router)
    app.include_router(analytics.router)

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    return app


app = create_app()
