"""Durable key/value for runtime-rotating secrets (build step 14).

Only the Salesforce Hosted-MCP refresh token lives here today: its ECA forces rotation, so the value
in the env goes stale after the first refresh. We persist the latest so a restart recovers it.
Portable upsert (get-then-set) so the same code runs on Postgres and the SQLite test DB.
"""

from __future__ import annotations

from app.db.models import AppSecret
from app.db.session import get_sessionmaker

SF_REFRESH_TOKEN_KEY = "sf_mcp_refresh_token"


async def load_secret(key: str) -> str | None:
    """The stored value, or None if nothing has been persisted yet."""
    async with get_sessionmaker()() as session:
        obj = await session.get(AppSecret, key)
        return obj.value if obj else None


async def save_secret(key: str, value: str) -> None:
    """Upsert the value (insert or update), portable across Postgres + SQLite."""
    async with get_sessionmaker()() as session:
        obj = await session.get(AppSecret, key)
        if obj is None:
            session.add(AppSecret(key=key, value=value))
        else:
            obj.value = value
        await session.commit()
