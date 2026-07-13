"""
app/database.py — SQLAlchemy engine and session management.

Usage (in runner.py and anywhere else that needs DB access):

    from app.database import get_db
    from app.models import Source

    with get_db() as db:
        sources = db.query(Source).filter_by(is_active=True).all()

The context manager handles commit, rollback, and close automatically.
"""

from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings

# Engine — one per process; thread-safe connection pool built in
engine = create_engine(
    settings.sqlalchemy_database_url,
    pool_pre_ping=True,   # test connections before using from pool
    echo=False,           # set True temporarily to log all SQL for debugging
)

# Session factory — call SessionLocal() to get a raw session
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@contextmanager
def get_db() -> Generator[Session, None, None]:
    """
    Context manager that yields a SQLAlchemy Session.

    - Commits on clean exit.
    - Rolls back on any exception (so no partial writes leak into the DB).
    - Always closes the session when the block exits.
    """
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def get_db_session() -> Generator[Session, None, None]:
    """
    FastAPI dependency that yields a SQLAlchemy Session.

    Use this with FastAPI's Depends() system:
        db: Session = Depends(get_db_session)

    The existing get_db() context manager is kept for the pipeline runner.
    """
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
