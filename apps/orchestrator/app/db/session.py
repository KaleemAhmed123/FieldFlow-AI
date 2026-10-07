"""Async SQLAlchemy engine + session factory. One engine per process."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from app.config import settings
from app.db.models import Base

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker | None = None


def get_sessionmaker() -> async_sessionmaker:
    if _sessionmaker is None:
        raise RuntimeError("DB not initialised — call init_db() first.")
    return _sessionmaker


async def init_db() -> None:
    """Create the engine and the tables. create_all is fine for the spine; alembic later."""
    global _engine, _sessionmaker
    _engine = create_async_engine(settings.database_url, future=True)
    _sessionmaker = async_sessionmaker(_engine, expire_on_commit=False)
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def dispose_db() -> None:
    global _engine
    if _engine is not None:
        await _engine.dispose()
        _engine = None
