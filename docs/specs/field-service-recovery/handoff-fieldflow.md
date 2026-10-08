# Handoff: FieldFlow AI POC — continue the build

## LATEST — 2026-10-09 (session 5): read this first

- **Step 8 (control panel) is IN PROGRESS — foundation built, GREEN checkpoint, paused mid-build so
  the user could switch accounts (weekly limit).** No work lost; everything is on disk + committed.
- **What's done (apps/control-panel/):** React+Vite+TS panel's **foundation** — deps installed with
  **pnpm**, a **fully token-driven theme** (dark default + light, one CSS-var block in
  `src/index.css`, Tailwind mapped to semantic tokens in `tailwind.config.js`), fonts (IBM Plex Sans
  + JetBrains Mono), `@/` import alias, `src/lib/cn.ts`, and the **generated** contract types
  (`scripts/gen-types.mjs` → `src/lib/contract.gen.ts` + `src/lib/contract/*.ts`, run via
  `pnpm run types`). `pnpm typecheck` + `pnpm build` both pass.
- **What's NOT done yet:** the data layer (`api.ts` for all endpoints, hand-typed `trace.ts`,
  `metrics.ts` Prometheus parser, `fixtures.ts` + `VITE_USE_FIXTURES` flag, TanStack Query hooks,
  QueryClient in `main.tsx`), the shadcn `ui/` primitives, the `Layout` shell, and all views
  (CaseList, **CaseDetail decision-trace hero**, RcsCardPreview, StatusTimeline, ApprovalActions,
  FailureDeck, ToolsSurface, MetricsStrip). The **old** `App.tsx`/`api.ts` are still the live app
  (untouched) so the build stays coherent — replace them when the new shell lands.
- **Decisions locked this session (OQ1–Q5 in [`build-step-8.md`](build-step-8.md) §3):** Tailwind +
  shadcn primitives we own · **polling now** behind a `useLiveCases` seam (**real SSE deferred** —
  needs a backend broadcast bus that would risk the 70 green tests) · ship **all** views A→B→C ·
  **in-panel metrics strip, Grafana deferred** · **fixtures + live flag** for UI dev · pnpm · theme
  fully manageable (dark+light).
- **To resume:** read [`build-step-8.md`](build-step-8.md) — §4 Plan, §5 Tasks + the **Resume
  notes** (exact decision-trace shape, canonical statuses, the `/cases`-has-full-trace shortcut, and
  the **pnpm esbuild allowlist** in `apps/control-panel/pnpm-workspace.yaml` — keep that file or
  `pnpm install` fails). A ready continuation prompt is in [`playbook.md`](../../../playbook.md) §8
  ("Resume Step 8").
- **Gate reminder:** backend was NOT touched → still 70 green. Don't add SSE/websocket or change any
  backend behaviour for the UI without telling the user first.

---

## LATEST — 2026-10-08 (session 4): read this first

- **Step 6 (Commerce + Razorpay) SHIPPED mock-first.** Price-book authority (LLM proposes *which
  part*, the book sets the amount), `FakeRazorpay` behind a `PaymentGateway` seam, flow
  quote → **Approve & Pay** (one RCS tap) → capture → close. **Two-layer no-double-charge:**
  idempotent gateway capture + envelope dedup on the payment `eventId`. Money is **integer paise**.
  High-value quotes (≥ ₹5,000, env `COMMERCE_HIGH_VALUE_PAISE`) route to a human via `/sim/approve`.
  Chargeable = chosen option needs a part AND (asset out of warranty OR `reason=additional_fault_found`);
  demo via `reason=additional_fault_found` or `appointmentId=SA-OOW`. Full detail:
  [`build-step-6.md`](build-step-6.md).
- **Step 9 Razorpay BUILT + offline-tested (live fire gated).** Real `RazorpayGateway` +
  `build_gateway(settings)` factory (blank keys → `FakeRazorpay`; a **non-`rzp_test_` key aborts the
  boot**). Confirmation is by **polling** `payment_link.fetch` in `settle_payment` (no Razorpay
  webhook). The SDK client is **injected** → **no `razorpay` dep added yet** (added only at the live
  fire). Detail: [`build-step-9.md`](build-step-9.md).
- **WEBHOOK DECISION (important, corrected this session):** "no webhooks in the POC" was
  **Razorpay-only** (Razorpay stays a `/sim/payment` poll). **Vonage RCS gets REAL inbound + status
  webhooks** — the user wants it real + robust to impress partners. `/sim/*` stays as the **offline
  twin** for tests/demos. Docs updated (context/00, scaffold framing, playbook).
- **Step 9b (real Vonage RCS) PLANNED, not built — this is the NEXT step.** Real **send** (carousel +
  "Approve & Pay" open-url) **and real `/webhooks/inbound` + `/webhooks/status`** (JWT verify, dedup
  by `message_uuid`, return 200). Full plan + the RCS send/webhook reference:
  [`build-step-9b.md`](build-step-9b.md). **A ready-to-paste continuation prompt for a fresh chat is
  in [`playbook.md`](../../../playbook.md) §8** ("Build Step 9b…").
- **Step 9c (real Salesforce MCP) — offload sheet written:** [`salesforce-handoff.md`](salesforce-handoff.md).
  The user builds custom **Apex REST** APIs; recommended path = point our Toolbox at those endpoints
  first (I write the Python), wrap as a real MCP server later ("Headless 360"). User has a DE org, new
  to Field Service.
- **Tests/gates:** from `apps/orchestrator`: `uv run pytest -q` → **58 passed**; `uv run ruff check .`
  clean; `uv run python -c "import app.main"` OK. Dev deps: `uv sync --extra dev`. Everything offline
  (fakes; no keys, no network).
- **User action items pending:** Vonage creds (`VONAGE_API_KEY/SECRET`, `VONAGE_APPLICATION_ID`,
  private key, `VONAGE_RCS_SENDER`) "added soon" + an ngrok tunnel + the 2 webhook URLs on the Vonage
  Application + a test Android (Google Messages) number. Razorpay **test** keys are already in `.env`
  (live fire is far off). **$100 Vonage credit — spend sensibly** (one send per manual demo).
- Housekeeping: `temp.txt` at root is the user's scratch notes — **leave it**.

---

## 2026-10-08 (session 3)

- **Step 5 is SHIPPED + LIVE-VERIFIED.** New `app/llm/` package: the `Proposer` ladder (Groq →
  Gemini → deterministic floor, lazy-imported SDKs), evidence-weighted `confidence.py` (5 factors,
  LLM clamped `min(self,prior)`), and the `needs_human_for` risk-tier floor (`ALWAYS_HUMAN_REASONS`).
  Confidence is blended in `policy_validate` (it needs policy headroom). **47 pytest green, ruff
  clean, `import app.main` OK.** Full detail + 7-section Explanation in [`build-step-5.md`](build-step-5.md).
- **Live-verified on the user's real keys (billed):** live Groq (blended 0.988), live Gemini
  (0.9175), and a forced-429 + real-503 fallback all the way to deterministic (rate-limit note
  preserved; complex blended 0.67 < 0.7 → human). Deps `groq` + `google-genai` are installed.
- **MODEL DRIFT (important):** the planned `llama-3.3-70b-versatile` and `gemini-2.5-flash` were
  **gone** from the free tiers (404). **Live-locked defaults now: Groq `openai/gpt-oss-120b`, Gemini
  `gemini-flash-latest`** (set in `config.py`, `.env`, `.env.example`). Always verify model ids per
  account with the SDK `.models.list()`.
- **Calibration note:** the `complex` prior was lowered 0.50 → 0.40 so a well-grounded complex job
  stays below the 0.7 gate at ANY grounding (0.50 would auto-send live). `test_confidence.py` locks it.
- **Still open (gated — ask before doing):** (1) OQ5 — add the confidence + risk-tiering note to
  `context/02` + `context/06` (needs a yes before editing context docs); (2) panel wiring of
  `rateLimitNote`/`confidenceBreakdown` is Step 8. **Next build step is 6 (commerce + Razorpay).**
- Housekeeping: `make install` = plain `uv sync` prunes dev extras → use `uv sync --extra dev`.
  `temp.txt` at repo root is still untracked noise (safe to delete).

---

## LATEST — 2026-10-08 (session 2)

- **Step 4 RAG is now LIVE-VERIFIED.** Ran `scripts/ingest_knowledge.py` against the user's real
  Supabase pgvector via Jina: **17 chunks embedded**; real cited retrieval works (warranty query →
  warranty Clause 1, score 0.752; fault-code query → F3 control-board). Fixed a cp1252 console crash
  in the script's final `print` (`→`→`->`). **28/28 pytest, ruff clean.** See
  [`build-step-4.md`](build-step-4.md) Updates.
- **Commits:** all Step 4 work + the testing guide were handed to the user as **8 small commit
  commands** (human-commits style, no AI trailer). Confirm they ran them: `git log --oneline` should
  show the feat/test/docs commits above `8d0927d`. `temp.txt` (empty) was told to be deleted.
- **Step 5 is DECIDED but NOT built.** Full plan + locked decisions in
  [`build-step-5.md`](build-step-5.md). Summary: Groq `llama-3.3-70b-versatile` as the real proposer;
  fallback ladder **Groq → Gemini `gemini-2.5-flash` → deterministic canned**; **evidence-weighted
  confidence** (5 factors, LLM can only lower not inflate, calibration test locks delay/parts→auto &
  complex→human — fixes over-escalation). Deps to add: `groq`, `google-genai`. Both `GROQ_API_KEY`
  and `GEMINI_API_KEY` are already in `.env`.
- **New doc:** [`testing-guide.md`](testing-guide.md) — a learn-by-testing guide for juniors (every
  test mapped to the promise it guards + 10 scoped tests to add). Linked from playbook + spec index.
- **OQ1–OQ5 are ANSWERED** (see build-step-5.md "Open questions — ANSWERED"). Key one: OQ1 =
  **risk-tiering** — the calibrated confidence score is the primary gate **plus** a hard
  `ALWAYS_HUMAN_REASONS` floor (`safety_risk`, `warranty_dispute`) that forces human review regardless
  of score. OQ2 = every LLM + confidence knob lives in `.env` (tweakable). OQ5 = approved to update
  context/02 + context/06 **after** Step 5 ships.
- **Immediate next action:** implement Step 5 **mock-first** in the task order in `build-step-5.md`
  (no need to re-confirm OQs). Tests stay offline (fake proposer); the 28 stay green; one gated live
  Groq call + a forced 429 proves the fallback at the end.

---

# (original handoff — session 1)

## Context & goal
- The user is the **tech lead** managing the FieldFlow AI POC (working dir `C:\Users\hp\Desktop\RCS-VONAGE-POC`). They are managing the project, not necessarily deep in the jargon — explain plainly.
- **Goal:** an AI field-service recovery demo. One idea: *AI proposes, deterministic policy decides, a human approves risk; RCS (rich customer messaging) is the customer control plane.*
- Build is **mock-first**, managed free tiers, no Docker. Shipped in numbered steps; specs live under `docs/specs/field-service-recovery/`.
- The user just asked for this handoff so work can continue in another chat without losing context.

## Key decisions made (do NOT re-lititate)
- **Orchestrator = MCP client; Salesforce + e-com = MCP servers** (final state). Today an **in-process `Toolbox`** stands in for the network MCP — same shape, fakes behind it. Real hosted MCP swaps in at Step 9 (needs a Salesforce Field Service Developer Edition org + access, risk R3, not yet cleared).
- **Tool surface split concern-wise (SOC):** granular Salesforce reads (`get_appointment/get_customer/get_asset/get_technician`, `inventory.find_part`); the aggregate `get_context` was **dropped**.
- **Action tools run the authority ladder in the tool layer and return a `ToolResult` that can refuse** (`inventory.reserve`, `reschedule.confirm`). Idempotency + audit + emit stay in the **service layer** (`case_service._persist`), so graph nodes stay DB-free.
- **`toolsUsed` in the decision trace is real** (recorded from actual Toolbox calls), not hard-coded.
- **`GET /tools`** exposes the surface (reads/actions grouped, with descriptions).
- **10 at-risk reasons → 3 behaviour archetypes:** `delay` (conf 0.9 → reschedule), `parts` (conf 0.8 → inventory race NFR-5), `complex` (conf 0.5 → human approval NFR-4). The 3 canonical reasons (`technician_delay`, `part_missing`, `asset_complex`) drive the real demos; the other 7 are cosmetic variety. `reason` is wired into `/sim/appointment-at-risk`.
- **RAG = LlamaIndex (knowledge); MCP = Toolbox (live data/actions); LangGraph orchestrates both.** Justification: LangGraph = conductor (when to retrieve, interrupt/resume); LlamaIndex = library desk (loaders, chunking, embeddings, vector store, reranker, incremental ingest). They are different layers.
- **RAG embeddings = Jina (hosted)**, not local (user vetoed local — slows their PC). Reranker: Jina. Everything else prod-grade (eval harness, hybrid/BM25 search, multi-tenant) **deferred**.
- **RAG corpus is generated by Claude** (all fake), multi-format, with citations + links.
- **Incremental ingest** uses **content-stable chunk ids** (`doc#<sha1(text)[:12]>`) + a store-agnostic diff, so inserting pages anywhere re-embeds only the new chunks. Owned by us (not LlamaIndex's docstore) so it's unit-testable on the fake store.
- **Unit tests never touch Supabase or Jina** (use `FakeKnowledgeStore` + a deterministic token-hash embedder). The real Jina+pgvector path is covered by a separate **live smoke test** (user wants "real testing soon").
- **Checkpointer is in-memory** (LangGraph); Postgres swap deferred behind `make_checkpointer()`.
- Installing LlamaIndex **pinned SQLAlchemy 2.1.3 → 2.0.54**; all tests stayed green.

## Current state
- **Shipped & green: Spine, Step 1 (policy + full LangGraph flow + NFR-4/5/6), Step 2 (Toolbox/MCP surface), §3 (10 reasons/3 archetypes), Step 4 (RAG mock-first).**
- **Tests: `uv run pytest -q` → 28 passed. `uv run ruff check .` → All checks passed. `import app.main` → OK.** (Run from `apps/orchestrator`.)
- Graph flow now: `load_case → load_context → retrieve_knowledge → evaluate_sla → generate_options → policy_validate → (auto-safe → offer_to_customer | risky/low-conf → human_approval) → offer_to_customer → await_reply → execute → verify → close`.
- RAG retrieval sanity-checked on the fake store: 17 chunks across 5 docs; warranty query → warranty doc, PCB query → control-board chunk.
- **The user has added REAL keys to `apps/orchestrator/.env`** (`JINA_API_KEY` + Supabase `DATABASE_URL`). `.env` is gitignored (confirmed).
- **Nothing is mid-edit in code.** The one outstanding task is the **live smoke test** (below), which was NOT run because it touches the user's real Supabase + Jina and needs an explicit go.

## Work in progress (verbatim)

**The single open task — live RAG smoke test (gated on user go).** It creates a `knowledge_chunks` table in the user's Supabase DB and makes ~17 Jina embedding calls. Commands (run from `apps/orchestrator`):
```bash
uv run python scripts/ingest_knowledge.py       # ingests corpus into real pgvector via Jina
# then verify a real retrieval returns cited passages from pgvector (write a short one-off script
# or reuse app.rag: make_knowledge_store(settings).retrieve("...warranty...", 3))
```
If it surfaces a config issue, the likely culprit is the Supabase connection string: must be the **Session pooler, port 5432**, with the `+asyncpg` driver (the RAG store converts `+asyncpg`→`+psycopg2` internally); the transaction pooler on **6543 breaks asyncpg** — avoid it.

**Key files built this session (all under `apps/orchestrator/`):**
- `app/tools/registry.py` — `ToolResult`, `Toolbox` (`register/call/describe`), `build_toolbox(salesforce, inventory)`.
- `app/tools/salesforce.py` — `FakeSalesforce` with granular reads + `reschedule`; `get_context` removed.
- `app/tools/inventory.py` — unchanged backing (`find_part` read, atomic `reserve` action, `set_stock`).
- `app/graph/build.py` — `build_graph(toolbox, vonage, knowledge, *, checkpointer, retrieval_k=3)`; `REASON_ARCHETYPE`, `CONFIDENCE_BY_ARCHETYPE`, `_propose`, `retrieve_knowledge` node, real `toolsUsed`, `knowledgeSources`.
- `app/rag/embed.py` — `Embedder` Protocol, `DeterministicEmbedder` (tests), `JinaEmbedder` (live).
- `app/rag/store.py` — `Chunk`, `RetrievedChunk`, `KnowledgeStore` Protocol, `FakeKnowledgeStore`.
- `app/rag/split.py` — `split_markdown/split_csv/split_pdf/split_file` (structure-aware, content-hash ids).
- `app/rag/ingest.py` — `ingest_dir(store, corpus_dir)` → `IngestReport` (idempotent, incremental).
- `app/rag/pgstore.py` — `PgVectorKnowledgeStore` (sync pgvector + Jina embed + Jina rerank; live only).
- `app/rag/__init__.py` — `make_knowledge_store(settings)` (picks real vs fake).
- `app/rag/corpus/` — generated: `service-manual.pdf`, `warranty-policy.pdf`, `troubleshooting-faultcodes.md`, `technician-sop.md`, `part-compatibility.csv`.
- `scripts/generate_corpus.py`, `scripts/ingest_knowledge.py`.
- `app/sim/routes.py` — `AtRiskRequest.reason` added. `app/api/routes.py` — `GET /tools`.
- `app/config.py` + `.env.example` — Jina/RAG settings. `app/main.py` — builds Toolbox + knowledge store + graph.
- Tests: `tests/test_tools.py`, `tests/test_rag.py`, archetype tests in `tests/test_decision_flow.py`, `tests/conftest.py` (toolbox + knowledge fixtures).
- Specs: `docs/specs/field-service-recovery/build-step-2.md` and `build-step-4.md` (full plan/tasks/explanation). `playbook.md` (repo root) = canonical commands.

## Rejected paths
- Real network MCP server now (FastMCP) — blocked on SF org access + slow; in-process Toolbox chosen.
- Giving the LLM raw tool execution — breaks the one rule (model proposes, function decides).
- Idempotency/audit inside graph nodes — breaks the DB-free-node design.
- Local embeddings (fastembed/sentence-transformers) — user vetoed (slows PC); Jina chosen.
- Whole-document embedding / position-based chunk ids — can't do incremental; content-hash ids chosen.
- LlamaIndex `IngestionPipeline` docstore for dedup — would diverge fake vs real; own store-agnostic diff chosen so it's testable.
- LlamaIndex `PGVectorStore` for the vector table — kept the table in our own Postgres for transparency; LlamaIndex still supplies Jina embed + rerank.
- Postgres LangGraph checkpointer now — in-memory kept for no-infra tests.

## Tone & working preferences (HARD RULES — in project CLAUDE.md + memory)
- **Explain in plain, teaching style:** simple words, point form, one-line meaning for every technical term on first use, why-it-matters per choice, small examples/diagrams. No jargon dumps.
- **Do NOT move until the user answers.** When an open question is on the table, stop — no edits, no building, no "I'll start the easy part." Wait for explicit go on every open question.
- **Always surface the user's own action items + delegation map** (env/service setup, SF/e-com org work, testing, resources, and which boring low-risk tasks to give junior devs vs keep). Treat them as a tech lead.
- **End every substantial reply with three headings in this order:** `What I achieved`, `What I need from you`, `Next steps` (numbered).
- **Plan-first even in auto mode:** restate the task, write the plan, list open questions with recommendations, wait for approval before editing. Spec-driven: append Plan/Tasks/Updates/Explanation to the step's `build-step-N.md`.
- **`playbook.md` is the single home for all commands/how-to-run** — update it in the same change as any operational change; don't re-paste long command lists in chat.
- **Ask before rewriting context docs** (`docs/specs/field-service-recovery/context/**`).
- No real customer data — fake everything. No em-dashes in generated PDFs (they extract as mojibake; use hyphens).
- Confirm before outward-facing/irreversible actions (e.g. hitting the user's live Supabase/Jina).

## Immediate next step
Ask the user to choose: **(A)** run the live RAG smoke test now (ingest the corpus into their real Supabase pgvector via Jina, then show real cited retrievals) — this writes one `knowledge_chunks` table + ~17 Jina calls, so get their explicit go first; or **(B)** start **Step 5 (Groq LLM)** — plan-first (restate, open questions with recommendations, wait for go) before any code. Do not edit files until they pick.
