"""Database engine, session, and declarative base for hop-core."""

from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from typing import AsyncGenerator, Optional

Base = declarative_base()

_engine = None
_SessionLocal = None


def init_engine(database_url: str, echo: bool = False):
    """Create the SQLAlchemy engine and session factory."""
    global _engine, _SessionLocal
    _engine = create_engine(database_url, echo=echo)
    _SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_engine)


def get_engine():
    if _engine is None:
        raise RuntimeError("Database engine not initialized. Call init_engine() first.")
    return _engine


def get_session_factory():
    if _SessionLocal is None:
        raise RuntimeError("Database engine not initialized. Call init_engine() first.")
    return _SessionLocal


async def init_db():
    """Create all tables registered on Base.metadata."""
    engine = get_engine()
    Base.metadata.create_all(bind=engine)


async def get_db() -> AsyncGenerator[Session, None]:
    """FastAPI dependency for database sessions."""
    SessionLocal = get_session_factory()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
