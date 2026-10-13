#!/usr/bin/env python
"""Reset the orchestrator's OWN state for a clean demo slate — touches NOTHING in Salesforce/e-com.

Clears the case history (cases, audit, decisions, idempotency) + the paused-graph checkpoints, and
purges the RabbitMQ dead-letter queue (the parked failed events). KEEPS `app_secrets` (the rotated
Salesforce MCP refresh token) so the admin copilot survives the reset.

Destructive: a bare run only REPORTS what it would delete; pass --yes to actually wipe.

Run (from apps/orchestrator, reads .env):
    uv run python scripts/reset_state.py          # dry run — counts only
    uv run python scripts/reset_state.py --yes    # actually wipe
"""

from __future__ import annotations

import asyncio
import sys

# Windows: psycopg3 async needs the SelectorEventLoop (as app/main.py). No-op on Linux.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from app.config import settings  # noqa: E402
from sqlalchemy import text  # noqa: E402 — after the Windows loop policy, before use
from sqlalchemy.ext.asyncio import create_async_engine  # noqa: E402

# Case state we own. app_secrets is deliberately NOT here (keeps the SF refresh token).
_CASE_TABLES = ["cases", "idempotency_keys", "audit_log", "ai_decisions"]
# LangGraph durable-checkpointer tables (Postgres only; absent on SQLite/offline). children first.
# checkpoint_migrations (schema-version marker) is left alone.
_CHECKPOINT_TABLES = ["checkpoint_writes", "checkpoint_blobs", "checkpoints"]


async def _wipe_db(apply: bool) -> None:
    engine = create_async_engine(settings.database_url, future=True)
    try:
        for table in _CASE_TABLES + _CHECKPOINT_TABLES:
            async with engine.begin() as conn:  # per-table tx: a missing one won't abort the rest
                try:
                    n = (await conn.execute(text(f"SELECT count(*) FROM {table}"))).scalar_one()
                except Exception as exc:  # noqa: BLE001 — table may not exist (SQLite/offline)
                    print(f"  skip        {table:<22} (absent: {type(exc).__name__})")
                    continue
                if apply:
                    await conn.execute(text(f"DELETE FROM {table}"))
                print(f"  {'wiped' if apply else 'would wipe':<11} {table:<22} ({n} rows)")
    finally:
        await engine.dispose()


async def _purge_dlq(apply: bool) -> None:
    try:
        import aio_pika
    except ImportError:
        print("  skip        DLQ purge (aio_pika not installed)")
        return
    try:
        conn = await aio_pika.connect_robust(settings.rabbitmq_url, timeout=10)
    except Exception as exc:  # noqa: BLE001 — broker down / not configured
        print(f"  skip        DLQ purge (broker unreachable: {type(exc).__name__})")
        return
    try:
        for q in ("events.dlq", "events"):
            channel = await conn.channel()  # fresh channel: a passive-declare miss closes it
            try:
                queue = await channel.declare_queue(q, durable=True, passive=True)
                depth = queue.declaration_result.message_count
                if apply:
                    await queue.purge()
                print(f"  {'purged' if apply else 'would purge':<11} {q:<22} ({depth} msgs)")
            except Exception as exc:  # noqa: BLE001 — queue may not exist yet
                print(f"  skip        {q:<22} (absent: {type(exc).__name__})")
            finally:
                await channel.close()
    finally:
        await conn.close()


async def main() -> None:
    apply = "--yes" in sys.argv
    where = settings.database_url.rsplit("@", 1)[-1]  # hide creds in the printout
    print(f"{'APPLYING reset' if apply else 'DRY RUN (pass --yes to apply)'}  ->  {where}\n")
    print("Postgres (keeps app_secrets):")
    await _wipe_db(apply)
    print("\nRabbitMQ:")
    await _purge_dlq(apply)
    print("\nDone." if apply else "\nNo changes made - re-run with --yes to apply.")


if __name__ == "__main__":
    asyncio.run(main())
