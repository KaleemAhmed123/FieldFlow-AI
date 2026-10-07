"""Shared in-memory DB (StaticPool so every session sees the same tables) + the fakes."""

from __future__ import annotations

import pytest
from app.db.models import Base
from app.graph.build import build_graph
from app.graph.checkpointer import make_checkpointer
from app.tools.inventory import FakeInventory
from app.tools.registry import build_toolbox
from app.tools.salesforce import FakeSalesforce
from app.tools.vonage import FakeVonage
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool


@pytest.fixture
async def sessionmaker():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


@pytest.fixture
def vonage() -> FakeVonage:
    return FakeVonage()


@pytest.fixture
def salesforce() -> FakeSalesforce:
    return FakeSalesforce()


@pytest.fixture
def inventory() -> FakeInventory:
    return FakeInventory()


@pytest.fixture
def toolbox(salesforce, inventory):
    """The controlled surface over the same fakes the test asserts on."""
    return build_toolbox(salesforce, inventory)


@pytest.fixture
def graph(toolbox, vonage):
    """Compiled graph over the Toolbox + Vonage, with a per-test checkpointer."""
    return build_graph(toolbox, vonage, checkpointer=make_checkpointer())
