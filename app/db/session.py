"""Engine / session factory and the FastAPI database dependency."""

from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings


def _build_engine(url: str) -> Engine:
    kwargs: dict = {"pool_pre_ping": True, "future": True}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
        if ":memory:" in url or url.endswith("mode=memory"):
            kwargs["poolclass"] = None
    elif url.startswith("postgres"):
        # Pin the session timezone so timestamptz values always come back UTC.
        kwargs["connect_args"] = {"options": "-c TimeZone=UTC"}
    engine = create_engine(url, **kwargs)
    if url.startswith("sqlite"):
        # Enforce foreign keys on SQLite so the test-suite behaves like Postgres.
        @event.listens_for(engine, "connect")
        def _set_sqlite_pragma(dbapi_connection, _record):  # pragma: no cover - driver hook
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()
    return engine


engine = _build_engine(settings.database_url)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, class_=Session)


def get_db() -> Generator[Session, None, None]:
    """Yield a request-scoped session and roll back on unhandled errors."""
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def transaction(db: Session) -> Session:
    """Commit the current unit of work, rolling back on failure."""
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    return db
