"""The LangGraph checkpointer — where paused cases are stored so they can resume.

A case pauses for hours/days waiting on a human or a customer tap, so the paused state must be
*durable*: it has to survive a restart, a deploy, or a crash. Two savers behind one seam:

- **InMemorySaver** (`make_checkpointer`) — tests and keyless/offline runs. Zero infra, but lost on
  restart. Fine when there's no Postgres.
- **AsyncPostgresSaver** (`checkpointer_scope`) — the live app. Writes paused state to the Supabase
  Postgres we already run, next to the Case row. Survives restart and frees RAM (state lives in the
  DB, not the process). Chosen over Redis/Upstash: same wiring, but no extra service to stand up.

ponytail: no checkpoint retention/TTL yet — closed/expired cases keep their rows forever. Add a
periodic prune (delete checkpoints for CLOSED/REJECTED cases) when real volume lands, not before.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from langgraph.checkpoint.memory import InMemorySaver


def make_checkpointer():
    """In-memory saver for tests and offline runs. Paused cases are lost on restart."""
    return InMemorySaver()


def _psycopg_dsn(database_url: str) -> str:
    """LangGraph's Postgres saver talks psycopg3, not the SQLAlchemy/asyncpg driver the app DB uses.
    Strip the `+asyncpg`/`+psycopg` driver suffix and force TLS (Supabase requires it)."""
    dsn = database_url.replace("+asyncpg", "").replace("+psycopg", "")
    if "sslmode=" not in dsn:
        dsn += ("&" if "?" in dsn else "?") + "sslmode=require"
    return dsn


@asynccontextmanager
async def checkpointer_scope(settings):
    """Yield the checkpointer the app should use, open for the app's lifetime.

    Postgres when `database_url` is Postgres (the real app), else in-memory (SQLite/offline). The
    Postgres path opens one psycopg3 connection and runs `.setup()` once — idempotent DDL that
    creates LangGraph's checkpoint tables in Supabase if they're missing.
    """
    if not settings.database_url.startswith("postgres"):
        yield make_checkpointer()
        return

    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

    async with AsyncPostgresSaver.from_conn_string(_psycopg_dsn(settings.database_url)) as cp:
        await cp.setup()  # one-time, idempotent: creates the checkpoint tables if absent
        yield cp
