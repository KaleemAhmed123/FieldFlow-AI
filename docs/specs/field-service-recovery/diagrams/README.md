# FieldFlow AI — Diagrams

Rich Excalidraw diagrams for presenting the idea (built for the manager review).

| File | Shows | Use it to say |
|------|-------|---------------|
| [`01-system-architecture.excalidraw`](01-system-architecture.excalidraw) | The 7 layers and how data flows, customer → Vonage → gateway → RabbitMQ → LangGraph → policy/MCP/RAG → Salesforce/commerce/Razorpay, with Postgres + observability underneath. | "This is a complete enterprise decision-and-execution system; RCS is the control plane." |
| [`02-customer-journey.excalidraw`](02-customer-journey.excalidraw) | The 13 stages of one recovery, each tagged with the RCS primitive it uses. | "One failed AC appointment, fully recovered through RCS — no phone call." |
| [`03-decision-authority.excalidraw`](03-decision-authority.excalidraw) | The authority ladder and "every mutation" path: AI proposes → policy validates → human if risky → execute → event → audit. | "The AI never decides. Deterministic rules do; humans approve risk." |
| [`04-scaffold-walking-skeleton.excalidraw`](04-scaffold-walking-skeleton.excalidraw) | The thin-spine scaffold: fired event → RabbitMQ → idempotency → LangGraph → FakeVonage → Postgres → panel. Dashed red = mocked now, real later. | "We prove the pipes end-to-end before any real logic." (See [`../scaffold.md`](../scaffold.md).) |

## How to open

- **VS Code:** install the *Excalidraw* extension, then click any `.excalidraw` file.
- **Browser:** go to <https://excalidraw.com>, then drag-and-drop the file (or File → Open).

## How they were made / editing

Generated from a small deterministic script
(`scratchpad/gen_excalidraw.py`) so IDs, bindings and layout are consistent. They're plain
Excalidraw JSON — once open, drag, recolor, and rearrange freely; your edits won't be overwritten
unless the generator is re-run to the same paths.

**Colour key:** yellow = customer-facing / core · green = deterministic / knowledge ·
purple = AI & tools · red = failure / event · blue = external systems · grey = infra.

> Per the project convention, the text versions of these flows also live in
> [`../context/`](../context/) and [`../srs.md`](../srs.md); these `.excalidraw` files are the
> presentation layer. If a flow changes, update the text first, then regenerate the diagram.
