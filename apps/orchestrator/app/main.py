"""FastAPI entrypoint. The consumer runs inside this process (one deploy for the spine).

Flow proven here: sim publishes → RabbitMQ → this consumer → case_service → FakeVonage + Postgres
→ the panel reads /cases.
"""

from __future__ import annotations

import asyncio
import sys
from contextlib import asynccontextmanager

# Windows only: psycopg3's async driver (the Postgres checkpointer) refuses the default
# ProactorEventLoop. Select the SelectorEventLoop before uvicorn builds its loop. No-op on Linux,
# where this deploys. ponytail: selector loop caps at 512 sockets / no subprocess — fine for a POC.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fieldflow_contract import AppointmentAtRisk

from app.api.routes import router as api_router
from app.commerce import router as commerce_router
from app.commerce.razorpay import build_gateway
from app.commerce.service import CommerceService
from app.config import settings
from app.db.session import dispose_db, get_sessionmaker, init_db
from app.events import build_event_source
from app.graph.build import build_graph
from app.graph.checkpointer import checkpointer_scope
from app.llm.proposer import build_proposer
from app.logging import configure_logging, get_logger
from app.mcp import build_mcp_client
from app.queue.broker import Broker
from app.rag import make_knowledge_store
from app.services import case_service
from app.sim.routes import router as sim_router
from app.tools.inventory import build_inventory
from app.tools.registry import build_toolbox
from app.tools.salesforce import build_salesforce
from app.tools.vonage import build_vonage
from app.webhooks import router as webhooks_router

log = get_logger("main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging(settings.log_level)
    # Logfire — the god-eye view (Step 12). send_to_logfire='if-token-present' makes it a no-op
    # offline (tests, keyless dev) and stream live traces when LOGFIRE_TOKEN is set. Instruments
    # every FastAPI request. Wrapped so observability can never crash the app.
    try:
        import logfire

        logfire.configure(
            token=settings.logfire_token or None,
            send_to_logfire="if-token-present",
            service_name="fieldflow-orchestrator",
        )
        logfire.instrument_fastapi(app)
        log.info("logfire.configured", enabled=bool(settings.logfire_token))
    except Exception as exc:  # noqa: BLE001 — observability must never take the app down
        log.error("logfire.configure_failed", error=str(exc))
    await init_db()
    # Mockable tools + the compiled graph: built once so paused cases resume on the same
    # checkpointer. Swap the fakes / checkpointer for real ones in a later step.
    # Vonage RCS (Step 9b): real send is armed only when key+secret+agent_id+test_to are all set
    # (else FakeVonage) — the one swap line. Inbound/status taps arrive at /webhooks/* (real) or
    # /sim/* (offline twin); both resume the same case.
    app.state.vonage = build_vonage(settings)
    # Salesforce (Step 12): real Apex REST org when the client-credentials creds are set, else the
    # in-memory fake — the one swap line (like build_vonage). Reads live first; reschedule is gated.
    app.state.salesforce = build_salesforce(settings)
    # FakeInventory unless ECOM_API_URL is set, then the real e-com service (Decision A, step 13).
    app.state.inventory = build_inventory(settings)
    # Commerce (Step 6/9): the price authority + the payment gateway. build_gateway returns
    # FakeRazorpay unless a Razorpay TEST key is set (then the real Test-Mode gateway) — the one
    # swap line. A non-test key aborts the boot (POC is Test-Mode only).
    app.state.commerce = CommerceService(settings.commerce_labour_paise, settings.commerce_currency)
    app.state.razorpay = build_gateway(settings)
    # Hosted MCP client (Step 12 Task 4): the agentic copilot path. None unless SF_MCP_* + the
    # one-time refresh token are armed, so a keyless boot and tests are unaffected. (/copilot/tools)
    app.state.mcp = build_mcp_client(settings)
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
    # Durable checkpointer (Postgres on Supabase) so paused cases survive a restart; in-memory for
    # SQLite/offline. Opened here for the app's lifetime — the graph is built inside the scope so it
    # closes over the live saver, and setup() runs once before any case is processed.
    async with checkpointer_scope(settings) as checkpointer:
        app.state.graph = build_graph(
            app.state.toolbox, app.state.vonage, app.state.knowledge,
            checkpointer=checkpointer, retrieval_k=settings.retrieval_k,
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

        # The event SOURCE (Step 9c): a real Salesforce Pub/Sub subscriber when SF_* creds are
        # armed, else None so /sim stays the trigger. It publishes onto the SAME exchange —
        # downstream is unchanged. The one swap line for the trigger (like build_vonage).
        app.state.event_source = build_event_source(settings)
        source_task: asyncio.Task | None = None
        if app.state.event_source is not None and app.state.broker is not None:

            async def _publish_event(ev: AppointmentAtRisk) -> None:
                await app.state.broker.publish(ev.event, ev.model_dump(mode="json"))

            source_task = asyncio.create_task(app.state.event_source.run(_publish_event))
            log.info("event_source.started")

        yield

        if source_task is not None:
            await app.state.event_source.stop()
            source_task.cancel()
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
