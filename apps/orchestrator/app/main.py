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
from app.config import settings
from app.db.session import dispose_db, get_sessionmaker, init_db
from app.graph.build import build_graph
from app.graph.checkpointer import make_checkpointer
from app.logging import configure_logging, get_logger
from app.queue.broker import Broker
from app.services import case_service
from app.sim.routes import router as sim_router
from app.tools.inventory import FakeInventory
from app.tools.registry import build_toolbox
from app.tools.salesforce import FakeSalesforce
from app.tools.vonage import FakeVonage

log = get_logger("main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging(settings.log_level)
    await init_db()
    # Mockable tools + the compiled graph: built once so paused cases resume on the same
    # checkpointer. Swap the fakes / checkpointer for real ones in a later step.
    app.state.vonage = FakeVonage()
    app.state.salesforce = FakeSalesforce()
    app.state.inventory = FakeInventory()
    # The Toolbox is the controlled MCP-shaped surface over the fakes; the graph only ever calls
    # tools through it. Swapping in a real MCP client later touches only this line.
    app.state.toolbox = build_toolbox(app.state.salesforce, app.state.inventory)
    app.state.graph = build_graph(
        app.state.toolbox, app.state.vonage, checkpointer=make_checkpointer(),
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
