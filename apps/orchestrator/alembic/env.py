"""Alembic environment — async, and scoped to OUR tables only.

Two things make this safe for FieldFlow:

1. The DB URL comes from `settings.database_url` (same source the app uses), so there's one
   source of truth and no secret committed here.
2. `include_object` restricts autogenerate to tables declared on our `Base`. The same Postgres
   also holds LangGraph's durable checkpoint tables (`checkpoints*`, created by `cp.setup()`) and
   the RAG `knowledge_chunks` (pgvector). Those are NOT ours — without this guard, `--autogenerate`
   would see them as "extra" and emit DROP TABLE, which would wipe every paused case. The guard
   makes Alembic ignore anything not on our Base.
"""

from __future__ import annotations

import asyncio

from alembic import context
from app.config import settings
from app.db.models import Base
from sqlalchemy.ext.asyncio import create_async_engine

config = context.config
target_metadata = Base.metadata

# The only tables Alembic is allowed to manage. Everything else in the DB (LangGraph checkpoints,
# pgvector knowledge_chunks) is owned by its own library and must be left untouched.
_OUR_TABLES = set(target_metadata.tables)


def include_object(obj, name, type_, reflected, compare_to):
    if type_ == "table" and name not in _OUR_TABLES:
        return False
    return True


def _do_run_migrations(connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        include_object=include_object,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_offline() -> None:
    context.configure(
        url=settings.database_url,
        target_metadata=target_metadata,
        include_object=include_object,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


async def _run_async() -> None:
    engine = create_async_engine(settings.database_url, future=True)
    async with engine.connect() as connection:
        await connection.run_sync(_do_run_migrations)
    await engine.dispose()


def run_migrations_online() -> None:
    asyncio.run(_run_async())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
