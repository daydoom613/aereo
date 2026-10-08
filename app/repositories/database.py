"""Creating the database engine and its tables."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import Engine, create_engine

from app.models import Base


def create_engine_for(database_url: str) -> Engine:
    # SQLite connections refuse to be used from a thread other than the one that opened them.
    # Requests run in a thread pool and each uses its own session, so that check is lifted.
    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    return create_engine(database_url, connect_args=connect_args)


def prepare_database(engine: Engine) -> None:
    """Create the folder a SQLite file lives in, then any tables that do not exist yet."""
    database = engine.url.database
    if engine.url.get_backend_name() == "sqlite" and database and database != ":memory:":
        Path(database).parent.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(engine)
