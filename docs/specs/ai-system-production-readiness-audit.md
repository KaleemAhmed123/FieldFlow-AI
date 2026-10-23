# FieldFlow AI — AI-System Production-Readiness Audit

**Audited revision:** `26dcc04` (HEAD, branch `main`, 2026-10-21)
**Live deploy at audit time:** `26dcc04` (orchestrator `/version` on Render — **current, not stale**)
**Auditor role:** AI/LLM architect · AI-security · distributed-systems · SRE · QA · release reviewer
**Method:** code is the source of truth; every finding cites `file:line` or a live read-only probe.
**Changes made to the app during this audit:** none (report only, as required).

> **Remediation status (updated 2026-10-22).** Fixes are tracked in
> [`production-readiness-remediation.md`](production-readiness-remediation.md). **Phase 0 (all P0
> pilot-blockers) is COMPLETE:** AI-SEC-01 (auth gate, verified live), AI-SEC-02 (copilot rate-limit),
> AI-SEC-03/P0-6 (fail-closed secrets), AI-REL-01 (retry tier), AI-BEH-01 (slot-time validation),
> AI-BEH-02 (customer-message guard), plus the `/ops` vs `/sim` split and authz tests. Remaining:
> Phase 1 (migrations, CI/lock, output eval, observability) + Phase 2 backlog.

> **Companion doc.** A separate `production-readiness-audit.md` (repo root, dated 2026-10-14)
> grades functional/reliability requirements (SRS FR/NFR) and the 12 engineering parameters. This
> report does **not** replace it — it goes deeper on the **AI-specific** surface the superset audit
> asks for: guardrails, prompt injection, RAG/memory, MCP/tool security, output validation,
> consequential-action authority, and the end-to-end AI workflow. Where the two overlap, this one is
> newer (HEAD `26dcc04` vs `9e93359`) and corrects two now-stale claims (the deploy is current; the
> Salesforce Hosted MCP is armed live).

---

## 1. Executive Summary and Overall Verdict

**In plain words.** FieldFlow AI is a field-service recovery system. When a repair appointment is
"at risk" (technician late, part missing, unit more broken than booked), the system uses an LLM
(large language model — the AI that writes text) to **propose** fixes, a deterministic **policy
engine** (plain rule code, no AI) to **decide** what is allowed, and a **human** to approve the risky
calls. The customer fixes everything over **RCS** (Rich Communication Services — SMS upgraded with
cards, buttons, payment links).

**The core architecture is genuinely well-built.** The one idea — *AI proposes, deterministic
policy decides, humans approve, and the LLM can never mutate anything directly* — is enforced in
code, end to end, not just promised in a prompt. The hard reliability parts (idempotency, dead-letter
queue, atomic inventory reserve, durable checkpoints, decision trace, two-layer no-double-charge) are
real and mostly live-verified. 129 tests pass; lint is clean.

**What blocks production is operational security, not the AI design.** The orchestrator is on a
**public URL with no authentication at all**, while wired to a **real Salesforce org, real Razorpay
test-mode, and a live admin copilot**. Anyone on the internet can fire events, toggle "Salesforce
down", read every case (names + phone numbers), and drive the copilot against the real org. That is a
release-blocker regardless of how good the pipeline is.

### Verdict: **NOT READY** for production with real customers or real money.

The blocker is a single Critical finding (**AI-SEC-01**, no auth on a public, live-wired API). It is
a classic POC corner that `CLAUDE.md` explicitly permits — but it stops being acceptable the moment
the deployment is public and touching live external systems, which it now is. Close AI-SEC-01 and
AI-SEC-02, and the system becomes **CONDITIONALLY READY for a controlled pilot** on the reliability
spine, with the documented residual gaps (no retry tier, no migrations, no adversarial tests).

---

## 2. Scope, Methodology, and Repository Revision

- **Repo:** `RCS-VONAGE-POC`, monorepo. Audited at `26dcc04`.
- **In scope:** orchestrator (FastAPI + LangGraph), the LLM proposer + confidence engine, the policy
  engine, RAG (LlamaIndex + pgvector), the MCP clients + admin copilot, the Toolbox tool surface,
  Vonage/Salesforce/Razorpay/e-com integrations, RabbitMQ, the Postgres state + checkpointer, the
  e-com inventory service (Next.js), the Salesforce Apex REST surface, and the React control panel.
- **Verification performed (Phase D, safe/authorized only):**
  - `uv run pytest -q` → **129 passed** (26.4 s).
  - `uv run ruff check .` → **All checks passed.**
  - Read-only live GETs against the Render deploy: `/version`, `/health`, `/health/deps`, `/cases`,
    `/copilot/tools`, `/dlq`; `GET` (not `POST`) on `/sim/fault` and `/sim/appointment-at-risk`
    (returned `405` — proving the routes are mounted and unauthenticated, with **zero** side effect).
  - Git checks for tracked secrets and lockfiles.
- **Deliberately NOT done** (would create real effects): no `POST /sim/*`, no event firing, no
  payment capture, no RCS/SMS send, no copilot chat call, no dependency installs, no code changes.

---

## 3. System Architecture and Dependency Map

```
CUSTOMER (Android · Google Messages · RCS)
   │  ▲  (card / carousel / payment link / confirmation)
   ▼  │
VONAGE Messages API  ──inbound/status webhooks──▶  /webhooks/*   (real)
SALESFORCE Apex trigger ──HTTP callout──────────▶  /webhooks/sf/at-risk
DEMO / tests ───────────────────────────────────▶  /sim/*        (offline twin, UNAUTHENTICATED)
                                   │  publish
                                   ▼
                              RabbitMQ  `events`  ──nack(no requeue)──▶  `events.dlq`
                                   │  consume (in-process, single consumer)
                                   ▼
                       LangGraph Orchestrator (durable Postgres checkpointer)
        ┌──────────────┬───────────────┬────────────────┬──────────────────┐
        ▼              ▼               ▼                ▼                  ▼
  Policy Engine   LLM Proposer     RAG (pgvector)   Toolbox (read+       Commerce
  (authority)     Groq→Gemini→     Jina embed+       action tools)       (price book,
                  deterministic    rerank            │                    Razorpay test)
                                              ┌───────┴────────┐
                                              ▼                ▼
                                      Salesforce Apex    e-com inventory
                                      REST (real org)    (Next.js+Supabase)

  Agentic side-path:  /copilot/chat → Groq tool-calling → MCP clients →
                      Salesforce Hosted MCP (OAuth2+PKCE) + e-com MCP (/api/mcp, no auth)

  State of record:  Supabase Postgres (cases, idempotency, audit, ai_decisions,
                    app_secrets, pgvector chunks, LangGraph checkpoints)
  Observability:    Logfire (live), Prometheus /metrics, structlog + correlation_id
```

### Trust boundaries & systems of record

| Data / concern | System of record | Notes |
|---|---|---|
| Service domain (appointment, asset, warranty, technician) | **Salesforce** | read via Apex REST; the one mutation is `reschedule` |
| Product price + stock | **e-com (Supabase)** | atomic reserve is a row-locked SQL function |
| Payment outcome | **Razorpay** | polled (no webhook); gateway is the authority on `captured` |
| Case state / decisions / audit / idempotency | **orchestrator Postgres** | the only state the system itself owns |
| Knowledge (manuals, SOPs, fault codes) | **pgvector corpus** | static internal docs; not operational data |

**Key correction vs. prior memory/docs:** the Salesforce **Hosted MCP is armed and answering live**
(`/copilot/tools` → `available:true` with real `FFCopilot_*` tools), and the deploy is **current**
(`/version` = HEAD). Earlier notes calling these "deferred/stale" are out of date.

---

## 4. AI Feature, Model, Prompt, and Provider Inventory

| AI feature | Where | Model(s) | Output | Authority over effects |
|---|---|---|---|---|
| **Option proposer** (reschedule slots + customer message) | `llm/proposer.py`, `graph/build.py:250` | Groq `openai/gpt-oss-120b` → Gemini `gemini-flash-latest` → deterministic floor | JSON `{options, confidence, explanation, customer_message}` | **None** — only proposes; policy re-validates every option |
| **Evidence-weighted confidence** | `llm/confidence.py` | n/a (deterministic blend of 5 factors) | `[0,1]` + breakdown | LLM slice is **clamped** (`min(self, prior)`) — can only lower |
| **Admin copilot** (NL ops/inventory questions) | `copilot/chat.py`, `/copilot/chat` | Groq tool-calling, temp 0, 5-step cap | grounded text answer + `toolsUsed` | **Read-only** — tools never mutate |
| **Vision/OCR of unit label** (FR-8/9) | `services/case_service.py:148` | **simulated** (`matchesAsset:True` hard-coded) | fake verification | n/a — mocked |

**Prompt-hardening already present (good):** the proposer system prompt tells the model it only
proposes; `parse_proposal` (`proposer.py:188`) **enforces** grounding in code — a `delay` archetype
can never carry a part, and any `partNo` not in the asset catalog is stripped. The model literally
cannot smuggle in authority. Generation is schema-constrained (Groq `json_object`, Gemini
`response_schema`). Temperature 0.2 (pipeline) / 0 (copilot). `max_tokens=1024`, `timeout=20s`.

**Provider fallback is a true ladder** (`proposer.py:230`): a 429 or any exception on one rung falls
to the next, and the deterministic floor **never fails or calls the network** — the decision loop
cannot be taken down by an LLM outage. The fallback output satisfies the same `Proposal` shape and is
re-validated by the same policy, so a degraded answer is still a safe answer.

---

## 5. MCP, Tools, Agents, and Permission Inventory

**Two distinct tool surfaces — the separation is deliberate and correct:**

1. **Deterministic Toolbox** (`tools/registry.py`) — the pipeline's surface. Tools are typed
   `read` (safe lookup, no ladder) or `action` (runs an authority ladder, returns a `ToolResult` that
   may **refuse**). The LLM may *call* an action but never decides its outcome. Raw Salesforce write
   access never reaches the model. Actions: `inventory.reserve`, `reschedule.confirm`,
   `salesforce.record_payment`, `commerce.*` (quote/order/link/capture/refund).

2. **Agentic MCP** (`mcp/client.py` + `copilot/chat.py`) — the copilot's surface. **Read-only tools
   only.** Salesforce Hosted MCP (8 `FFCopilot_*` read tools, OAuth2+PKCE, rotating refresh token
   persisted to `app_secrets`) + e-com MCP (`/api/mcp`, `list_products`/`get_stock`, **no auth**).
   The e-com MCP server deliberately does **not** expose `reserve`/`set-stock` (`apps/ecom/app/api/mcp/route.ts:7`).

**Bounded agency (good):** copilot has a hard 5-step cap (`_MAX_STEPS`), per-tool-result truncation
(`_TOOL_RESULT_CAP=2500`), temperature 0, single-turn (no history), and every model/tool failure is
caught and returned as a friendly message, never a 500 or an infinite loop.

**Gap:** copilot tool arguments and results are passed to/from the model with no schema-level
argument validation beyond what each MCP server enforces, and retrieved record content is fed back to
the model unsanitised (indirect-injection surface — see **AI-SEC-02**).

---

## 6. Data Stores, Sources of Truth, and Information Flows

- **Orchestrator Postgres** (`db/models.py`): `cases`, `idempotency_keys`, `audit_log`,
  `ai_decisions`, `app_secrets`. Generic `JSON` columns (portable to SQLite for tests). Tables created
  via `metadata.create_all` — **no migrations** (AI-DATA-01).
- **LangGraph checkpoints** in the same Postgres via `AsyncPostgresSaver` (durable); `InMemorySaver`
  offline. **No checkpoint TTL/prune** — closed cases keep rows forever (noted ceiling).
- **pgvector** `knowledge_chunks` (content-stable ids → incremental re-ingest).
- **e-com Supabase** `ecom_products` + `ecom_stock` with an atomic `ecom_reserve()` SQL function.
- **Tenancy:** the system is effectively **single-tenant** — one `correlationId` keyspace, no user
  accounts. There is no per-tenant isolation to breach, but there is also no access control on reads
  (every case is world-readable via `/cases` — see AI-SEC-01).

---

## 7. Integration and Critical Workflow Inventory

**The one end-to-end workflow:** `appointment.at_risk` event → load context (4 SF reads) → RAG
retrieve → evaluate SLA → LLM propose options → policy validate + confidence → (human gate if
risky/low-confidence/safety reason) → offer carousel over RCS → await customer tap → execute
(atomic reserve + reschedule) → [chargeable? quote → high-value human gate → payment link → await pay
→ settle + write to SF] → confirmation card → close. Every pause is a durable LangGraph `interrupt`.

Integrations audited request/response: Vonage (JWT RS256 send, HMAC webhook verify), Salesforce
(client-credentials OAuth, 401-refetch-once, Apex REST), e-com (HTTP + atomic reserve), Razorpay
(test-key-only boot guard, poll-confirm), Groq/Gemini (lazy SDK, schema output), Jina (embed+rerank),
Salesforce Hosted MCP (PKCE + rotating token).

---

## 8. Findings Summary by Severity and Priority

| ID | Title | Severity | Priority | Confidence | Status |
|---|---|---|---|---|---|
| **AI-SEC-01** | No authentication on the public, live-wired API (incl. `/sim/*`) | **Critical** | **P0** | Confirmed | Verified |
| **AI-SEC-02** | Unauthenticated copilot reaches live SF org; no injection defense; no rate limit | **High** | **P1** | High | Verified (exposure) |
| **AI-REL-01** | No retry/backoff tier before the DLQ (NFR-3 half-met) | **High** | **P1** | Confirmed | Verified |
| **AI-BEH-01** | Policy's time/hours/warranty checks are dead code — offered slot times are never validated | **High** | **P1** | Confirmed | Verified |
| **AI-BEH-02** | Customer-facing LLM message is unconstrained — the fence guards actions, not words (supersedes AI-OUT-01) | **High** | **P1** | High | Partially verified |
| **AI-BEH-03** | Confidence is a case-difficulty proxy, not an AI-correctness measure; no proposal-quality/faithfulness eval | **Medium** | **P2** | Confirmed | Verified |
| **AI-SEC-03** | Webhook/trigger secrets fail **open** when blank | **Medium** | **P1** | Confirmed | Verified |
| **AI-TEST-01** | No adversarial/injection/authz tests; no live e2e; coverage unmeasured | **Medium** | **P2** | Confirmed | Verified |
| **AI-DATA-01** | No DB migrations — schema change strands checkpoints/state | **Medium** | **P2** | Confirmed | Verified |
| **AI-SUP-01** | Deps floored not pinned; `uv.lock` gitignored; no CI/vuln scan | **Medium** | **P2** | Confirmed | Verified |
| **AI-OUT-01** | No moderation on customer-facing LLM text | **Medium** | **P2** | Medium | Partially verified |
| **AI-OBS-01** | Thin metrics; no alerting on FAILED/DLQ; no dashboards | **Low/Med** | **P2** | Confirmed | Verified |
| **AI-PERF-01** | `record_delivery_status` full `cases` table scan per callback | **Low** | **P3** | Confirmed | Verified |
| **AI-DOM-01** | No GST/tax line on quotes (India invoicing) | **Low** | **P3** | Confirmed | Verified |
| **AI-INT-01** | Payment poll-only + 3-min TTL; no inbound Razorpay webhook | **Low** | **P3** | Confirmed | Verified (by design) |

Totals: **1 Critical, 4 High, 5 Medium, 4 Low.** (AI-OUT-01 Medium is superseded by AI-BEH-02 High.)

> **Addendum 2026-10-22 — AI-behaviour findings.** The first pass under-weighted LLM-behaviour
> correctness vs. security/infra. On re-review (and a code challenge from the tech lead), three
> AI-behaviour findings were added: **AI-BEH-01** (dead policy time-checks), **AI-BEH-02** (unguarded
> customer message), **AI-BEH-03** (confidence is not a correctness measure). Detailed entries in §23A.

---

## 9. Model Quality, Safety, and Guardrails

- **Deterministic enforcement of the non-negotiable constraint:** the LLM never decides an effect.
  Enforced three ways — `parse_proposal` strips invented/illegal parts; `policy.validate_options`
  removes every illegal option; the confidence `llm` factor is clamped so the model can only *lower*
  confidence (`confidence.py:53`). This is the single strongest property in the system. **PASS.**
- **Instruction hierarchy:** the system prompt asserts "you only propose"; even if the model ignored
  it, the code fences hold. Good — prompt wording is *not* relied on as the boundary.
- **Safety floor:** `always_human_reasons = safety_risk,warranty_dispute` forces a human at **any**
  confidence (`policy.needs_human_for`). Risk-tiering is real.
- **Gap — output moderation (AI-OUT-01):** the model's `customer_message` is sent **verbatim** to a
  real customer over RCS with no moderation/toxicity/PII check. Inputs come from Salesforce (not the
  customer), so the injection surface is low, but there is no safety net on customer-facing text.
- **No regression/eval suite** for prompt/model/provider drift (AI-TEST-01). Models already drifted
  off the free tier once (`config.py:35` note) — a silent provider swap could change behaviour with
  no gate.

---

## 10. Context Limits, Output Validation, and Memory

- **Output validation: strong.** Schema-constrained generation + runtime `parse_proposal` that
  raises on missing keys (falls to next rung), coerces/clamps confidence to `[0,1]`, and defaults a
  missing `customer_message` to a warm template so the RCS body is never empty.
- **Context budgeting: adequate for the scope.** Proposer input is bounded (one asset, one
  technician, `k=3` knowledge snippets truncated to 160 chars, catalog parts list). Copilot caps each
  tool result at 2500 chars and steps at 5, with a free-tier-aware friendly error on 413/429.
- **No conversation memory.** Copilot is single-turn; the pipeline carries case state in LangGraph,
  not a chat history. No summarization/compression needed → **mostly N/A**, no context-drift risk.
- **Duplicate submissions** handled by idempotency keys (events + payments) — see §15.

---

## 11. RAG and Knowledge Quality

- **Pipeline:** Jina embeddings → pgvector cosine search (pool of 20) → Jina reranker → top-k
  (`rag/pgstore.py`). Content-stable chunk ids enable incremental re-ingest and clean deletion.
  Retrieval **fails soft** — a RAG error degrades to "no sources" and never breaks the decision
  (`graph/build.py:205`).
- **Grounding is used honestly:** retrieved score feeds the confidence `grounding` factor; sources
  are cited in the decision trace with scores.
- **Poisoning / indirect injection: low risk, unmitigated.** The corpus is internal static docs
  (manuals/SOPs), so poisoning needs write access to the corpus. Retrieved snippets are inserted into
  the proposer prompt without sanitisation, but the proposer's output is fully re-validated, so a
  poisoned snippet cannot create an illegal action — only a misleading `explanation`. **Low.**
- **No cross-tenant retrieval risk** (single-tenant, one shared corpus).

---

## 12. MCP, Tool Execution, and Agent Security

- **Read/write separation enforced server-side**, not by the model (Toolbox + e-com MCP omits
  mutating tools). **PASS.**
- **Least privilege:** copilot path is read-only; pipeline action tools validate args and run a
  ladder. Salesforce Apex uses `with sharing` and bind variables (no SOQL injection).
- **Credential handling:** SF Hosted MCP rotating refresh token is persisted to `app_secrets` and
  restored on boot (`main.py:94`) — a real correctness fix, well handled.
- **Gaps:**
  - **AI-SEC-02:** `/copilot/chat` is unauthenticated and live-armed. An anonymous caller can read
    the real org's data (within the integration user's scope) and spend Groq budget (no rate limit →
    cost-amplification / DoS).
  - **Indirect prompt injection** via record/field content returned by MCP tools is unmitigated; the
    model is told to "use ONLY the provided tools and never invent data," but that is prompt-level
    only. Blast radius is bounded to read-only data and token spend.
  - e-com MCP is intentionally unauthenticated ("POC admin service") — acceptable only while the data
    is fake and non-sensitive.

---

## 13. Orchestration and Workflow Reliability

**Strong.** Durable Postgres checkpointer; typed interrupts for every human/customer pause;
`resume_case` guards a **lost checkpoint** with a clean `409` instead of a 500 (`case_service.py:234`).
`execute` exits only via dynamic `Command(goto=...)` so no static edge double-fires. Stale-reply
guard (version in postback, NFR-6), lost-inventory-race recompute (NFR-5), high-value quote human
gate — all present and tested (`test_decision_flow`, `test_failures`, `test_spine_e2e`).

- **Crash-point behaviour:** a handler crash → FAILED case row (visible in `/cases`) **and** the
  message dead-letters for replay; the idempotency key is rolled back so a replay can reprocess
  (`case_service.py:199`). Terminal sends (confirmation) are best-effort so a send hiccup can't strand
  a committed reschedule.
- **Gaps:** no checkpoint TTL/prune; `reconcile` is **read-only** (lists stuck cases, no auto-heal);
  resume across a workflow-graph **version change** is not handled (a redeploy that renames nodes
  could strand in-flight checkpoints — untested).

---

## 14. External Integration and Contract Correctness

- **Salesforce:** client-credentials OAuth, `instance_url` from token, 401 → re-auth once
  (`salesforce.py:253`). Slot labels → UTC ISO before the wire (no floating datetimes). Reschedule
  updates a **minimal** record to dodge FSL field-access checks. Good contract discipline.
- **Vonage:** JWT RS256 send; webhook JWT HMAC-SHA256 + `payload_hash` verify (stdlib only); handles
  `to` as string-or-dict (a real past 500). RCS chip shapes carefully matched to avoid 422s.
- **Razorpay:** boot **refuses a non-`rzp_test_` key** (`razorpay.py:164`) — a live charge cannot
  fire from a POC. Capture is **idempotent** and the gateway (not the caller) is the authority on
  `captured`.
- **e-com:** atomic reserve is a row-locked `SELECT … FOR UPDATE` function — a lost race returns
  `false` (refusal, not oversell). Correct.
- **Gaps:** no wire-level contract tests against vendor sandboxes (mocks only); the Pub/Sub gRPC
  source is a **stub that raises** (`events/source.py:103`) — fine, because the HTTP-callout path is
  the chosen real trigger and the stub is gated off by default.

---

## 15. Event, Queue, and Distributed-System Reliability

- **Idempotency: two independent layers.** Envelope dedupe on `eventId`/`message_uuid`
  (`case_service.py:190,243`) + gateway-level idempotent capture. Payment auto-pay uses a stable
  `autopay-{ref}` key. **PASS** (NFR-2).
- **DLQ:** durable `events` queue with `x-dead-letter-exchange`; peek (non-consuming) + replay. FAILED
  cases are visible, not silent.
- **AI-REL-01 (the real gap):** a handler exception nacks **straight** to the DLQ with no
  retry/backoff tier (`broker.py:80`). A transient Salesforce/DB blip dead-letters immediately and
  needs a manual `POST /sim/dlq/replay`. NFR-3's "retry → backoff → DLQ" is only half-built.
- **Single in-process consumer** (`prefetch=10`); no backpressure/concurrency test; no alert on DLQ
  depth or consumer lag (AI-OBS-01). Replay is bounded to 20/call.

---

## 16. Consequential Actions and Business Invariants

| Invariant | Enforcement | Verdict |
|---|---|---|
| Model never sets the amount | Price book / e-com price only; `build_quote` computes it (`service.py:42`) | **PASS** |
| No double-charge | Envelope dedupe + idempotent capture (2 layers) | **PASS** (unit-tested; **not** verified in live Razorpay) |
| No oversell | Atomic `ecom_reserve` / `FakeInventory.reserve` | **PASS** |
| High-risk needs a human | `commerce_high_value_paise` gate + `always_human_reasons` + confidence gate | **PASS** |
| Live charge can't fire from POC | Non-test-key boot refusal | **PASS** |
| External state matches internal | Payment written back to SF (best-effort, idempotent upsert) | **PARTIAL** — SF write is best-effort; a failed write logs to the trace but the case still closes |
| Money precision | Integer paise everywhere | **PASS** |

- **AI-DOM-01:** quotes are **part + flat labour only** — **no GST/tax line**. Fine for a demo,
  blocks real Indian invoicing.
- **Approval-at-execution:** the high-value human gate approves the quote, then payment proceeds; a
  change of authorization between approval and capture is not re-checked (low risk at POC scope).
- **Not verified live:** the full money lifecycle (link → pay → capture → refund) has **not** been
  run end-to-end in the Razorpay test sandbox during this audit (deliberately not fired).

---

## 17. Privacy, Identity, and Authorization

- **AI-SEC-01 (Critical):** there is **no authentication or authorization anywhere** on the
  orchestrator. Live, unauthenticated reads confirmed: `/cases` returns every case including customer
  **name + phone** (`[{"...","customer":{"phone":"+91-...","name":"Priya N..."}}]`), `/copilot/tools`,
  `/dlq`, `/reconcile`. `/sim/*` is mounted unauthenticated (`GET` → 405, proving reachability) — a
  `POST` would fire at-risk events, toggle `/sim/fault` (Salesforce-down), resume/poison any case, or
  drive the copilot. CORS (`main.py:171`) only restricts browsers; `curl`/server clients ignore it.
- **Data is fake** (per `CLAUDE.md` "no real data, ever"), which contains the *privacy* blast radius
  today — but the **integrity/abuse** blast radius is full: anyone can drive the pipeline and the real
  Salesforce/Razorpay-test wiring behind it.
- **Secrets:** none are git-tracked (`.env`, `*.key` gitignored; verified via `git ls-files`).
  `/health/deps` and the health module scrub error details to avoid leaking a DB URL/password
  (`health.py:48`). Good.
- **AI-SEC-03:** `verify_vonage_jwt` and the SF-hook secret check both **return true / skip when the
  secret is blank** (`webhooks/routes.py:43,131`). Safe default is *skip*, not *fail-closed* — on a
  public URL a misconfigured blank secret silently disables verification.

---

## 18. Performance, Capacity, and Cost

- **Latency:** no measurements taken (no load test exists). Design is bounded: one `propose()` + one
  `retrieve()` per decision, deterministic hot path, `llm_timeout_s=20`.
- **Cost controls:** copilot result cap + step cap guard Groq free-tier token spend **per call**, but
  there is **no rate limit**, so unauthenticated `/copilot/chat` is a cost-amplification vector
  (AI-SEC-02). `/health/deps` deep pings are cached ~30 s to avoid hammering/billing vendors.
- **AI-PERF-01:** `record_delivery_status` loads **all** `Case` rows to find one by `message_uuid`
  (`case_service.py:127`, ponytail-flagged) — O(n) per delivery callback; add a `message_uuid` index/
  column before volume.
- **No concurrency/backpressure testing**; single consumer; checkpoint rows grow unbounded.

---

## 19. Testing and AI Evaluation

- **129 deterministic tests pass; ruff clean.** Coverage is genuinely good on the hard parts: policy,
  idempotency, failures/DLQ, commerce, RAG, confidence calibration (`test_confidence` is the explicit
  calibration contract), MCP client, Salesforce/inventory REST, SF hook, availability slots, copilot,
  spine e2e.
- **AI-TEST-01 gaps:** **zero** adversarial / prompt-injection / jailbreak tests; **zero** authz /
  access-control tests (because there is no authz); no cross-tenant tests (single-tenant); no live
  end-to-end against vendor sandboxes; no LLM-output regression/eval dataset; coverage % unmeasured.
  Tests are all offline/deterministic — none exercise a live model or provider.

---

## 20. Observability and Operational Readiness

- **Present and live:** Logfire tracing (auto-instrumented, wrapped so it can never crash the app),
  Prometheus `/metrics`, structlog with a `correlation_id` contextvar threaded through
  event→case→audit→decision, `/health` + `/health/deps` (shallow + deep), `/version`, `/reconcile`,
  `/dlq`, and FAILED cases visible in `/cases`. An auditor **can** reconstruct a case end-to-end.
- **AI-OBS-01 gaps:** metric taxonomy is thin (`events_processed`, `events_duplicate`, `cards_sent`,
  `sms_fallbacks`, `dlq_replays`) — **no** latency histograms, LLM token/cost metrics,
  provider-fallback counter, or decision-outcome breakdown. **No alerting** on FAILED-case or DLQ
  growth. No Grafana dashboards (provisioning files exist in `infra/`, unused in the live deploy).

---

## 21. Deployment, Lifecycle, and Recovery

- **Deploy is current** (`/version` = HEAD `26dcc04`) — the prior audit's stale-deploy blocker is
  **resolved**.
- **AI-SUP-01:** `uv.lock` is **gitignored** (`.gitignore:11`) → builds are not reproducible; deps are
  floored (`>=`) not pinned; there is no CI (no pytest/ruff gate on push), no `render.yaml`, no
  Dependabot/`pip-audit`. Supply-chain + reproducibility risk once money is real.
- **AI-DATA-01:** no Alembic/migrations — `create_all` only. A schema change will strand the durable
  LangGraph checkpoints and case state in a shared environment.
- **No kill-switch / feature-flag** to disable the copilot or the live sends independently at runtime
  (arming is env-only, needs a redeploy). No documented rollback runbook.

---

## 22. Domain-Specific Risks

- **Commerce/payments:** pricing authority is code (good); **no GST** (AI-DOM-01); refund path exists
  and is idempotent but untested live; reconciliation is read-only.
- **Communication (RCS):** single test device; India/Android only (iOS silently fails — accepted);
  real SMS failover logic exists but the real send is gated; no consent/opt-out handling (POC).
- **Enterprise copilot:** least-privilege read-only is correct, but it is unauthenticated and reaches
  the real org (AI-SEC-02).
- **Vision/OCR (FR-8/9):** simulated — any "photo verified" result is hard-coded `True`; must not be
  trusted as a real check.

---

## 23. Detailed Findings with Evidence and Recommendations

### AI-SEC-01 — No authentication on the public, live-wired API · Critical · P0 · Confirmed · Verified
- **Where:** `app/main.py:177-180` (routers mounted unconditionally), `app/sim/routes.py` (all
  `/sim/*`), `app/api/routes.py` (`/cases`, `/copilot/*`, `/dlq`, `/reconcile`). CORS only:
  `main.py:171`.
- **Evidence (live, read-only):** `GET /cases` returned real case JSON incl. `customer.name` +
  `customer.phone`; `GET /copilot/tools` → `available:true`; `GET /dlq` → readable; `GET /sim/fault`
  and `GET /sim/appointment-at-risk` → `405` (routes mounted, unauthenticated; `POST` not fired).
- **Scenario:** an anonymous attacker `POST`s `/sim/fault {salesforceDown:true}` (pipeline starts
  dead-lettering), fires fake at-risk events, resumes/poisons any case, reads all case data, or drives
  the copilot against the real org — all with no credential.
- **Impact:** unauthorized consequential actions + data read on a public endpoint wired to live
  Salesforce/Razorpay-test/copilot. Release-blocking.
- **Fix:** put the whole API behind an auth gate (API key or JWT) at the ASGI/middleware layer;
  split `/sim/*` behind a separate, non-production flag or stronger gate; restrict `/cases`/`/dlq`/
  `/reconcile`/`/copilot/*` to operator identities.
- **Verify:** every route returns `401` without a credential; `/sim/*` is unreachable in the
  production profile; an authz test suite covers each route.

### AI-SEC-02 — Unauthenticated copilot reaches live SF org; no injection defense; no rate limit · High · P1
- **Where:** `/copilot/chat` (`api/routes.py:124`), `copilot/chat.py`, `mcp/client.py`.
- **Scenario:** anonymous `POST /copilot/chat` reads real org data within the integration user's scope
  and burns Groq tokens (no rate limit → cost DoS). Malicious content in a returned SF/e-com record
  can steer the model (indirect prompt injection); blast radius is read-only + token spend.
- **Fix:** gate behind AI-SEC-01's auth; add per-identity rate limiting + a daily token budget; treat
  tool output as untrusted (don't let it change tool-selection policy); consider an allowlist of
  copilot tools.
- **Verify:** unauthenticated call → 401; a rate-limit test; an injection test set that proves a
  poisoned record cannot exfiltrate beyond the read scope.

### AI-REL-01 — No retry/backoff before the DLQ · High · P1 · Confirmed
- **Where:** `app/queue/broker.py:80` (`nack(requeue=False)` on any exception).
- **Scenario:** a 2-second Salesforce/DB blip dead-letters the event immediately; recovery needs a
  manual `POST /sim/dlq/replay`.
- **Fix:** add a bounded retry-with-backoff tier (aio-pika delayed-retry / a retry queue with TTL)
  before the nack; distinguish transient vs permanent errors.
- **Verify:** inject a transient failure → event retries N times with backoff, then DLQs; a permanent
  failure DLQs immediately.

### AI-SEC-03 — Webhook/trigger secrets fail open when blank · Medium · P1 · Confirmed
- **Where:** `app/webhooks/routes.py:43` (`if not secret: return True`), `:131` (SF-hook skip).
- **Fix:** in the production profile, treat a blank signature/hook secret as a **fatal boot error**
  (fail-closed), not a skip.
- **Verify:** a production boot with a blank secret aborts; a forged webhook with a wrong signature is
  rejected.

### AI-TEST-01 — No adversarial/authz/eval tests; no live e2e · Medium · P2 · Confirmed
- **Fix:** add (a) an authz test per route once auth lands; (b) a prompt-injection set for proposer +
  copilot; (c) an LLM-output regression dataset gated in CI; (d) one live sandbox e2e (SF + Razorpay
  test) run manually before each pilot.

### AI-DATA-01 — No DB migrations · Medium · P2 · Confirmed
- **Where:** `db/models.py:4` (create_all), `graph/checkpointer.py:52` (`setup()`).
- **Fix:** add Alembic (or equivalent) before any schema change ships to a shared environment.

### AI-SUP-01 — Deps floored, `uv.lock` gitignored, no CI/scan · Medium · P2 · Confirmed
- **Where:** `.gitignore:11`; `apps/orchestrator/pyproject.toml` (`>=` ranges).
- **Fix:** commit `uv.lock`, pin ranges, add CI (pytest + ruff on push) + `pip-audit`/Dependabot.

### AI-OUT-01 — No moderation on customer-facing LLM text · Medium · P2 · Partially verified
- **Where:** `proposer.py` `customer_message` → `graph/build.py:368` body → Vonage send verbatim.
- **Fix:** add a lightweight output check (length/PII/toxicity) before sending model-written text to a
  real customer; keep the deterministic template as the safe fallback.

### AI-OBS-01 — Thin metrics, no alerting · Low/Med · P2 · Confirmed
- **Fix:** add latency/token/cost/provider-fallback/decision-outcome metrics and alerts on
  FAILED-case + DLQ-depth growth; stand up the existing Grafana provisioning.

### AI-PERF-01 — Full `cases` scan per delivery callback · Low · P3 · Confirmed
- **Where:** `services/case_service.py:127`.
- **Fix:** index/store `message_uuid` and look up directly.

### AI-DOM-01 — No GST/tax on quotes · Low · P3 · Confirmed
- **Where:** `commerce/service.py:42` (part + labour only).
- **Fix:** add a tax line before real invoicing.

### AI-INT-01 — Payment poll-only + 3-min TTL · Low · P3 · By design
- **Where:** `payment_poller.py`, `config.py:64`. A payment just after TTL expiry needs a manual
  `/sim/payment`. Acceptable for POC; add an inbound Razorpay webhook for production.

---

## 23A. AI-Behaviour Findings (added 2026-10-22)

These are the "how the AI itself behaves, and how that costs money in the real world" findings.

### AI-BEH-01 — Policy's time/hours/warranty checks never fire; slot times are unvalidated · High · P1 · Confirmed · Verified
- **Where:** `app/policy/__init__.py:42` (`cand.get("startMinutes")`), `:45` (`cand.get("hour")`),
  `:48` (`cand.get("requiresWarranty")`). Candidate construction: `app/graph/build.py:250-301`
  (fallback/LLM options carry only `slotId/label/technician/note/requiredSkill?/partNo?`; real-FSL
  options add `start/end`). Grep confirms **no code anywhere** sets `startMinutes`, `hour`, or
  `requiresWarranty` on a candidate.
- **Consequence:** on the fallback/canned/LLM path, policy validates only `skill` + `inventory` +
  terminal `state`. The **SLA-window, working-hours, and warranty-requirement checks are dead
  branches** — so a slot whose time breaches the SLA or falls outside 09:00–18:00 is offered and
  booked with no policy objection. A malformed LLM time (e.g. `25:00`) instead crashes to the DLQ
  (`salesforce.py:176` `replace(hour=25)` → ValueError).
- **Mitigations present:** when real Field Service slots are used (`slotsAuthority="scheduler"`), SF's
  own engine honours working hours, so the real-FSL path is safe; the canned fallback labels are
  hard-coded sane. The exposure is the **live-LLM + FSL-returns-nothing** path.
- **Real-world cost:** a customer booked into a past or after-hours slot; a technician dispatched
  outside working hours; silent SLA breaches. The "deterministic policy decides" guarantee is
  incomplete for time.
- **Fix:** derive `startMinutes`/`hour` from each candidate's `start`/`label` in `generate_options`
  (or add an explicit time-validity check in `policy.validate_options`) so the time checks actually
  run on every offered slot; reject past/out-of-hours/SLA-breaching slots before the carousel.
- **Verify:** a test that feeds an out-of-hours / past / SLA-breaching slot and asserts policy removes
  it; a test that a malformed time is rejected cleanly (not a DLQ crash).

### AI-BEH-02 — Customer-facing LLM message is unconstrained; the fence guards actions, not words · High · P1 · High
- **Where:** `app/llm/proposer.py` (`customer_message`), `app/graph/build.py:368` (body), Vonage send.
- **Consequence:** the policy engine validates slots/parts, never the prose. The model's message is
  sent to a real customer verbatim. It can promise outcomes the decision did not authorize — "free
  under warranty", a specific ETA, a compensation — while the actual path is chargeable or different.
- **Real-world cost:** broken promises, wrong customer expectations, trust and potential legal
  exposure — a cost the action-level fence does not prevent.
- **Fix (ponytail):** a deterministic pre-send check — cap length, strip control chars, and gate
  obvious unauthorized promises (e.g. "free"/"no charge" when the decision is chargeable; a concrete
  time/price not drawn from the decision); fall back to the warm template on fail. Supersedes
  AI-OUT-01 and raises its severity.
- **Verify:** a test that a chargeable decision cannot emit a "free"/"no charge" customer message.

### AI-BEH-03 — Confidence is a case-difficulty proxy, not an AI-correctness measure · Medium · P2 · Confirmed
- **Where:** `app/llm/confidence.py` (weights: prior 0.40, headroom 0.20, grounding 0.15, data 0.10,
  llm 0.15 — and the `llm` factor is clamped to `min(self, prior)`).
- **Consequence:** ~85% of the score is deterministic case difficulty; the model's own rating is 15%
  and can only lower. An easy, well-grounded, APPROVED delay **always** clears the 0.7 human-gate
  regardless of whether the AI's actual slots/message are good. Nothing evaluates proposal quality or
  whether the explanation/message is faithful to the retrieved manuals.
- **Real-world cost:** overtrust — a poor-but-easy case auto-sends to the customer without a human,
  and there is no quality/faithfulness signal to catch a bad-but-legal proposal. Pairs with the
  model-drift risk (AI-TEST-01): a silent provider/model swap changes behaviour with no eval gate.
- **Fix:** add a lightweight groundedness/faithfulness check (does the explanation cite a retrieved
  source? does the message avoid unsupported claims?) and an offline eval set gated in CI; consider
  surfacing a separate "AI-quality" signal distinct from case-difficulty confidence.
- **Verify:** an eval dataset with pass/fail thresholds run in CI on any prompt/model change.

---

## 24. Missing Safeguards and Implementation Gaps

1. Authentication/authorization — **entirely absent** (AI-SEC-01).
2. Rate limiting / token budgets — absent (AI-SEC-02).
3. Retry/backoff tier before DLQ (AI-REL-01).
4. Fail-closed secret verification in production (AI-SEC-03).
5. DB migrations (AI-DATA-01) and checkpoint retention/prune.
6. Reproducible builds + CI + vuln scan (AI-SUP-01).
7. Output moderation on customer-facing text (AI-OUT-01).
8. Alerting + richer metrics (AI-OBS-01).
9. Adversarial/eval/authz test coverage (AI-TEST-01).
10. Real vision/OCR (currently simulated), real GST, inbound payment webhook.

---

## 25. Verification Results and Unverified Checks

| Check | Result |
|---|---|
| `uv run pytest -q` | **129 passed** (26.4 s) |
| `uv run ruff check .` | **All checks passed** |
| Live `/version` | `26dcc04` = HEAD (**deploy current**) |
| Live `/health`, `/health/deps` (shallow) | `ok`; postgres 297 ms, rabbitmq ok, logfire ok, vonage **armed** |
| Live `/cases` (unauth) | real cases incl. customer name + phone — **exposure confirmed** |
| Live `/copilot/tools` (unauth) | `available:true` — SF Hosted MCP **armed live** |
| Live `/dlq` (unauth) | readable, depth 0 |
| `GET /sim/*` | `405` (mounted, unauthenticated; **not** POSTed) |
| Git-tracked secrets | **none** (`.env`, `*.key` gitignored) |
| **Unverified (deliberately):** deep `/health/deps`, live Razorpay money lifecycle, real RCS/SMS send, copilot answer quality, provider failover under real 429, concurrency/load, injection resistance | **NOT VERIFIED** |

---

## 26. Prioritized Remediation Roadmap

- **Before any pilot (P0/P1):** AI-SEC-01 (auth gate + split `/sim`), AI-SEC-02 (gate copilot + rate
  limit), AI-REL-01 (retry tier), AI-SEC-03 (fail-closed secrets).
- **Before real money/customers (P2):** AI-DATA-01 (migrations), AI-SUP-01 (lock+CI+scan),
  AI-OUT-01 (output check), AI-TEST-01 (authz + injection + one live e2e), AI-OBS-01 (alerts).
- **Backlog (P3):** AI-PERF-01, AI-DOM-01 (GST), AI-INT-01 (payment webhook), real vision/OCR,
  checkpoint prune, workflow-version migration safety.

---

## 27. Release Gate Checklist

| Gate | Status |
|---|---|
| Critical / P0 findings resolved | **FAIL** (AI-SEC-01 open) |
| AI outputs validated before consequential use | **PASS** |
| Guardrails independently (deterministically) enforced | **PASS** |
| Private data + authorization boundaries verified | **FAIL** (no authz) |
| RAG / memory isolation | **N/A** (single-tenant, internal corpus) |
| MCP / tool permissions verified | **PARTIAL** (read/write split good; access unauthenticated) |
| Primary + fallback provider behaviour tested | **PARTIAL** (ladder unit-tested; not live) |
| Input/output/token/cost budgets enforced | **PARTIAL** (per-call caps; no rate limit) |
| Workflows recover from process/dependency failure | **PARTIAL** (DLQ+resume yes; retry tier no) |
| Duplicate events / side-effects safe | **PASS** |
| Payments independently verified (sandbox) | **NOT VERIFIED** |
| Queues/retries/DLQ/reconciliation tested | **PARTIAL** (no retry tier; reconcile read-only) |
| External API/webhook contracts verified | **PARTIAL** (mocks; fail-open secrets) |
| Evaluation/regression suites passing | **PARTIAL** (129 functional; no AI-eval) |
| Monitoring + actionable failure visibility | **PARTIAL** (traces yes; alerts no) |
| Deployment/config/rollback safeguards | **PARTIAL** (current deploy; no migrations/CI/rollback) |
| Residual risks documented + authorized | **PASS** (this report + root audit) |

---

## 28. Residual Risks, Assumptions, and Limitations

- **Assumption:** all customer/asset/payment data is fake (per `CLAUDE.md`). If any real data is ever
  loaded, AI-SEC-01 immediately becomes a privacy breach, not just an abuse vector.
- **Limitation:** no live money/message/injection/load testing was performed (would create real
  effects); those gates are **NOT VERIFIED**, not passed.
- **Limitation:** the Salesforce Apex SOQL assumes a specific org data model (`FieldFlowRest.cls`
  header A1–A4); correctness depends on the org matching those assumptions.
- **Accepted POC corners (per `CLAUDE.md`), not scored as defects:** simulated OCR, placeholder PDF,
  single RCS device, poll-only payment, gRPC Pub/Sub stub, no Grafana. Each sits behind a clean seam.

---

## 29. Appendix: Commands, Test Outputs, and Evidence

```bash
# Local (from apps/orchestrator, after `uv sync --extra dev`)
uv run pytest -q          # → 129 passed in 26.41s
uv run ruff check .       # → All checks passed!

# Live, read-only (no side effects)
B=https://fieldflow-ai-w6bm.onrender.com
curl -s "$B/version"              # {"commit":"26dcc04...","branch":"main"}
curl -s "$B/health/deps"          # status ok; postgres/rabbitmq/logfire ok; vonage armed
curl -s "$B/cases"                # real cases incl. customer name+phone  (AI-SEC-01)
curl -s "$B/copilot/tools"        # available:true  (SF Hosted MCP armed live)
curl -s "$B/dlq"                  # available:true, depth 0
curl -s -o /dev/null -w '%{http_code}' "$B/sim/fault"   # 405 (mounted, unauth; POST not fired)

# Git
git ls-files | grep -E '\.env$|private\.key'   # → only .env.example (no secrets tracked)
grep -n 'uv.lock' .gitignore                   # → uv.lock is gitignored (AI-SUP-01)
```

*End of report. No application code, prompts, policies, config, or data were modified.*
