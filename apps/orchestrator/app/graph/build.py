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
from app.commerce.service import rupees
from app.config import settings
from app.llm.confidence import confidence_factors, score_confidence
from app.llm.proposer import Proposer, build_proposer
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


def _is_chargeable(state: GraphState, chosen: dict) -> bool:
    """Step-6 commerce trigger. A job is chargeable when the chosen option needs a part AND either
    the asset is out of active warranty OR the reason is a newly-found fault outside the original
    warranty scope (`additional_fault_found`). Warranty is the authority; no new event field."""
    if not chosen.get("partNo"):
        return False
    warranty = state["context"].get("asset", {}).get("warranty")
    reason = state["event"].get("reason", "")
    return warranty != "active" or reason == "additional_fault_found"


def _commerce_trace(state: GraphState, **extra: Any) -> dict:
    """Merge commerce facts into the running decision trace (quote/order/payment)."""
    decision = dict(state.get("decision", {}))
    commerce = dict(decision.get("commerce", {}))
    commerce.update(extra)
    decision["commerce"] = commerce
    return decision


class GraphState(TypedDict, total=False):
    event: dict[str, Any]
    context: dict[str, Any]
    knowledgeSources: list[dict[str, Any]]
    sla: dict[str, Any]
    candidates: list[dict[str, Any]]
    options: list[dict[str, Any]]
    toolsUsed: list[str]
    policy_result: dict[str, Any]
    archetype: str
    llm_confidence: float
    explanation: str
    llmProvider: str
    degraded: bool
    rateLimitNote: str | None
    confidence: float
    confidenceBreakdown: dict[str, Any]
    decision: dict[str, Any]
    card: dict[str, Any]
    sent: dict[str, Any]
    version: int
    approval: dict[str, Any]
    reply: dict[str, Any]
    executed: dict[str, Any]
    status: str
    note: str
    # Commerce (Step 6): the chosen chargeable part, the quote/order/payment-link, and the result.
    chosenPart: str
    quote: dict[str, Any]
    order: dict[str, Any]
    paymentLink: dict[str, Any]
    payment: dict[str, Any]
    captured: dict[str, Any]


def build_graph(
    toolbox: Toolbox,
    vonage: VonageClient,
    knowledge: KnowledgeStore,
    *,
    checkpointer,
    retrieval_k: int = 3,
    proposer: Proposer | None = None,
):
    """Compile the graph once, closing over the Toolbox + Vonage + KnowledgeStore (RAG) + the LLM
    proposer. Reused across start + resume. The proposer defaults to the deterministic-only ladder
    (fully offline) when none is injected, so tests and keyless runs never touch the network."""
    propose = proposer or build_proposer(settings, providers=[])

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
        # The LLM only *proposes* (Level-2). The proposer runs the ladder Groq -> Gemini ->
        # deterministic; whatever it returns is untrusted and re-validated by policy next.
        reason = state["event"].get("reason", "technician_delay")
        proposal = propose(reason, state["context"], state.get("knowledgeSources", []))
        candidates = proposal.options
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
        log.info("graph.generate_options", reason=reason, candidates=len(candidates),
                 provider=proposal.provider, degraded=proposal.degraded)
        return {"candidates": candidates, "context": context, "toolsUsed": tools_used,
                "archetype": proposal.archetype, "llm_confidence": proposal.llm_confidence,
                "explanation": proposal.explanation, "llmProvider": proposal.provider,
                "degraded": proposal.degraded, "rateLimitNote": proposal.rate_limit_note}

    def policy_validate(state: GraphState) -> GraphState:
        valid, result = policy.validate_options(state["candidates"], state["context"])
        # Evidence-weighted confidence: blended here (not in generate_options) because policy
        # headroom (APPROVED/PARTIAL/DENIED) is one of the five factors and is only known now.
        top_score = max((s.get("score", 0.0) for s in state.get("knowledgeSources", [])),
                        default=0.0)
        factors = confidence_factors(
            state.get("archetype", "delay"), result["policyResult"], top_score,
            state["context"], state.get("llm_confidence", 0.0), settings.conf_grounding_full,
        )
        final, breakdown = score_confidence(factors, settings.confidence_weights)
        decision = {
            "decision": "OFFER_RESCHEDULE",
            "reason": [
                f"event={state['event'].get('reason')}",
                f"policy={result['policyResult']}",
                *(f"removed {r['slotId']}: {r['reason']}" for r in result["removed"]),
            ],
            "knowledgeSources": state.get("knowledgeSources", []),
            "toolsUsed": state.get("toolsUsed", []),
            "confidence": final,
            "confidenceBreakdown": breakdown,
            "explanation": state.get("explanation"),
            "llmProvider": state.get("llmProvider"),
            "degraded": state.get("degraded", False),
            "rateLimitNote": state.get("rateLimitNote"),
            "policyResult": result["policyResult"],
            "removed": result["removed"],
        }
        log.info("graph.policy_validate", valid=len(valid), result=result["policyResult"],
                 confidence=round(final, 4))
        return {"options": valid, "policy_result": result, "confidence": final,
                "confidenceBreakdown": breakdown, "decision": decision}

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
        version = state.get("version", 0) + 1
        card = Card(kind="carousel", title="Your appointment needs a small adjustment",
                    options=opts, version=version)  # version → RCS postback (stale guard, NFR-6)
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
        # route_commerce: a chargeable repair (OQ2 rule) detours through quote → pay before verify.
        if _is_chargeable(state, chosen):
            return Command(goto="build_quote",
                           update={"executed": result, "status": "EXECUTED",
                                   "chosenPart": chosen["partNo"]})
        return Command(goto="verify", update={"executed": result, "status": "EXECUTED"})

    # --- Commerce branch (Step 6): quote → [human gate if high-value] → order+link → pay → settle.
    # Each money step is a MUTATION; the deterministic work (price authority, amount checks,
    # gateway) lives in the commerce.* action tools — the LLM still only proposed which part.
    def build_quote(state: GraphState) -> GraphState:
        part_no = state["chosenPart"]
        quote = toolbox.call("commerce.create_quote",
                             workOrderId=state["event"]["correlationId"], partNo=part_no).data
        tools_used = _add(state.get("toolsUsed", []), "commerce.create_quote")
        decision = _commerce_trace(state, quote=quote)
        decision["reason"] = [*decision.get("reason", []),
                              f"quote {rupees(quote['amountPaise'])} (authority: price_book)"]
        log.info("graph.build_quote", amountPaise=quote["amountPaise"])
        return {"quote": quote, "toolsUsed": tools_used, "decision": decision,
                "status": "QUOTE_BUILT"}

    def quote_approval(state: GraphState) -> GraphState:
        # Risk-tiering: a high-value quote pauses for an operator (Level-3); /sim/approve resumes.
        q = state["quote"]
        decision = interrupt({
            "type": "quote_approval", "quote": q, "amountPaise": q["amountPaise"],
            "note": f"high-value quote {rupees(q['amountPaise'])} needs approval",
        })
        return {"approval": decision}

    def create_payment(state: GraphState) -> GraphState:
        quote = state["quote"]
        order = toolbox.call("commerce.create_order", quote=quote).data
        link = toolbox.call("commerce.create_payment_link", orderId=order["orderId"],
                            amountPaise=order["amountPaise"], currency=order["currency"]).data
        tools_used = _add(state.get("toolsUsed", []),
                          "commerce.create_order", "commerce.create_payment_link")
        decision = _commerce_trace(state, order=order, paymentLink=link)
        log.info("graph.create_payment", orderId=order["orderId"])
        return {"order": order, "paymentLink": link, "toolsUsed": tools_used,
                "decision": decision, "status": "ORDER_CREATED"}

    def offer_payment(state: GraphState) -> GraphState:
        # One tap: the "Approve & Pay" card's button opens the Razorpay page (approve == pay).
        quote = state["quote"]
        card = Card(kind="payment", title=f"Approve & Pay {rupees(quote['amountPaise'])}",
                    payUrl=state["paymentLink"]["shortUrl"])
        version = state.get("version", 0) + 1
        sent = vonage.send_card(state["event"]["correlationId"], card)
        log.info("graph.offer_payment", amountPaise=quote["amountPaise"], version=version)
        return {"card": card.model_dump(), "sent": sent, "version": version,
                "status": "PAYMENT_PENDING"}

    def await_payment(state: GraphState) -> GraphState:
        # Interrupt and wait for the customer to complete payment (resumed via /sim/payment).
        pay = interrupt({"type": "await_payment", "orderId": state["order"]["orderId"],
                         "amountPaise": state["order"]["amountPaise"],
                         "payUrl": state["paymentLink"]["shortUrl"]})
        return {"payment": pay}

    def settle_payment(state: GraphState):
        pay = state["payment"]
        # Confirm through the gateway keyed by the payment-LINK id: the real gateway polls Razorpay
        # for the true status (no webhook); the fake honours the /sim-reported status. Idempotent →
        # no double-charge (NFR-2). A non-captured outcome re-offers the pay card.
        link_id = state["paymentLink"]["paymentLinkId"]
        res = toolbox.call("commerce.capture_payment", paymentRef=link_id,
                           amountPaise=state["order"]["amountPaise"],
                           reportedStatus=pay.get("status", "captured"))
        if not res.ok:
            log.info("graph.payment_failed", reason=res.reason)
            return Command(goto="offer_payment",
                           update={"note": f"payment not completed ({res.reason}); re-offered"})
        receipt = res.data
        decision = _commerce_trace(state, payment=receipt)
        log.info("graph.settle_payment", paymentRef=link_id,
                 alreadyCaptured=receipt.get("alreadyCaptured"))
        return Command(goto="verify",
                       update={"captured": receipt, "decision": decision, "status": "PAID"})

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
        ("execute", execute),
        ("build_quote", build_quote), ("quote_approval", quote_approval),
        ("create_payment", create_payment), ("offer_payment", offer_payment),
        ("await_payment", await_payment), ("settle_payment", settle_payment),
        ("verify", verify), ("close", close),
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
        if policy.needs_human_for(
            s["event"].get("reason", ""), s["confidence"], s["policy_result"],
            settings.always_human_set, settings.conf_threshold,
        ) else "offer_to_customer",
        {"human_approval": "human_approval", "offer_to_customer": "offer_to_customer"},
    )
    g.add_conditional_edges(
        "human_approval",
        lambda s: "offer_to_customer" if s.get("approval", {}).get("approved") else "close",
        {"offer_to_customer": "offer_to_customer", "close": "close"},
    )
    g.add_edge("offer_to_customer", "await_reply")
    g.add_edge("await_reply", "execute")
    # execute exits dynamically via Command(goto=...): verify | offer_to_customer |
    # generate_options | build_quote (chargeable, Step 6).
    # Commerce branch: high-value quotes pause for a human before any payment link is offered.
    g.add_conditional_edges(
        "build_quote",
        lambda s: "quote_approval"
        if s["quote"]["amountPaise"] >= settings.commerce_high_value_paise
        else "create_payment",
        {"quote_approval": "quote_approval", "create_payment": "create_payment"},
    )
    g.add_conditional_edges(
        "quote_approval",
        lambda s: "create_payment" if s.get("approval", {}).get("approved") else "close",
        {"create_payment": "create_payment", "close": "close"},
    )
    g.add_edge("create_payment", "offer_payment")
    g.add_edge("offer_payment", "await_payment")
    g.add_edge("await_payment", "settle_payment")
    # settle_payment exits dynamically via Command(goto=...): verify | offer_payment (retry).
    g.add_edge("verify", "close")
    g.add_edge("close", END)
    return g.compile(checkpointer=checkpointer)
