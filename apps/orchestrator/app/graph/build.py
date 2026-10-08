"""The LangGraph recovery graph — the decision core.

Flow:
  load_case -> load_context -> retrieve_knowledge -> evaluate_sla
    -> generate_options -> policy_validate
    policy_validate --(auto-safe)----------> offer_to_customer
    policy_validate --(risky/low-conf)-----> human_approval (interrupt; Level-3, NFR-4)
    human_approval  --(approved)-----------> offer_to_customer
    human_approval  --(rejected)-----------> close
  offer_to_customer -> await_reply (interrupt; wait for the customer tap)
  await_reply -> execute
    execute --(stale reply, NFR-6)---------> offer_to_customer  (re-send current options)
    execute --(reserve lost the race, NFR-5)-> generate_options (recompute, re-offer)
    execute --(ok)-------------------------> verify -> close

The LLM only ever *proposes* (generate_options). Every removal and the confidence gate are the
deterministic policy engine's call. External effects go through the Toolbox (read tools compose
context; action tools run the authority ladder and may refuse) and the Vonage adapter; DB
persistence lives in the service layer so nodes stay pure and testable.
"""

from __future__ import annotations

from typing import Any, TypedDict

from fieldflow_contract import Card, SlotOption
from langgraph.graph import END, StateGraph
from langgraph.types import Command, interrupt

from app import policy
from app.logging import get_logger
from app.rag.store import KnowledgeStore
from app.tools.registry import Toolbox
from app.tools.vonage import VonageClient

log = get_logger("graph")

# Granular read tools composed into the case context (recorded as real toolsUsed).
_CONTEXT_READS = [
    "salesforce.get_appointment", "salesforce.get_customer",
    "salesforce.get_asset", "salesforce.get_technician",
]


def _add(used: list[str], *names: str) -> list[str]:
    """Append tool names, order-preserving + unique (generate_options may run twice on NFR-5)."""
    out = list(used)
    for n in names:
        if n not in out:
            out.append(n)
    return out

# Ten realistic at-risk reasons collapse to three behaviour archetypes. Only the archetype drives
# the proposer + confidence; the extra labels are demo variety (a real SF event carries any).
REASON_ARCHETYPE = {
    "technician_delay": "delay", "traffic_weather": "delay",
    "technician_no_show": "delay", "customer_access_issue": "delay",
    "part_missing": "parts", "wrong_part_shipped": "parts", "additional_fault_found": "parts",
    "asset_complex": "complex", "safety_risk": "complex", "warranty_dispute": "complex",
}
# Mock stand-in for the LLM's self-reported confidence (Groq lands in a later step). `complex`
# sits below the 0.7 policy threshold, so it routes to human approval (NFR-4).
CONFIDENCE_BY_ARCHETYPE = {"delay": 0.9, "parts": 0.8, "complex": 0.5}


class GraphState(TypedDict, total=False):
    event: dict[str, Any]
    context: dict[str, Any]
    knowledgeSources: list[dict[str, Any]]
    sla: dict[str, Any]
    candidates: list[dict[str, Any]]
    options: list[dict[str, Any]]
    toolsUsed: list[str]
    policy_result: dict[str, Any]
    confidence: float
    decision: dict[str, Any]
    card: dict[str, Any]
    sent: dict[str, Any]
    version: int
    approval: dict[str, Any]
    reply: dict[str, Any]
    executed: dict[str, Any]
    status: str
    note: str


def _propose(reason: str, context: dict) -> tuple[list[dict], float]:
    """The mock proposer (LLM seam). Deterministic candidates + confidence, per archetype."""
    tech = context.get("technician", {}).get("name", "Technician")
    skill = (context.get("technician", {}).get("skills") or [None])[0]
    archetype = REASON_ARCHETYPE.get(reason, "delay")
    confidence = CONFIDENCE_BY_ARCHETYPE[archetype]

    if archetype == "parts":
        # One slot needs the scarce part; one swaps in a loaner and needs none. If the part is
        # lost to the race (NFR-5), the part slot drops out and the loaner slot still stands.
        candidates = [
            {"slotId": "t-part-1", "label": "TODAY 15:00-17:00", "technician": tech,
             "note": "After part fitted", "requiredSkill": skill, "partNo": "CAP-492"},
            {"slotId": "t-swap-1", "label": "TOMORROW 10:00-12:00", "technician": tech,
             "note": "Loaner unit, no part needed", "requiredSkill": skill},
        ]
        return candidates, confidence

    # delay / complex: two reschedule slots with the same technician (complex just scores lower
    # confidence, so policy sends it to a human — NFR-4).
    candidates = [
        {"slotId": "t-today-1", "label": "TODAY 11:00-13:00", "technician": tech,
         "note": "Same technician", "requiredSkill": skill},
        {"slotId": "t-tomorrow-1", "label": "TOMORROW 09:00-11:00", "technician": tech,
         "note": "Earlier slot", "requiredSkill": skill},
    ]
    return candidates, confidence


def build_graph(
    toolbox: Toolbox,
    vonage: VonageClient,
    knowledge: KnowledgeStore,
    *,
    checkpointer,
    retrieval_k: int = 3,
):
    """Compile the graph once, closing over the Toolbox + Vonage + KnowledgeStore (RAG). Reused
    across start + resume."""

    def load_case(state: GraphState) -> GraphState:
        log.info("graph.load_case", appointmentId=state["event"].get("appointmentId"))
        return {"status": "LOADING"}

    def retrieve_knowledge(state: GraphState) -> GraphState:
        # RAG (Level-2 grounding): fetch the most relevant manual/warranty/SOP passages for this
        # asset + reason and attach them as cited knowledgeSources. Read-only — never mutates. A
        # retrieval failure must NOT break the decision, so it degrades to no sources.
        ctx = state["context"]
        model = ctx.get("asset", {}).get("model", "")
        reason = state["event"].get("reason", "")
        query = f"{model} {reason} repair warranty part fault".strip()
        try:
            hits = knowledge.retrieve(query, retrieval_k)
        except Exception as exc:  # noqa: BLE001 — knowledge must not break the decision (R9)
            log.error("graph.retrieve_knowledge.failed", error=str(exc))
            return {"knowledgeSources": []}
        sources = [
            {
                "source": h.chunk.metadata.get("source"),
                "locator": h.chunk.metadata.get("locator"),
                "link": h.chunk.metadata.get("link"),
                "score": round(h.score, 4),
                "snippet": h.chunk.text[:160].replace("\n", " "),
            }
            for h in hits
        ]
        log.info("graph.retrieve_knowledge", query=query, sources=len(sources))
        return {"knowledgeSources": sources}

    def load_context(state: GraphState) -> GraphState:
        # Compose the case context from granular read tools (SOC). Each call is recorded, so the
        # decision trace's toolsUsed is real — "show your work", not a hard-coded list.
        appt = toolbox.call("salesforce.get_appointment",
                            appointmentId=state["event"]["appointmentId"]).data
        customer = toolbox.call("salesforce.get_customer", customerId=appt["customerId"]).data
        asset = toolbox.call("salesforce.get_asset", assetId=appt["assetId"]).data
        tech = toolbox.call("salesforce.get_technician", resourceId=appt["resourceId"]).data
        ctx = {
            "appointmentId": appt["appointmentId"],
            "customer": customer,
            "asset": asset,
            "technician": tech,
            "slaWindowMinutes": appt["slaWindowMinutes"],
            "caseState": appt["caseState"],
        }
        return {"context": ctx, "toolsUsed": list(_CONTEXT_READS)}

    def evaluate_sla(state: GraphState) -> GraphState:
        window = state["context"].get("slaWindowMinutes")
        delay = state["event"].get("detail", {}).get("delayMinutes", 0)
        breached = window is not None and delay > window
        return {"sla": {"windowMinutes": window, "delayMinutes": delay, "breached": breached}}

    def generate_options(state: GraphState) -> GraphState:
        reason = state["event"].get("reason", "technician_delay")
        candidates, confidence = _propose(reason, state["context"])
        # Fresh inventory snapshot every pass via the read tool, so a recompute after a lost race
        # sees the new stock. Record find_part as a real tool use when any candidate needs a part.
        part_nos = {c["partNo"] for c in candidates if c.get("partNo")}
        inv = {
            pn: sum(loc["qty"] for loc in toolbox.call("inventory.find_part", partNo=pn).data)
            for pn in part_nos
        }
        context = {**state["context"], "inventory": inv}
        tools_used = _add(state.get("toolsUsed", []), "inventory.find_part") if part_nos \
            else state.get("toolsUsed", [])
        log.info("graph.generate_options", reason=reason, candidates=len(candidates))
        return {"candidates": candidates, "confidence": confidence, "context": context,
                "toolsUsed": tools_used}

    def policy_validate(state: GraphState) -> GraphState:
        valid, result = policy.validate_options(state["candidates"], state["context"])
        decision = {
            "decision": "OFFER_RESCHEDULE",
            "reason": [
                f"event={state['event'].get('reason')}",
                f"policy={result['policyResult']}",
                *(f"removed {r['slotId']}: {r['reason']}" for r in result["removed"]),
            ],
            "knowledgeSources": state.get("knowledgeSources", []),
            "toolsUsed": state.get("toolsUsed", []),
            "confidence": state["confidence"],
            "policyResult": result["policyResult"],
            "removed": result["removed"],
        }
        log.info("graph.policy_validate", valid=len(valid), result=result["policyResult"])
        return {"options": valid, "policy_result": result, "decision": decision}

    def human_approval(state: GraphState) -> GraphState:
        # Level-3 interrupt (NFR-4): persist and wait for an operator decision.
        decision = interrupt({
            "type": "approval_request",
            "options": state["options"],
            "confidence": state["confidence"],
            "policyResult": state["policy_result"]["policyResult"],
        })
        return {"approval": decision}

    def offer_to_customer(state: GraphState) -> GraphState:
        opts = [
            SlotOption(slotId=c["slotId"], label=c["label"], technician=c["technician"],
                       note=c.get("note", ""))
            for c in state["options"]
        ]
        card = Card(kind="carousel", title="Your appointment needs a small adjustment",
                    options=opts)
        version = state.get("version", 0) + 1
        sent = vonage.send_card(state["event"]["correlationId"], card)
        log.info("graph.offer_to_customer", options=len(opts), version=version)
        return {"card": card.model_dump(), "sent": sent, "version": version,
                "status": "OPTIONS_SENT"}

    def await_reply(state: GraphState) -> GraphState:
        # Interrupt and wait for the customer's tap, tagged with the version they were shown.
        reply = interrupt({"type": "await_reply", "version": state["version"],
                           "options": state["options"]})
        return {"reply": reply}

    def execute(state: GraphState):
        reply = state["reply"]
        # NFR-6: a reply against a stale version is rejected; re-send the current options.
        if reply.get("version") != state.get("version"):
            log.info("graph.stale_reply", got=reply.get("version"), current=state.get("version"))
            return Command(goto="offer_to_customer",
                           update={"note": "stale reply rejected; current options re-sent"})

        chosen = next((c for c in state["options"] if c["slotId"] == reply.get("slotId")), None)
        if chosen is None:
            return Command(goto="offer_to_customer",
                           update={"note": f"unknown slot {reply.get('slotId')}; re-offered"})

        # NFR-5: atomic reserve through the action tool. The tool runs the ladder and decides;
        # a refusal (part taken since we offered it) → recompute + re-offer.
        part = chosen.get("partNo")
        if part:
            reserved = toolbox.call("inventory.reserve", partNo=part, qty=1)
            if not reserved.ok:
                log.info("graph.reserve_failed", partNo=part, reason=reserved.reason)
                return Command(goto="generate_options",
                               update={"note": f"part {part} unavailable; options recomputed"})

        # reschedule.confirm: an action tool; runs the ladder, may refuse (unknown/terminal case).
        confirmed = toolbox.call("reschedule.confirm",
                                 appointmentId=state["event"]["appointmentId"],
                                 slotId=chosen["slotId"])
        if not confirmed.ok:
            log.info("graph.reschedule_refused", reason=confirmed.reason)
            return Command(goto="offer_to_customer",
                           update={"note": f"reschedule refused: {confirmed.reason}; re-offered"})
        result = confirmed.data
        log.info("graph.execute", slotId=chosen["slotId"])
        # All exits from execute are dynamic (Command), so the superstep schedules exactly one
        # next node — no static edge, which would double-fire and clash on the `status` channel.
        return Command(goto="verify", update={"executed": result, "status": "EXECUTED"})

    def verify(state: GraphState) -> GraphState:
        return {"status": "VERIFIED"}

    def close(state: GraphState) -> GraphState:
        if state.get("approval") and not state["approval"].get("approved"):
            return {"status": "REJECTED"}
        return {"status": "CLOSED"}

    g = StateGraph(GraphState)
    for name, fn in [
        ("load_case", load_case), ("load_context", load_context),
        ("retrieve_knowledge", retrieve_knowledge),
        ("evaluate_sla", evaluate_sla), ("generate_options", generate_options),
        ("policy_validate", policy_validate), ("human_approval", human_approval),
        ("offer_to_customer", offer_to_customer), ("await_reply", await_reply),
        ("execute", execute), ("verify", verify), ("close", close),
    ]:
        g.add_node(name, fn)

    g.set_entry_point("load_case")
    g.add_edge("load_case", "load_context")
    g.add_edge("load_context", "retrieve_knowledge")
    g.add_edge("retrieve_knowledge", "evaluate_sla")
    g.add_edge("evaluate_sla", "generate_options")
    g.add_edge("generate_options", "policy_validate")
    g.add_conditional_edges(
        "policy_validate",
        lambda s: "human_approval"
        if policy.needs_human(s["confidence"], s["policy_result"]) else "offer_to_customer",
        {"human_approval": "human_approval", "offer_to_customer": "offer_to_customer"},
    )
    g.add_conditional_edges(
        "human_approval",
        lambda s: "offer_to_customer" if s.get("approval", {}).get("approved") else "close",
        {"offer_to_customer": "offer_to_customer", "close": "close"},
    )
    g.add_edge("offer_to_customer", "await_reply")
    g.add_edge("await_reply", "execute")
    # execute exits dynamically via Command(goto=...): verify | offer_to_customer | generate_options
    g.add_edge("verify", "close")
    g.add_edge("close", END)
    return g.compile(checkpointer=checkpointer)
