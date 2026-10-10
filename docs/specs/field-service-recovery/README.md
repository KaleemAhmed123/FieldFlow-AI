# FieldFlow AI — POC Spec Index

**Status:** In progress — backend through Steps 1–10 + 9c; Step 12 (MCP/observability) underway ·
**Started:** 2026-10-06 · **Last updated:** 2026-10-10

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
| [`testing-guide.md`](testing-guide.md) | How to learn the system by testing it: every test mapped to the promise it guards + 10 scoped tests to add. | You're a new/junior dev, or writing a test. |

## The raw source

The untouched original lives at [`../../poc_idea.md`](../../poc_idea.md). `idea.md` here is
the arranged copy — same content, readable.

## Locked decisions (from the interview)

1. **Problem:** field-service failure & appointment recovery (home services / appliance repair).
2. **Target:** Android + Google Messages + India (Vonage lists India for Android RCS).
3. **Agent type:** Transactional (Multi-use RCS agents aren't available in India).
4. **Cost:** ₹0 for the POC. RCS managed-account access is the one real dependency.
5. **Salesforce owns the service domain; inventory is a separate e-com source** (Decision A,
   2026-10-10 — product image + price + stock live in a real Node/Postgres e-com service, not in
   Salesforce). We build only a thin service-commerce layer. Proven engineering *patterns* are
   reused, not any other product's domain model.
6. **Two parallel tracks from day one**, built against a shared interface contract so neither
   side blocks the other.

## Build status (updated 2026-10-10)

Backend is deep: **Spine → 1 (policy+graph+NFR-4/5/6) → 2 (Toolbox) → §3 (reasons) → 4 (RAG, live) →
5 (LLM ladder, live) → 6 (commerce) → 9 (Razorpay) → 9b (Vonage RCS, LIVE-fired on a device
2026-10-09) → 7 (failure demos) → 9c (SF Pub/Sub trigger, mock-first) → 8 (React panel) → 10
(realistic catalog) → 13 (e-com inventory service: Next.js + Supabase + MCP, shipped 2026-10-11)**.
**Step 12** (real MCP + Logfire god-eye + reconciliation): Logfire + reconcile **shipped 2026-10-10**;
SF-MCP + copilot sequenced. **94 tests green, ruff clean.**

Per-step write-ups: `build-step-*.md`. Setup recipes: [`salesforce-handoff.md`](salesforce-handoff.md)
§8 (provision the org + the 3 `SF_*` trigger vars), [`hosted-mcp-setup.md`](hosted-mcp-setup.md) (Oct-2026
Hosted MCP steps), `../../apps/salesforce-apex/README.md` (deploy the Apex REST reads). Commands/run:
[`../../playbook.md`](../../playbook.md).

### Key decisions (2026-10-10)
- **Decision A** — inventory is a **separate e-com source** (product image+price+stock), not Salesforce;
  Salesforce owns the service domain only. E-com = a Node/Next.js service + admin dashboard, no storefront.
- **Make MCP real** — driven by an **admin copilot** (agentic chat over SF + e-com); pipeline stays
  deterministic (Apex REST + policy ladder); copilot writes human-confirmed. See `build-step-12`.
- **Deployment** — panel + e-com on **Vercel**, orchestrator on **Render** (health-pinged warm),
  Supabase + CloudAMQP managed.

Origin brainstorm (the "why" behind the 7-layer stack): [`../poc_idea.md`](../poc_idea.md).
