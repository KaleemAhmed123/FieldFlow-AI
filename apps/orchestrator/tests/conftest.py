"""Shared in-memory DB (StaticPool so every session sees the same tables) + the fakes."""

from __future__ import annotations

from pathlib import Path

import pytest
from app.commerce.razorpay import FakeRazorpay
from app.commerce.service import CommerceService
from app.config import settings
from app.db.models import Base
from app.graph.build import build_graph
from app.graph.checkpointer import make_checkpointer
from app.rag.ingest import ingest_dir
from app.rag.store import FakeKnowledgeStore
from app.tools.inventory import FakeInventory
from app.tools.registry import build_toolbox
from app.tools.salesforce import FakeSalesforce
from app.tools.vonage import FakeVonage
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

CORPUS = Path(__file__).resolve().parent.parent / "app" / "rag" / "corpus"


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
def razorpay() -> FakeRazorpay:
    return FakeRazorpay()


@pytest.fixture
def commerce() -> CommerceService:
    return CommerceService(settings.commerce_labour_paise, settings.commerce_currency)


@pytest.fixture
def toolbox(salesforce, inventory, commerce, razorpay):
    """The controlled surface over the same fakes the test asserts on (incl. commerce.*, Step 6)."""
    return build_toolbox(salesforce, inventory, commerce, razorpay)


@pytest.fixture
def knowledge() -> FakeKnowledgeStore:
    """In-memory knowledge store, ingested from the generated corpus (deterministic embedder)."""
    store = FakeKnowledgeStore()
    ingest_dir(store, CORPUS)
    return store


@pytest.fixture
def graph(toolbox, vonage, knowledge):
    """Compiled graph over the Toolbox + Vonage + knowledge store, with a per-test checkpointer."""
    return build_graph(toolbox, vonage, knowledge, checkpointer=make_checkpointer())
