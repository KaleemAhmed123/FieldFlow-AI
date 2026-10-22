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
    """Create the engine + session factory.

    On Postgres (the real deploy) Alembic owns the schema — the Render start command runs
    `alembic upgrade head` before the app boots, so we do NOT create_all here (it would race the
    migrations and clash on the first ALTER). On SQLite (local dev + tests) there are no migrations,
    so create_all still builds the tables.
    """
    global _engine, _sessionmaker
    _engine = create_async_engine(settings.database_url, future=True)
    _sessionmaker = async_sessionmaker(_engine, expire_on_commit=False)
    if not settings.database_url.startswith("postgres"):
        async with _engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)


async def dispose_db() -> None:
    global _engine
    if _engine is not None:
        await _engine.dispose()
        _engine = None
