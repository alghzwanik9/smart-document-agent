"""The SQLAlchemy engine and its sessions. One `Database` per app, so tests can use a database of their own."""
from __future__ import annotations

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from database.models import Base


class Database:
    def __init__(self, url: str):
        sqlite = url.startswith("sqlite")
        # Background tasks run in other threads than the request that started them.
        self.engine = create_engine(url, connect_args={"check_same_thread": False} if sqlite else {})
        if sqlite:
            @event.listens_for(self.engine, "connect")
            def _enable_foreign_keys(dbapi_connection, _record):   # ON DELETE CASCADE needs it in SQLite
                dbapi_connection.execute("PRAGMA foreign_keys=ON")
        self._sessions = sessionmaker(self.engine, expire_on_commit=False)

    def create_tables(self) -> None:
        Base.metadata.create_all(self.engine)

    def session(self) -> Session:
        return self._sessions()

    def dispose(self) -> None:
        self.engine.dispose()
