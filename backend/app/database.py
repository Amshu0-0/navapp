"""Database connection setup.

Defines the SQLAlchemy engine, session factory, and declarative base that
every model in `app/models.py` inherits from. This is the one place that
knows which database we're actually talking to (SQLite locally, Postgres
in production) — models and routes stay database-agnostic.
"""

import os

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

# Defaults to a local SQLite file for dev. In production this is overridden
# via the DATABASE_URL env var to point at Postgres (see Phase 9).
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./navapp.db")

# SQLite only allows a connection to be used from the thread that created it
# by default. FastAPI can hand requests to different threads, so this flag
# relaxes that restriction. Postgres doesn't need it, hence the conditional.
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)

# Factory that produces new DB sessions on demand. autocommit/autoflush are
# left off so we control exactly when writes hit the database.
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    """Base class every ORM model inherits from.

    SQLAlchemy uses this to collect table metadata (used by Alembic for
    autogenerating migrations, and by tests to build an in-memory schema).
    """

    pass


def get_db() -> Session:
    """FastAPI dependency that yields a DB session for the life of a request.

    Usage: `def endpoint(db: Session = Depends(get_db))`. The session is
    always closed after the request finishes, even if the handler raises.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
