# FieldFlow AI — Risk & Friction Register

**Status:** Planning · **Started:** 2026-10-06 · **Last updated:** 2026-10-06

This is the "what can bite us, and when" doc. It is the risk register you asked for, plus a
short SDLC phase map so each risk is tied to the phase where it actually hurts.

> **Owners:** *You* = project lead, AI + RCS + orchestration, hands-on on Salesforce APIs/MCP.
> *SF Dev* = Salesforce Field Service + commerce execution. *Both* = shared/integration work.
> (Full split in [`roles.md`](roles.md).)

---

## 1. Short SDLC phase map

A lightweight phase view — not a committed timeline (no fixed date yet), just the logical order
and where the biggest risks land.

| Phase | What happens | Biggest risk here |
|-------|--------------|-------------------|
| **P0 · Access & setup** | Clear Vonage RCS access; stand up Field Service DE; local Docker infra. | R1, R3 — the two things most likely to stall everything. |
| **P1 · Contract & stubs** | Agree the interface contract (events + MCP tools); both sides build against mocks. | R12 — contract drift if skipped. |
| **P2 · Happy path** | One appointment recovered end-to-end over RCS, data real. | R6, R9 — RCS rendering, AI latency. |
| **P3 · Enterprise depth** | Real Salesforce Pub/Sub events, inventory reserve, commerce + Razorpay. | R7 — payment-is-not-in-RCS nuance. |
| **P4 · Reliability demos** | The 6 failure scenarios made triggerable and correct. | R8 — webhook reachability under failover. |
| **P5 · Showcase polish** | Demo control panel, observability dashboards, PDF report, demo script. | R10 — demo-day device/data surprises. |

**Entry/exit rule of thumb:** a phase is "done" when its risk above is either retired or has a
working mitigation demonstrated, not just planned.

## 2. Risk & friction register

Severity: 🔴 high (can block the POC) · 🟠 medium (slows us / needs a workaround) · 🟡 low
(annoyance, plan around it).

| # | Risk / friction | Sev | Why it matters | Mitigation | Owner | Phase |
|---|-----------------|-----|----------------|------------|-------|-------|
| **R1** | Vonage RCS needs a **managed account + Developer Mode** activated by an account manager | 🔴 | No live RCS until this clears; it's the one thing we can't self-serve. | Raise with the Vonage partner contact **first**, before any code. Until cleared, build against a mocked Vonage adapter. | You | P0 |
| **R2** | RCS in India is **Android-only** (no iOS in Vonage coverage) | 🟠 | A demo on an iPhone would silently fail. | Fix the official target: **Android + Google Messages + Indian test number**. State it in the demo script. | You | P0 |
| **R3** | Generic Salesforce DE ≠ **Field Service DE** | 🔴 | A normal Developer Edition is missing Field Service objects/sample data; hours lost configuring the wrong org. | Sign up for the **special Field Service-enabled Developer Edition** with the managed package + sample data. | SF Dev | P0 |
| **R4** | RCS agent config has **irreversible choices** (use case, billing category) | 🟠 | Picking wrong means re-creating the agent. | Decide up front: **Transactional** use case. Document the full agent-config checklist before creating it. | You | P0 |
| **R5** | **Multi-use RCS agents unavailable in India** | 🟡 | Can't mix promotional + transactional. | None needed — our agent is Transactional by design. Actually simplifies the build. | You | P0 |
| **R6** | **Rich-card rendering varies** by device/client | 🟠 | Cards may look different or drop features on some phones. | Test on the real target device early; don't rely on untested primitives in the demo. | You | P2 |
| **R7** | **Payment is not inside RCS** — it's Open-URL → webview → Razorpay | 🟠 | Easy to mis-sell as "pay in RCS"; also a real integration seam (webhook back from Razorpay). | Show the webview flow honestly in the architecture. Wire Razorpay Test-Mode webhook → RabbitMQ → order state. | You | P3 |
| **R8** | **Public webhook** — Vonage/Razorpay must reach localhost | 🟠 | Local dev isn't publicly reachable; webhooks silently fail. | **Cloudflare Quick Tunnel** (no account/domain). Re-check the URL each session; it rotates. | You | P1 |
| **R9** | **AI can be the slowest component** | 🟠 | LLM→LLM→LLM chains make RCS feel laggy and unimpressive. | Bound AI to **one decision call + one retrieval + one response generation**; everything else deterministic. | You | P2 |
| **R10** | **Real customer data** leaking into the demo | 🟡 | Privacy/compliance exposure for zero benefit. | **Fake everything** — customers, addresses, assets, work orders, phone numbers, amounts. | Both | P5 |
| **R11** | **Platform onboarding, not coding, is the real timesink** | 🟠 | Effort estimates assume access exists; it often doesn't yet. | Front-load R1 + R3 in P0; treat them as blockers, not background tasks. | You | P0 |
| **R12** | **Contract drift** between the two tracks | 🟠 | If we don't fix event shapes + MCP tool signatures up front, the two halves won't meet. | Lock the **interface contract** in [`roles.md`](roles.md) before parallel work; both sides mock the other. | Both | P1 |
| **R13** | **Technology soup** — using every tool "because we can" | 🟡 | Dilutes the story; Vonage reads it as unfocused. | Each layer must earn its place (see SRS §6.1). If a layer isn't justified, cut it. | You | all |
| **R14** | **Scope creep toward "build a company"** | 🟠 | Storefront, mobile app, route optimization, multi-tenant — none improve the demo. | Hold the SRS "out of scope" line (SRS §4). Re-plan if real work exceeds it. | You | all |

## 3. The one thing to do first

**Clear R1 (Vonage RCS access) and R3 (Field Service DE) in parallel, on day one.** Everything
else can proceed against mocks; these two cannot be mocked past the final integration, and both
depend on external parties, so their lead time dominates the schedule.

## 4. Updates

*(Append-only. New dated entries go at the bottom; never rewrite an old one.)*

- **2026-10-06** — Register created from the research in [`idea.md`](idea.md) §27–§30. No fixed
  deadline set; phase map is logical order, not committed dates.
