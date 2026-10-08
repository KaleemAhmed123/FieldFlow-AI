"""FastAPI entrypoint. The consumer runs inside this process (one deploy for the spine).

Flow proven here: sim publishes → RabbitMQ → this consumer → case_service → FakeVonage + Postgres
→ the panel reads /cases.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fieldflow_contract import AppointmentAtRisk

from app.api.routes import router as api_router
from app.commerce import router as commerce_router
from app.commerce.razorpay import build_gateway
from app.commerce.service import CommerceService
from app.config import settings
from app.db.session import dispose_db, get_sessionmaker, init_db
from app.graph.build import build_graph
from app.graph.checkpointer import make_checkpointer
from app.llm.proposer import build_proposer
from app.logging import configure_logging, get_logger
from app.queue.broker import Broker
from app.rag import make_knowledge_store
from app.services import case_service
from app.sim.routes import router as sim_router
from app.tools.inventory import FakeInventory
from app.tools.registry import build_toolbox
from app.tools.salesforce import FakeSalesforce
from app.tools.vonage import build_vonage
from app.webhooks import router as webhooks_router

log = get_logger("main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging(settings.log_level)
    await init_db()
    # Mockable tools + the compiled graph: built once so paused cases resume on the same
    # checkpointer. Swap the fakes / checkpointer for real ones in a later step.
    # Vonage RCS (Step 9b): real send is armed only when key+secret+agent_id+test_to are all set
    # (else FakeVonage) — the one swap line. Inbound/status taps arrive at /webhooks/* (real) or
    # /sim/* (offline twin); both resume the same case.
    app.state.vonage = build_vonage(settings)
    app.state.salesforce = FakeSalesforce()
    app.state.inventory = FakeInventory()
    # Commerce (Step 6/9): the price authority + the payment gateway. build_gateway returns
    # FakeRazorpay unless a Razorpay TEST key is set (then the real Test-Mode gateway) — the one
    # swap line. A non-test key aborts the boot (POC is Test-Mode only).
    app.state.commerce = CommerceService(settings.commerce_labour_paise, settings.commerce_currency)
    app.state.razorpay = build_gateway(settings)
    # The Toolbox is the controlled MCP-shaped surface over the fakes; the graph only ever calls
    # tools through it. Swapping in a real MCP client later touches only this line.
    app.state.toolbox = build_toolbox(
        app.state.salesforce, app.state.inventory, app.state.commerce, app.state.razorpay,
    )
    # RAG store (real Jina+pgvector if a key is set, else the in-memory fake). The graph reads it
    # through the KnowledgeStore seam, so this is the only line that changes when creds land.
    app.state.knowledge = make_knowledge_store(settings)
    # The LLM proposer ladder (Groq -> Gemini -> deterministic). Built from settings: a provider is
    # only live if its key is set, so a keyless boot runs the deterministic proposer offline.
    app.state.proposer = build_proposer(settings)
    app.state.graph = build_graph(
        app.state.toolbox, app.state.vonage, app.state.knowledge,
        checkpointer=make_checkpointer(), retrieval_k=settings.retrieval_k,
        proposer=app.state.proposer,
    )

    async def handle(routing_key: str, body: dict) -> None:
        if body.get("event") == "appointment.at_risk":
            event = AppointmentAtRisk(**body)
            async with get_sessionmaker()() as session:
                await case_service.handle_event(session, event, graph=app.state.graph)
        else:
            log.info("event.ignored", routing_key=routing_key)

    broker = Broker(settings.rabbitmq_url)
    try:
        await broker.connect()
        await broker.start_consuming(handle)
        app.state.broker = broker
    except Exception as exc:  # noqa: BLE001 — allow the API to run even if RabbitMQ is down
        log.error("broker.unavailable", error=str(exc))
        app.state.broker = None

    yield

    if app.state.broker is not None:
        await broker.close()
    await dispose_db()


app = FastAPI(title="FieldFlow AI — Orchestrator", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.panel_origin],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(api_router)
app.include_router(sim_router)
app.include_router(commerce_router)
app.include_router(webhooks_router)
