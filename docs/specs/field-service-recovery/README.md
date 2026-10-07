# FieldFlow AI — POC Spec Index

**Status:** In progress — walking-skeleton spine built · **Started:** 2026-10-06 · **Last updated:** 2026-10-07

## One-line pitch

An AI field-service recovery system. When a home-service / appliance-repair appointment
goes wrong, FieldFlow AI detects it, reasons over enterprise context, validates options
against hard business rules, and lets the customer fix it through **RCS** — then executes
the real changes across Salesforce, inventory, commerce and payment.

> RCS is the customer's **control plane**, not a notification channel.

## The documents

| Doc | What it is | Read it when |
|-----|-----------|--------------|
| [`idea.md`](idea.md) | The full research, arranged. Nothing deleted. Your prompts kept inline. | You want the original thinking and the "why". |
| [`srs.md`](srs.md) | Software Requirements Spec. Problem, scope, the 13-stage journey as functional requirements, the 6 failure modes as reliability requirements, per-layer tech justification. | You're building, or showing Vonage what we're building. |
| [`risks.md`](risks.md) | Risk & friction register (severity · mitigation · owner) + a short SDLC phase map. | You want to know what can block us and in what order. |
| [`roles.md`](roles.md) | Who builds what (not a wall), the Field Service setup checklist, and the **interface contract** both sides build against. | You're splitting work with the Salesforce dev. |
| [`context/`](context/) | Project-context folder (7 dense, numbered files): the shared mental model of the system — overview, domain, orchestration, RAG+MCP, RCS, reliability, principles. | You want the dense "how it all fits" map. |
| [`diagrams/`](diagrams/) | 3 rich Excalidraw diagrams: system architecture, customer journey, decision/authority flow. | You're presenting to your manager / Vonage. |

## The raw source

The untouched original lives at [`../../poc_idea.md`](../../poc_idea.md). `idea.md` here is
the arranged copy — same content, readable.

## Locked decisions (from the interview)

1. **Problem:** field-service failure & appointment recovery (home services / appliance repair).
2. **Target:** Android + Google Messages + India (Vonage lists India for Android RCS).
3. **Agent type:** Transactional (Multi-use RCS agents aren't available in India).
4. **Cost:** ₹0 for the POC. RCS managed-account access is the one real dependency.
5. **Salesforce owns the domain** (Field Service + inventory). We build only a thin
   service-commerce layer. Proven engineering *patterns* are reused, not any other product's domain model.
6. **Two parallel tracks from day one**, built against a shared interface contract so neither
   side blocks the other.

## Build status

Context docs, diagrams and the scaffold are **done**. The walking-skeleton **spine runs**
(event → queue → idempotency → LangGraph → fake card → DB → panel; tests green). Next up is the
real policy engine + full LangGraph nodes — see [`scaffold.md`](scaffold.md) and
[`build-step-1.md`](build-step-1.md).
