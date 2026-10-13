"""Build step 14 — the durable secret store that survives the SF refresh-token rotation.

Proven on the in-memory SQLite DB (the `sessionmaker` fixture), wired into the global the helpers
use. load → None, save → read back, and a second save upserts (no duplicate-key crash).
"""

from __future__ import annotations

import pytest
from app.db import session as db_session
from app.db.secrets import SF_REFRESH_TOKEN_KEY, load_secret, save_secret


@pytest.fixture
def _wire_db(sessionmaker, monkeypatch):
    # Point the helpers' global get_sessionmaker() at the test's in-memory DB.
    monkeypatch.setattr(db_session, "_sessionmaker", sessionmaker)


async def test_secret_roundtrip_and_upsert(_wire_db) -> None:
    assert await load_secret(SF_REFRESH_TOKEN_KEY) is None  # nothing stored yet
    await save_secret(SF_REFRESH_TOKEN_KEY, "rt-2")
    assert await load_secret(SF_REFRESH_TOKEN_KEY) == "rt-2"
    await save_secret(SF_REFRESH_TOKEN_KEY, "rt-3")  # same key again = update, not insert
    assert await load_secret(SF_REFRESH_TOKEN_KEY) == "rt-3"
