"""The column mappings the model has given, kept per layout. Best effort: a failing store means one more model call,
never a lost document."""
from __future__ import annotations

import json
import logging

from database.connection import Database
from database.models import LayoutMapping

log = logging.getLogger("document_processing.layout_store")


class LayoutStore:
    def __init__(self, db: Database):
        self._db = db

    def get(self, fingerprint: str) -> list[str | None] | None:
        def read(session):
            row = session.get(LayoutMapping, fingerprint)
            return None if row is None else json.loads(row.columns)
        return self._run(read)

    def put(self, fingerprint: str, columns: list[str | None]) -> None:
        def write(session):
            row = session.get(LayoutMapping, fingerprint)
            if row is None:
                session.add(LayoutMapping(fingerprint=fingerprint, columns=json.dumps(columns), use_count=0))
            else:
                row.columns = json.dumps(columns)
        self._run(write, commit=True)

    def used(self, fingerprint: str) -> None:
        def count(session):
            row = session.get(LayoutMapping, fingerprint)
            if row is not None:
                row.use_count += 1
        self._run(count, commit=True)

    def discard(self, fingerprint: str) -> None:
        def remove(session):
            row = session.get(LayoutMapping, fingerprint)
            if row is not None:
                session.delete(row)
        self._run(remove, commit=True)

    def _run(self, action, commit: bool = False):
        session = self._db.session()
        try:
            result = action(session)
            if commit:
                session.commit()
            return result
        except Exception as exc:
            log.error("The layout store failed: %s", type(exc).__name__)
            session.rollback()
            return None
        finally:
            session.close()
