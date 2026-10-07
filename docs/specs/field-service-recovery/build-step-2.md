# Build Step 2 — MCP tool-interface over the fakes (read tools → action tools)

**Status:** Shipped · **Created:** 2026-10-07 · **Last updated:** 2026-10-08

> Goal of this step: stop the graph from calling fake objects directly. Put a **controlled tool
> surface** between the graph and the enterprise systems — safe **read** tools the model may call
> freely, and validated **action** tools where the *function* decides the outcome, never the LLM.
> Still mock-first (FakeSalesforce / FakeInventory behind the surface); real hosted MCP swaps in
> behind the same seam later. Build order #3 (see [`scaffold.md`](scaffold.md)).

## North star (unchanged)

The whole system in the context docs. This step builds the **Tools (MCP)** layer from
[`context/03-knowledge-and-tools.md`](context/03-knowledge-and-tools.md) and the tool contract in
[`roles.md`](roles.md) §4.2. RAG (`knowledge.*`), real Salesforce, Groq, and commerce are still
later steps — this step leaves their seams clean.

## What you asked for

- MCP **tool-interface filled with FakeSalesforce data; read tools first, then action tools**
  (build order #3).
- Keep the Step-1 invariants: **the LLM proposes, deterministic policy decides**; every mutation
  runs the authority ladder; nodes stay DB-free; mock-first; speed over prod complexity.

## The one rule this step enforces (from the docs)

**A read tool is a safe lookup. An action tool is a validated function that decides its own
outcome after the authority ladder — the model may *call* it but never decides the result.** Raw
Salesforce write access never reaches the LLM.

## Open questions (confirm before building)

| # | Question | Recommended answer |
|---|----------|--------------------|
| Q1 | Decompose reads into the **granular** documented tools (`salesforce.get_customer / get_asset / get_appointment / get_technician`, `inventory.find_part`) and have `load_context` compose them — or keep the Step-1 `get_context` aggregate? | **Granular.** Matches the docs, and makes `toolsUsed` in the decision trace real ("show your work"). `load_context` calls several and records which fired. |
| Q2 | **In-process Toolbox** (an MCP-*shaped* registry over the fakes) now, or stand up a **real network MCP server** (e.g. FastMCP)? | **In-process Toolbox now.** Speed-first; the real hosted Salesforce MCP needs org access (risk R3) that isn't cleared. The Toolbox is the exact seam a real MCP client drops behind. |
| Q3 | Expose **`GET /tools`** so the panel can show the controlled surface? | **Yes, tiny.** One read endpoint listing `{name, kind, args}`. Good demo value, near-zero cost. |
| Q4 | Where does the action tool's **idempotency + audit + emit** run? | **Service layer, as in Step 1.** The tool runs the *deterministic* ladder (permission/state/atomic execute) so it stays callable from a DB-free node; the service keeps idempotency + audit (already in `_persist`). Documented as the split. |

## Plan

**Shape:** introduce a `Toolbox` seam; the graph calls `toolbox.call(name, **args)` instead of
touching fakes. The Toolbox knows each tool's **kind**:
- `read` → dispatch straight to the backing fake.
- `action` → run the deterministic authority check first; refuse (with reasons) or execute
  atomically; return a `Result`. Idempotency + audit stay in the service layer.

```
LangGraph node ─▶ Toolbox.call("salesforce.get_asset", assetId=…)      # read: free
LangGraph node ─▶ Toolbox.call("inventory.reserve", partNo=…, qty=1)   # action: ladder → Result
                        │
                        ▼  (action only)
                 authority check (permission · state · validity) ─▶ atomic execute ─▶ Result
```

**Step-2 tool surface (subset of roles §4.2 — the rest land with their layers):**
- Read: `salesforce.get_customer`, `salesforce.get_asset`, `salesforce.get_appointment`,
  `salesforce.get_technician`, `inventory.find_part`.
- Action: `reschedule.confirm(appointmentId, slotId)`, `inventory.reserve(partNo, qty)`.
- Deferred seams (named, not built): `knowledge.*` (RAG step), `commerce.*` + `workorder.close`
  (commerce step), `reschedule.propose` (today it's `generate_options` + `policy_validate`).

**Files to touch:**
- **new** `app/tools/registry.py` — `Toolbox`: `register(name, kind, fn)`, `call(name, **args)`,
  `describe()`; the `action` path runs the authority check + records the call.
- `app/tools/salesforce.py` — split `get_context` into the granular read tools (keep a thin
  composer or drop the aggregate); keep `reschedule`.
- `app/tools/inventory.py` — unchanged backing; registered as `find_part` (read) + `reserve`
  (action).
- `app/graph/build.py` — `build_graph(toolbox, vonage, *, checkpointer)`; `load_context` composes
  read tools and records real `toolsUsed`; `execute` calls action tools via the Toolbox.
- `app/main.py`, `tests/conftest.py` — build the Toolbox over the fakes, pass it into `build_graph`.
- `app/api/routes.py` — `GET /tools` (surface for the panel), if Q3 = yes.
- **new** `tests/test_tools.py`.

**Alternatives to reject (write down why):** real MCP server now (infra + access we don't have);
giving the LLM raw tool execution (breaks the one rule); putting idempotency/audit inside nodes
(breaks the DB-free-node design from Step 1).

## Tasks

- [x] `Toolbox` registry with `read` / `action` kinds + `describe()`.
- [x] Action path runs the deterministic authority check and refuses illegal calls with reasons.
- [x] Granular Salesforce read tools; `inventory.find_part` read; `load_context` composes them.
- [x] `reschedule.confirm` + `inventory.reserve` as action tools; `execute` uses them.
- [x] Real `toolsUsed` recorded in the decision trace from actual Toolbox calls.
- [x] `GET /tools` surface (confirmed Q3 = yes; grouped reads/actions + descriptions).
- [x] Tests: read/action dispatch; action refusal; context composition; **Step-1 tests + NFR-4/5/6
      stay green**; ruff clean. `/sim` → panel path unchanged (live hop still manual, as before).

## Open questions — answered (2026-10-08)

- **Q1 → Granular.** Split reads concern-wise (SOC): `get_appointment / get_customer / get_asset /
  get_technician` + `inventory.find_part`. `load_context` composes them; the aggregate `get_context`
  is **dropped**.
- **Q2 → In-process Toolbox now.** User confirmed: fakes now, but the Toolbox must stay the clean
  swap-point for a real hosted-MCP demo later (events fired from the Salesforce UI → orchestrator as
  MCP client). The graph + tests do not change when the backend is swapped.
- **Q3 → Yes, detailed.** `GET /tools` returns reads/actions grouped, each with `{name, kind, args,
  description}` + a one-line read-vs-action note.
- **Q4 → Service layer.** The tool runs only the deterministic ladder; idempotency + audit + emit
  stay in `case_service._persist` (unchanged from Step 1), so nodes stay DB-free.

## Acceptance (self-checks, no infra)

Extend `pytest` (in-memory SQLite + fakes), all green:
- a read tool returns data; an action tool runs the authority check and **refuses an illegal call**
  with a reason;
- `inventory.reserve` through the Toolbox is still atomic and still drives **NFR-5**;
- `load_context` produces the same context via composed read tools, and `toolsUsed` reflects the
  real calls;
- every Step-1 test (idempotency, spine, policy, NFR-4/5/6, happy path) still passes.

Keep `ruff` clean. Keep the walking-skeleton run working (`/sim` → panel).

## Rules

Speed-first; mock-first; compact updates; **ask before any big context-doc rewrite**; the LLM
proposes, the function/policy decides. See [`CLAUDE.md`](../../../CLAUDE.md),
[`context/03-knowledge-and-tools.md`](context/03-knowledge-and-tools.md), and
[`context/02-orchestration-and-policy.md`](context/02-orchestration-and-policy.md).

## Updates

- **2026-10-07** — Plan created (after Step 1 shipped). Awaiting go on the open questions, then build.
- **2026-10-08** — **Built Step 2.** Q1–Q4 answered (above). `Toolbox` added; Salesforce split into
  granular reads; `reschedule.confirm` + `inventory.reserve` are action tools that run the ladder
  and may refuse; graph refactored to `build_graph(toolbox, vonage, *, checkpointer)`; `toolsUsed`
  is now real. `GET /tools` added. **20/20 pytest green** (was 10; +10 in `test_tools.py`), **ruff
  clean**, `app.main` imports. No context-doc rewrites yet — flagged below for a yes/no.

## Explanation

**1. What changed.** The graph no longer touches the fakes directly. A new **Toolbox** (an
MCP-shaped registry) sits between them. The graph calls `toolbox.call(name, **args)` for everything:
*read* tools are safe lookups; *action* tools run the authority ladder and return a `ToolResult`
that can **refuse**. The old single `salesforce.get_context` aggregate is gone — context is now
composed from four granular reads, and the decision trace's `toolsUsed` reflects the **real** calls
instead of a hard-coded list.

**2. Why it was needed.** Step 1 closed the graph over `FakeSalesforce`/`FakeInventory` and faked
`toolsUsed`. The product's one rule is *the model proposes, the function decides*; that needs a
controlled surface where read vs action is explicit and raw writes never reach the model. It's also
the exact seam a real hosted-MCP backend drops behind later (fired from the Salesforce UI).

**3. How it works, step by step.**
- `build_toolbox(salesforce, inventory)` registers each tool with a **kind** (`read`/`action`),
  its required args, and a one-line description. camelCase tool args (the contract) adapt to the
  pythonic fake methods via thin lambdas.
- `Toolbox.call(name, **args)` looks the tool up, guards missing args, then: **read** → wrap the
  backing return in `ToolResult(ok=True, data=…)`; **action** → call the function, which runs its
  own ladder and returns a `ToolResult` that may be `ok=False` with a `reason`. Unknown tool / bad
  args → a refusal `ToolResult`, never an exception.
- `load_context` composes the case context from `get_appointment → get_customer/get_asset/
  get_technician` (appointment carries the linked ids, same as real Salesforce) and records those
  four as `toolsUsed`. `generate_options` adds `inventory.find_part` to `toolsUsed` only when a
  candidate needs a part. `policy_validate` writes the real `toolsUsed` into the decision trace.
- `execute` performs both mutations through action tools: `inventory.reserve` (refusal → NFR-5
  recompute/re-offer) and `reschedule.confirm` (refusal on unknown/terminal case → re-offer).
- Idempotency + audit + decision-trace persistence stay in `case_service` (Q4) — nodes stay
  DB-free.

**4. Files / functions changed.**
- **new** `app/tools/registry.py` — `ToolResult`, `Toolbox` (`register` / `call` / `describe`),
  `build_toolbox()` (the Step-2 surface + the two action ladders).
- `app/tools/salesforce.py` — `FakeSalesforce` is now a small in-memory org with granular reads
  (`get_appointment/get_customer/get_asset/get_technician`) + `reschedule`; `get_context` removed.
- `app/graph/build.py` — `build_graph(toolbox, vonage, *, checkpointer)`; `load_context` composes
  reads; `generate_options`/`execute` go through the Toolbox; `_add()` keeps `toolsUsed` unique and
  ordered across the NFR-5 recompute; `toolsUsed` added to `GraphState`.
- `app/main.py`, `tests/conftest.py` — build the Toolbox over the fakes and pass it in.
- `app/api/routes.py` — `GET /tools` (reads/actions grouped, with descriptions).
- **new** `tests/test_tools.py` — read dispatch, refusals (unknown tool / missing arg / no stock /
  unknown appointment), atomic reserve, `describe()`, context composition + real `toolsUsed`.
- `app/tools/inventory.py` — unchanged backing; registered as `find_part` (read) + `reserve`
  (action).

**5. Important decisions.**
- **Uniform `ToolResult` for reads and actions** — one shape to assert on; reads are always
  `ok=True`. Rejected mixed return types (dict for reads, result for actions) as harder to test.
- **Action ladders live in `build_toolbox`, not in `FakeSalesforce`** — keeps the fake a pure data
  store and avoids a `salesforce → registry` import cycle. The ladder is deterministic and sits in
  the tool layer, exactly where real SF permission/territory checks slot in later.
- **camelCase tool args via adapter lambdas** — the public surface matches the contract/docs while
  the fakes stay pythonic. One obvious place (`build_toolbox`) does the mapping.
- **`toolsUsed` recorded in nodes (state), not a global log on the Toolbox** — concurrency-safe and
  honest per case; `_add()` dedupes across the recompute loop.

**6. Tests / verification.** `uv run pytest -q` → **20 passed** (10 Step-1 + 10 new). `uv run ruff
check .` → **All checks passed!**. `import app.main` → OK. `GET /tools` payload verified: 5 reads,
2 actions, each with name/kind/args/description. NFR-4/5/6 + idempotency + spine all still green —
the refactor is behavior-preserving; reserve is still atomic and still drives NFR-5 through the
action tool.

**7. Edge cases & limitations.** The Toolbox is in-process and does **not** speak the MCP wire
protocol yet — same registry/read-vs-action shape, fakes behind it; the real MCP client swaps into
`build_toolbox` at Step 9 (needs the SF DE org + access, R3). `load_context` assumes the event's
appointment exists in the fake org (seeded `SA-19281`); an unknown appointment is only exercised via
the `reschedule.confirm` refusal path. Action ladders cover stock + case-state only — permission,
territory, travel-time and price authority arrive with real Salesforce. `knowledge.*`, `commerce.*`,
`workorder.close`, and `reschedule.propose` are named seams, not built.
