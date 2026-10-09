# Durable checkpointer (Postgres on Supabase)

## Task

- **Name:** Durable LangGraph checkpointer + defensive resume
- **Status:** shipped
- **Started:** 2026-10-09
- **Last updated:** 2026-10-09

## What you asked for

- Clicking **Approve** on a paused case 500'd with `KeyError: 'event'`. Find the root cause and fix.
- Decide whether paused cases should live in memory or a durable store, given a real system could
  have **~5000 long-running cases** at once (memory worry).
- Judge the options the ponytail way: is Postgres right, or is it over-engineering? Would Redis
  (Upstash) be simpler? If Redis is the same complexity, go Postgres.

## Open questions

1. **Scope of the fix — guard only, SQLite, or Postgres?**
   My recommendation: guard **+** durable store. **Your answer:** Both, Postgres — "the Postgres
   entire setup is already done and working."
2. **Redis/Upstash instead of Postgres?**
   My recommendation: no — Redis brings the *same* wiring complexity **plus** a new service to run,
   while Postgres reuses the Supabase we already run and sits next to the Case row. **Your answer:**
   if same complexity, go Postgres. (It is → Postgres.)

## Plan

**Root cause (confirmed in code):** the checkpointer — the store that holds a paused graph's state
so it can resume — was `InMemorySaver`, which keeps state **only inside the running process**. The
Case row persists in the DB, so `/cases` still lists the case after a restart, but the in-memory
checkpoint is gone. Clicking Approve calls `resume_case` → `graph.ainvoke(Command(resume=...))` →
with no saved state the graph re-enters `load_case` with an empty state → `state["event"]` →
`KeyError` → 500.

**Two independent parts:**
- **A. Defensive resume guard** — a lost/expired checkpoint should fail cleanly, not 500. Correct
  even with a durable store (checkpoints can still be pruned/expired).
- **B. Durable checkpointer** — swap `InMemorySaver` → `AsyncPostgresSaver` on the Supabase Postgres
  we already run, so paused cases survive a restart and state lives in the DB (not RAM).

**Files touched:**
- `apps/orchestrator/pyproject.toml` — add `langgraph-checkpoint-postgres`, `psycopg[binary]` (v3).
- `app/graph/checkpointer.py` — keep `make_checkpointer()` (in-memory, for tests/offline); add
  `checkpointer_scope(settings)`: Postgres when the URL is Postgres, else in-memory; `.setup()` runs
  once (idempotent DDL creating the checkpoint tables).
- `app/main.py` — open `checkpointer_scope` for the app's lifetime in `lifespan`, build the graph
  inside it. Also set the **Windows SelectorEventLoop** policy (psycopg3 async refuses the default
  ProactorEventLoop); no-op on Linux.
- `app/services/case_service.py` — the resume guard: if `graph.aget_state(config).values` is empty,
  raise `HTTPException(409)` instead of re-running the graph. One guard covers approve / reply /
  payment (all route through `resume_case`).

**Rejected alternatives:**
- *Custom in-memory cache with eviction/TTL* — reinvents a database and still loses state on
  restart. Over-engineering.
- *SQLite saver* — durable + survives restart, but single-process and a second store to run when we
  already run Postgres.
- *Redis / Upstash saver* — same wiring complexity as Postgres **plus** a new managed service.

## Tasks

- [x] Add `langgraph-checkpoint-postgres` + `psycopg[binary]` via `uv`.
- [x] `checkpointer_scope` (Postgres path + in-memory fallback + `.setup()`).
- [x] Wire into `lifespan`; Windows event-loop fix.
- [x] Resume guard → 409 on lost/expired checkpoint.
- [x] 72 tests green; ruff clean.
- [x] Verified live against Supabase: connect + `.setup()` (4 tables), and a full
      pause → new-saver-instance (restart) → resume with no `KeyError`.
- [ ] *(junior, follow-up)* an automated restart-durability test in the suite.
- [ ] *(later, real volume)* checkpoint retention/TTL — prune CLOSED/REJECTED cases.

## Updates

- **2026-10-09.** Shipped A + B. `database_url` is already Supabase (`postgresql+asyncpg`, session
  pooler :5432). The saver talks psycopg3 on a `postgresql://…?sslmode=require` DSN (driver suffix
  stripped). `.setup()` created `checkpoints`, `checkpoint_blobs`, `checkpoint_writes`,
  `checkpoint_migrations`. Live proof: a case paused at `human_approval` under saver instance A was
  resumed by a fresh saver instance B (= a restart) straight through to `OPTIONS_SENT`. Context docs
  in `context/02-orchestration-and-policy.md` still say "Step 1 uses an in-memory checkpointer" —
  **stale, flagged, awaiting your go to update.**

## Explanation

**1. What changed.** Paused cases now save their state to Postgres (Supabase) instead of process
memory, and a resume with no saved state returns a clean 409 instead of crashing.

**2. Why it was needed.** A recovery case waits — hours or days — for a human or a customer. With
in-memory state, any restart/deploy/crash wiped every paused case; approving one afterward 500'd.
At ~5000 in-flight cases in-memory also costs ~0.5–2.5 GB of never-freed RAM. Durability is the
requirement for a human-in-the-loop flow, not a nice-to-have.

**3. How it works, step by step.**
- On boot, `lifespan` opens `checkpointer_scope`. URL is Postgres → it opens one psycopg3 connection
  and runs `.setup()` (creates the 4 checkpoint tables if absent), then builds the graph on that
  saver.
- A case runs until an `interrupt` (human approval / customer reply / payment). LangGraph writes the
  full state to the checkpoint tables, keyed by `thread_id = correlationId`.
- A restart drops the process but **not** the rows. On resume, `resume_case` first calls
  `aget_state`. If there's saved state, it resumes on the checkpoint. If not (lost/expired), it
  raises 409 — the case can't be resumed; start a fresh one.

**4. Files / functions changed.**
- `checkpointer.py` — `make_checkpointer()` (in-memory, tests/offline); `_psycopg_dsn()` (SQLAlchemy
  URL → psycopg DSN + TLS); `checkpointer_scope()` (async CM picking Postgres vs in-memory, running
  `.setup()`).
- `main.py` — Windows SelectorEventLoop policy; `lifespan` builds the graph inside
  `checkpointer_scope`.
- `case_service.py::resume_case` — the `aget_state` guard → 409.

**5. Important decisions.** Postgres over in-memory/SQLite/Redis (reuses Supabase, sits by the Case
row, no new service). Kept the in-memory saver for tests (no Supabase in CI). One guard at the
resume boundary, not per-route. Windows loop policy because psycopg3 async can't use the default
Windows loop.

**6. Tests / verification.** `uv run pytest -q` → **72 passed**; `ruff check` clean on the changed
files. Live Supabase: `setup()` created all 4 tables; a pause→restart→resume round-trip resumed to
`OPTIONS_SENT` with no `KeyError` (test checkpoints deleted after).

**7. Edge cases & limitations.** No retention/TTL yet — checkpoints accumulate (prune later). A
genuinely lost/expired checkpoint returns 409, not a magic re-hydrate — intentional, since the full
intermediate state (options, version) can't be rebuilt from the Case row alone. Supabase **session**
pooler (:5432) supports the prepared statements psycopg uses; the **transaction** pooler (:6543)
would need `prepare_threshold=0` (the saver already sets this). SelectorEventLoop on Windows caps at
512 sockets / no subprocess — irrelevant for the POC, and prod is Linux.
