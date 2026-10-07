"""The LangGraph recovery graph. Spine = 2 nodes: load_case -> offer_options.

Real nodes (evaluate_sla, retrieve_knowledge, human_approval, execute, verify) land next; this
proves the orchestration layer is wired and resumable.
"""

from __future__ import annotations

from typing import Any, TypedDict

from fieldflow_contract import Card, SlotOption
from langgraph.graph import END, StateGraph

from app import policy
from app.logging import get_logger
from app.tools.salesforce import SalesforceTools

log = get_logger("graph")


class GraphState(TypedDict, total=False):
    event: dict[str, Any]
    context: dict[str, Any]
    options: list[dict[str, Any]]
    card: dict[str, Any]
    decision: dict[str, Any]


def build_graph(salesforce: SalesforceTools):
    """Compile a graph closing over the tools it needs."""

    def load_case(state: GraphState) -> GraphState:
        appt = state["event"]["appointmentId"]
        ctx = salesforce.get_context(appt)
        log.info("graph.load_case", appointmentId=appt)
        return {"context": ctx}

    def offer_options(state: GraphState) -> GraphState:
        ctx = state["context"]
        tech = ctx.get("technician", {}).get("name", "Technician")
        proposed = [
            SlotOption(slotId="t-today-1", label="TODAY 11:00-13:00", technician=tech,
                       note="Same technician"),
            SlotOption(slotId="t-tomorrow-1", label="TOMORROW 09:00-11:00", technician=tech,
                       note="Earlier slot"),
        ]
        valid, policy_result = policy.validate_options(proposed, ctx)
        card = Card(kind="carousel", title="Your appointment needs a small adjustment",
                    options=valid)
        decision = {
            "decision": "OFFER_RESCHEDULE",
            "reason": [f"reason={state['event'].get('reason')}", "policy approved"],
            "knowledgeSources": [],
            "toolsUsed": ["salesforce.get_context"],
            "confidence": 0.9,
            **policy_result,
        }
        log.info("graph.offer_options", options=len(valid))
        return {
            "options": [o.model_dump() for o in valid],
            "card": card.model_dump(),
            "decision": decision,
        }

    g = StateGraph(GraphState)
    g.add_node("load_case", load_case)
    g.add_node("offer_options", offer_options)
    g.set_entry_point("load_case")
    g.add_edge("load_case", "offer_options")
    g.add_edge("offer_options", END)
    return g.compile()
