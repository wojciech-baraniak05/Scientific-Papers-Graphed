from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from loguru import logger
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings
from app.db.models import Base

_engine: Engine | None = None
_SessionFactory: sessionmaker[Session] | None = None


def get_engine() -> Engine:
    global _engine, _SessionFactory
    if _engine is None:
        settings = get_settings()
        url = settings.sqlalchemy_url
        kwargs: dict = {"pool_pre_ping": True, "future": True}
        if url.startswith("mysql"):
            kwargs.update(pool_size=10, max_overflow=20, pool_recycle=3600)
        _engine = create_engine(url, **kwargs)
        _SessionFactory = sessionmaker(bind=_engine, autoflush=False, expire_on_commit=False)
        logger.debug("Engine created for {}", settings.safe_sqlalchemy_url)
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    if _SessionFactory is None:
        get_engine()
    assert _SessionFactory is not None
    return _SessionFactory


@contextmanager
def session_scope() -> Iterator[Session]:
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_db(engine: Engine | None = None) -> None:
    engine = engine or get_engine()
    Base.metadata.create_all(engine, checkfirst=True)
    logger.info("Schema ensured (create_all checkfirst).")


def get_db_size_bytes(session: Session) -> int:
    dialect = session.bind.dialect.name
    if dialect == "mysql":
        row = session.execute(
            text(
                "SELECT COALESCE(SUM(data_length + index_length), 0) "
                "FROM information_schema.tables WHERE table_schema = DATABASE()"
            )
        ).scalar()
        return int(row or 0)
    if dialect == "sqlite":
        page_count = session.execute(text("PRAGMA page_count")).scalar() or 0
        page_size = session.execute(text("PRAGMA page_size")).scalar() or 0
        return int(page_count) * int(page_size)
    return 0
