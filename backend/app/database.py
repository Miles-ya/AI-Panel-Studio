from __future__ import annotations

from pathlib import Path

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session

from app.models import Base
from app.seed import seed_presets


def create_sqlite_engine(database_url: str) -> Engine:
    engine = create_engine(database_url)
    database_path = engine.url.database
    if engine.url.drivername.startswith("sqlite") and database_path not in {None, ":memory:"}:
        Path(database_path).parent.mkdir(parents=True, exist_ok=True)

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(dbapi_connection: object, _: object) -> None:
        cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
        cursor.execute("PRAGMA foreign_keys = ON")
        cursor.close()

    return engine


def initialize_database(engine: Engine, *, seed: bool = True) -> None:
    Base.metadata.create_all(engine)
    if seed:
        with Session(engine) as session:
            seed_presets(session)
