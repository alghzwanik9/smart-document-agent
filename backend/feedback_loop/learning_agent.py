"""Turns the user's corrections into examples for the next extraction.

SQLite (`feedback_loop`) is the record and ChromaDB the index over it. The vector side is best effort: a failure there is
logged and never loses or blocks a correction. Which examples reach the prompt is decided here, by distance, not by the model.
"""
from __future__ import annotations

import logging
import re
import unicodedata

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.config import Settings
from core.schemas import LearnedCorrection
from database.models import ExtractedField, FeedbackLoop
from feedback_loop.chroma_db import CorrectionStore, Neighbour

log = logging.getLogger("feedback_loop.learning_agent")

MAX_QUERY_CELLS = 300       # distinct cells searched in the index; past this the sheet is sampled (verbatim matches are not)
MAX_CELL_CHARS = 200
MIN_EXACT_CHARS = 3         # a shorter wrong value ('5') would "appear" everywhere


def _squash(text: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", text).casefold().split())


def _cells(text: str) -> list[str]:
    """The distinct cells of the text: a table row 'a | b | c' is three of them, a line of free text is one."""
    cells: dict[str, None] = {}
    for line in text.splitlines():
        for cell in line.split("|"):
            cell = cell.strip()[:MAX_CELL_CHARS]
            if cell and not cell.startswith("---"):
                cells[cell] = None
    unique = list(cells)
    if len(unique) > MAX_QUERY_CELLS:
        step = len(unique) / MAX_QUERY_CELLS
        unique = [unique[int(i * step)] for i in range(MAX_QUERY_CELLS)]
    return unique


class LearningAgent:
    def __init__(self, store: CorrectionStore, settings: Settings):
        self.store = store
        self.settings = settings

    # ------------------------------------------------------------------ recording
    def record(self, session: Session, field: ExtractedField) -> None:
        """Keeps one example per corrected field: a second correction of the same field replaces the first."""
        feedback = session.scalar(select(FeedbackLoop).where(FeedbackLoop.field_id == field.id))
        if feedback is None:
            feedback = FeedbackLoop(field_id=field.id, document_id=field.document_id, field_name=field.field_name)
            session.add(feedback)
        feedback.original_value = field.original_value
        feedback.corrected_value = field.corrected_value
        session.flush()
        vector_id = f"fb-{feedback.id}"
        feedback.vector_id = self._guard(
            lambda: self.store.upsert(vector_id, field.field_name, field.original_value or "", field.corrected_value)
        ) and vector_id or None

    def forget_field(self, session: Session, field_id: int) -> None:
        """The correction was cancelled: it is no longer an example."""
        feedback = session.scalar(select(FeedbackLoop).where(FeedbackLoop.field_id == field_id))
        if feedback is not None:
            self._drop_vectors([feedback.vector_id])
            session.delete(feedback)

    def forget_document(self, session: Session, document_id: int) -> None:
        """A deleted document takes its corrections with it: they quote its employees."""
        rows = session.scalars(select(FeedbackLoop).where(FeedbackLoop.document_id == document_id)).all()
        self._drop_vectors([row.vector_id for row in rows])

    # ------------------------------------------------------------------ retrieval
    def examples_for(self, text: str) -> list[LearnedCorrection]:
        """The corrections whose wrong value is written in `text` or looks like a value in it, nearest first.

        Two ways to find them, both decided here in code: a wrong value that appears verbatim in the text always
        applies (this also covers free text, such as a PDF line, where cells cannot be told apart); the others come
        from the vector index, searched with the cells of a table (a whole row would drown the value in its neighbours).
        """
        settings = self.settings
        if settings.learning_examples <= 0:
            return []
        found: dict[str, Neighbour] = {}

        def keep(neighbours: list[Neighbour]) -> None:
            for n in neighbours:
                if n.vector_id not in found or n.distance < found[n.vector_id].distance:
                    found[n.vector_id] = n

        if not self._guard(lambda: keep(self._written_in(text, self.store.everything()))):
            return []
        self._guard(lambda: keep([n for n in self.store.nearest(_cells(text), settings.learning_examples)
                                  if n.distance <= settings.learning_max_distance]))
        nearest_first = sorted(found.values(), key=lambda n: n.distance)[:settings.learning_examples]
        return [LearnedCorrection(n.field_name, n.original_value, n.corrected_value) for n in nearest_first]

    @staticmethod
    def _written_in(text: str, stored: list[Neighbour]) -> list[Neighbour]:
        haystack = _squash(text)
        return [n for n in stored if len(_squash(n.original_value)) >= MIN_EXACT_CHARS
                and re.search(rf"(?<!\w){re.escape(_squash(n.original_value))}(?!\w)", haystack)]

    # ------------------------------------------------------------------ internals
    def _drop_vectors(self, vector_ids: list[str | None]) -> None:
        ids = [vector_id for vector_id in vector_ids if vector_id]
        self._guard(lambda: self.store.delete(ids))

    @staticmethod
    def _guard(action) -> bool:
        try:
            action()
            return True
        except Exception as exc:    # the message can quote a payroll value: the type is enough
            log.error("The correction index failed: %s", type(exc).__name__)
            return False
