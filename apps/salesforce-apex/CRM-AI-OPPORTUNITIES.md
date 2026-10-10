# What We Can Build on CRM + AI — Top 5 Real Problems

**The thesis in one line:** one person who understands **Salesforce Hosted MCP**, uses **Claude to
write the Apex/logic**, and knows **basic Salesforce admin + config** can now ship systems that used
to need a whole team and a quarter — because the hard, risky parts are now standard, reusable
plumbing. FieldFlow AI (this repo) is the first proof. This doc picks the **top 5 CRM pains** the
same stack solves, with the idea and architecture for each.

> This is a strategy / possibility doc, not a build spec. Each idea reuses the **exact pattern**
> FieldFlow already proves: *AI proposes → deterministic policy decides → a human approves risk →
> tools act and may refuse.*

---

## The capability stack (why this is suddenly possible)

Three things became true, and together they change the economics of CRM software:

1. **Salesforce Hosted MCP (GA April 2026)** — Salesforce now hosts a standard **MCP (Model Context
   Protocol — a common way for an AI to discover and call tools)** server. An AI can *read* the CRM
   and *call curated Apex tools* without custom integration code. You enable it in Setup + an
   External Client App.
2. **Claude writes the logic** — the Apex classes, the policy rules, the orchestration, the tests.
   The bottleneck moves from "can we build it" to "do we know what to build and what the rules are."
3. **Basic admin + config** — objects, fields, permission sets, flows. The last mile that turns a
   prototype into something that runs in a real org.

**The missing piece most people get wrong:** letting the AI *act directly*. We don't. The AI only
**proposes**; a **deterministic policy engine decides**; a **human approves anything risky**; tools
**can refuse**. That is the difference between a demo and something a business will actually switch
on. Every idea below keeps that spine.

---

## The shared reference architecture

All five solutions are the same skeleton with different rules and data — which is why one person can
build many of them:

```
  Trigger                Brain (proposes)        Gatekeeper (decides)      Hands (act, may refuse)
  ───────                ────────────────        ────────────────────      ──────────────────────
  CRM event /     ──►    LLM proposer       ──►  Deterministic policy ──►  Apex REST (writes)
  schedule /             (Claude, grounded        engine (rules, SLAs,      Hosted MCP (agentic reads)
  inbound msg            in RAG + CRM reads)       thresholds, risk tiers)   e-com / billing / comms
                                                        │
                                                        ▼
                                                 Human approval for risk
                                                 (nothing risky auto-fires)

  Cross-cutting: observability (every decision traced) · reconciliation (nothing stuck) ·
                 dead-letter + replay (nothing lost) · idempotency (nothing double-done)
```

**Two lanes, deliberately separate** (this is the core design rule):
- **Deterministic lane** — the automated pipeline. Writes go through **Apex REST + the policy
  engine**. The LLM never fires a mutation.
- **Agentic lane** — the **admin copilot**. Open-ended questions over **Hosted MCP**. Reads are free;
  **writes are human-confirmed.**

---

## The top 5 problems

### 1. Field-service failure & appointment recovery  *(the flagship — built here)*

- **The pain:** a repair/visit goes wrong (tech delayed, part missing, wrong skill) and the customer
  is stuck waiting with no way to self-serve. Rebooking is manual, slow, and leaks goodwill.
- **Who feels it:** home services, appliance repair, telecom installs, utilities, medical equipment.
- **The idea:** detect the at-risk appointment, reason over the full context (customer, asset,
  warranty, stock, technician), validate options against hard rules, and let the customer **fix it
  themselves over RCS (Rich Communication Services — upgraded SMS with cards/buttons)**. Then execute
  the real changes across Salesforce, inventory and payment.
- **Architecture:** Platform Event trigger → LLM proposes new slots (grounded in RAG + CRM reads) →
  policy validates (SLA, warranty, part availability, travel) → human approves high-risk → RCS card →
  one tap reschedules in Salesforce via Apex REST; out-of-warranty parts route through a pay flow.
- **Guardrail:** reschedule is deterministic; safety/warranty disputes always go to a human.
- **Status:** **working end-to-end in this repo**, live-verified against a real Salesforce org.

### 2. Speed-to-lead: triage, qualify & route inbound leads

- **The pain:** inbound leads sit unactioned. Response time is the single biggest driver of
  conversion, and most teams answer in hours, not minutes — especially nights/weekends.
- **Who feels it:** any B2B/B2C sales org, agencies, marketplaces, education, real estate.
- **The idea:** the moment a Lead/Web-to-Lead lands, AI enriches it (reads account/contact history
  via MCP), scores and qualifies it against **your** ICP rules, drafts a first touch, and routes it
  to the right rep — within seconds, 24/7. A human approves anything that commits (pricing, promises).
- **Architecture:** Lead-created event → LLM proposes qualification + routing + draft reply (grounded
  in CRM history + your playbook via RAG) → policy decides routing by territory/round-robin/SLA →
  auto-send the *safe* nurture touch; *route + notify* for anything needing a human.
- **Guardrail:** AI drafts and routes; it never fabricates a commitment. Discounts/quotes → human.
- **Build effort:** small — it's the same skeleton; swap the trigger, rules, and channel (email/SMS).

### 3. Support case deflection & resolution copilot

- **The pain:** support backlogs, slow first response, agents hunting across knowledge bases and past
  cases. Customers re-explain themselves; easy tickets clog the queue.
- **Who feels it:** SaaS support, telco, retail, financial services, any help desk.
- **The idea:** on a new Case, AI reads the customer's history (MCP), retrieves the right knowledge
  (RAG over your docs/past resolutions), and **proposes** a resolution or the next question. Simple,
  high-confidence cases get an auto-draft reply for the agent to approve; complex ones get a prepared
  brief so the agent starts at minute 10, not minute 0.
- **Architecture:** Case-created/updated event → LLM proposes resolution + cited sources → policy
  gates by confidence + case type (billing/legal/safety never auto-resolve) → agent approves → reply
  + Case update via Apex. The **admin copilot** (Hosted MCP) answers "show me similar closed cases."
- **Guardrail:** confidence threshold + always-human categories; every answer cites its source.
- **Build effort:** medium — the RAG corpus (your knowledge) is the main investment.

### 4. Renewal risk & revenue leakage

- **The pain:** renewals slip through the cracks, at-risk accounts aren't flagged until they churn,
  and revenue leaks through under-billing, missed upsells, and expired contracts nobody chased.
- **Who feels it:** subscription/SaaS, B2B services, insurance, equipment leasing, memberships.
- **The idea:** a scheduled sweep reads renewal dates, usage/health signals and support history (MCP),
  **proposes** a prioritized at-risk list with a recommended play per account, and drafts the outreach.
  A deterministic check catches billing mismatches (contracted vs invoiced). Humans approve the plays.
- **Architecture:** scheduled trigger → LLM proposes risk ranking + per-account play (grounded in CRM
  signals) → policy flags hard billing discrepancies deterministically → CSM dashboard + drafted
  touches → approved actions write back tasks/opportunities via Apex.
- **Guardrail:** money math is deterministic, never the LLM's guess; nothing bills or discounts itself.
- **Build effort:** medium — the value is in the signals you feed it.

### 5. CRM data hygiene & the admin copilot

- **The pain:** dirty, duplicate, half-empty CRM data quietly breaks everything above it. Reps won't
  enter data; admins can't answer "what's going on in the org" without building a report for each ask.
- **Who feels it:** literally every Salesforce org, worst at scale.
- **The idea:** an **admin copilot** — a chat box where an admin asks open-ended questions over the CRM
  ("which appointments need attention?", "find duplicate contacts for this account", "what changed on
  this opportunity?") and the AI uses **Hosted MCP tools** to answer live. Plus a hygiene pass that
  **proposes** merges/fills and lets a human confirm in bulk.
- **Architecture:** this is the **agentic lane** — `/copilot` route → MCP client → Hosted MCP tools
  (curated Apex like `Get appointment health`, `Find appointments needing attention`) → the LLM picks
  and calls them. **Reads are free; every write is human-confirmed.**
- **Guardrail:** the copilot can look at anything it's permissioned for, but changes are always a human
  click — never an autonomous write.
- **Status:** the plumbing is **built in this repo** (`apps/salesforce-apex/FieldFlowCopilotTools.cls`
  + the orchestrator MCP client at `app/mcp/`); the chat UI is next.

---

## Why these five (the selection logic)

| # | Problem | Pain intensity | $ at stake | Build effort | Reuses FieldFlow pattern |
|---|---------|----------------|------------|--------------|--------------------------|
| 1 | Field-service recovery | High | High | **Done** | — (it *is* the pattern) |
| 2 | Speed-to-lead | High | High | Small | Trigger + rules swap |
| 3 | Support copilot | High | Medium | Medium | + RAG corpus |
| 4 | Renewal / leakage | Medium | **Very high** | Medium | + signal plumbing |
| 5 | Data hygiene / copilot | High (silent) | Medium | Small–Med | The agentic lane |

They're chosen because each is (a) a genuine, widely-felt CRM pain, (b) high-value, and (c) buildable
on the **same skeleton** — so shipping one makes the next cheaper.

---

## What makes this credible (not hype)

- **The guardrail is the product.** Businesses don't fear AI that drafts; they fear AI that *acts*.
  Keeping mutations deterministic and risk human-approved is why these can actually go live.
- **It's proven, not promised.** #1 runs end-to-end here against a real org; #5's plumbing is built.
- **Observability + recovery are built in.** Every decision is traced, nothing gets stuck (a
  reconciliation sweep), nothing gets lost (dead-letter + replay), nothing double-fires (idempotency).

## Honest limits

- **Data quality caps everything.** Garbage CRM in, garbage proposals out. #5 exists partly to fix this.
- **Hosted MCP inherits the user's permissions** — least-privilege matters; an over-permissioned
  integration user is a real risk to design around.
- **The LLM is a proposer, not an oracle.** The policy engine and the human are what make it safe; the
  moment someone removes those to "move faster," it stops being trustworthy.
- **Every org's shape differs.** The skeleton is reusable; the rules, fields and data chain are not —
  that last-mile config is the real work.

---

*Reference implementation: this repository (FieldFlow AI). The deterministic path is in
`apps/salesforce-apex/FieldFlowRest.cls` + the orchestrator policy engine; the agentic path is
`FieldFlowCopilotTools.cls` + `apps/orchestrator/app/mcp/`. Setup: `hosted-mcp-setup.md`.*
