# FieldFlow AI — Project Context

> **Living doc.** The shared mental model for FieldFlow AI — written so anyone new can read the
> codebase. It describes the whole target system; the walking-skeleton spine is built today and
> the deeper layers are planned. See [`../scaffold.md`](../scaffold.md) for what runs now.

Read in order the first time; jump by topic after.

| # | File | What it answers |
|---|------|-----------------|
| 00 | [overview](00-overview.md) | What FieldFlow AI is, the one idea, the 7 layers, the glossary. **Start here.** |
| 01 | [domain-and-data](01-domain-and-data.md) | What Salesforce owns vs what our Postgres owns; the `correlationId` tenancy key. |
| 02 | [orchestration-and-policy](02-orchestration-and-policy.md) | LangGraph graph, the authority ladder, "every mutation". |
| 03 | [knowledge-and-tools](03-knowledge-and-tools.md) | RAG (knowledge) vs MCP (live data + actions); read vs action tools. |
| 04 | [rcs-experience](04-rcs-experience.md) | RCS as control plane; the primitives; the 13-stage journey; hard constraints. |
| 05 | [reliability-and-observability](05-reliability-and-observability.md) | RabbitMQ/DLQ, idempotency, the 6 failure demos, and Logfire — the live god-eye trace view. |
| 06 | [principles-and-decisions](06-principles-and-decisions.md) | Why it's shaped this way; decisions made; open questions. |

**The one idea that explains everything:** *AI proposes; deterministic policy decides; humans
approve risk. RCS is the customer's control plane.*

See also: [`../srs.md`](../srs.md) · [`../risks.md`](../risks.md) · [`../roles.md`](../roles.md) ·
[`../diagrams/`](../diagrams/).
