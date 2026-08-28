from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from .models import Base


def create_database(database_url: str = "sqlite:///./block_sangam.db"):
    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    engine_args = {"connect_args": connect_args}
    if database_url in {"sqlite://", "sqlite:///:memory:"}:
        # FastAPI tests and local in-memory callers use several connections;
        # StaticPool makes them share the one in-memory database.
        engine_args["poolclass"] = StaticPool
    engine = create_engine(database_url, **engine_args)
    Base.metadata.create_all(engine)
    return engine


def get_session(engine) -> Generator[Session, None, None]:
    factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    session = factory()
    try:
        yield session
    finally:
        session.close()
