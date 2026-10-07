# FieldFlow AI — Project Context

> **Design-time.** The shared mental model for the system we're building. Inspired by
> `ONLYCOUPLEZ/docs/context`, but describing the **target** system (no code yet), not a live one.
> As code lands, each file flips from "intended" to "how it works on `main`".

Read in order the first time; jump by topic after.

| # | File | What it answers |
|---|------|-----------------|
| 00 | [overview](00-overview.md) | What FieldFlow AI is, the one idea, the 7 layers, the glossary. **Start here.** |
| 01 | [domain-and-data](01-domain-and-data.md) | What Salesforce owns vs what our Postgres owns; the `correlationId` tenancy key. |
| 02 | [orchestration-and-policy](02-orchestration-and-policy.md) | LangGraph graph, the authority ladder, "every mutation". |
| 03 | [knowledge-and-tools](03-knowledge-and-tools.md) | RAG (knowledge) vs MCP (live data + actions); read vs action tools. |
| 04 | [rcs-experience](04-rcs-experience.md) | RCS as control plane; the primitives; the 13-stage journey; hard constraints. |
| 05 | [reliability-and-observability](05-reliability-and-observability.md) | RabbitMQ/DLQ, idempotency, the 6 failure demos, real telemetry. |
| 06 | [principles-and-decisions](06-principles-and-decisions.md) | Why it's shaped this way; decisions made; open questions. |

**The one idea that explains everything:** *AI proposes; deterministic policy decides; humans
approve risk. RCS is the customer's control plane.*

See also: [`../srs.md`](../srs.md) · [`../risks.md`](../risks.md) · [`../roles.md`](../roles.md) ·
[`../diagrams/`](../diagrams/).
