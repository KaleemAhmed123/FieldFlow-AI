# Build Step 13 — e-com inventory service (the separate inventory source)

## 1. Task

- **Name:** build the **e-com inventory service** — the separate source from Decision A that owns
  product **image + price + stock** — as a Next.js + Supabase app with an admin dashboard, a
  read/reserve HTTP API, and an MCP server. Swap the orchestrator's `FakeInventory` for a real
  `RestInventory` adapter behind the same interface.
- **Status:** shipped + **LIVE-VERIFIED** 2026-10-11 against a new Supabase project (`fieldflow-ecom`):
  86 parts seeded, reserve race confirmed on real Postgres. Orchestrator `ECOM_API_URL` wiring is the
  user's last step.
- **Started:** 2026-10-11 · **Last updated:** 2026-10-11.

## 2. What you asked for

- Build **#3** from the front-door menu: the e-com service (Next.js + Supabase, admin dashboard +
  the NFR-5 grab-part knob) **+ its MCP server**.
- Four choices you locked (overriding two of my recommendations — noted):
  - **Scope:** full — service + `RestInventory` adapter **+ the e-com MCP server now** (not deferred).
  - **Data backing:** **real Supabase now** (not mock-first).
  - **Dashboard:** minimal operator view.
  - **Seed:** reuse the orchestrator's `catalog.json`.
- House rules honoured: keep the orchestrator's tests green, mock-first on the orchestrator side,
  update `playbook.md` + this Explanation in the same change, don't touch `context/**` beyond notes.

## 3. Open questions (answered)

| # | Question | Your answer |
|---|----------|-------------|
| Q1 | Scope — defer the MCP server? | **No — build it now.** |
| Q2 | Data backing | **Real Supabase now.** |
| Q3 | Dashboard | **Minimal operator view.** |
| Q4 | Seed source | **Reuse `catalog.json`.** |
| Q5 | Which Supabase project? | **A new, separate Supabase project** (user, 2026-10-11) — true separation of concerns, matches Decision A ("a separate source") and real-world architecture (independent creds, backups, blast radius). Code is identical to reuse; only `apps/ecom/.env.local` differs. Tables keep the `ecom_` prefix regardless. |

## 4. Plan

- The orchestrator talks to inventory through one tiny interface (`InventoryTools`: `find_part` +
  `reserve`). The e-com service swaps in behind it via a new `RestInventory(ECOM_API_URL)` adapter —
  the same **fake-unless-armed** convention as `build_vonage` / `build_gateway`. So the graph, the
  policy ladder and every test are untouched; only one wiring line in `main.py` changes.
- The e-com service is a standalone Next.js app (`apps/ecom/`), Vercel-bound, Supabase-backed. It
  holds the only Supabase creds; the orchestrator reaches it over HTTP.
- **Rejected:** exposing `reserve`/`set-stock` over MCP (breaks the guardrail — LLM-invoked
  inventory writes); a storefront (admin-only per Decision A); mocking Supabase (you chose real).

## 5. Tasks

- [x] `RestInventory` adapter + `build_inventory` factory behind `InventoryTools`
      (`apps/orchestrator/app/tools/inventory.py`).
- [x] Wire it in `main.py`; add `ecom_api_url` to `config.py` + `.env.example`.
- [x] Adapter test (`tests/test_inventory_rest.py`, httpx.MockTransport) — **94 tests green, ruff clean.**
- [x] Supabase schema + atomic `ecom_reserve` function (`apps/ecom/supabase/schema.sql`).
- [x] Seed from `catalog.json` (`apps/ecom/scripts/seed.mjs`).
- [x] Read/reserve/set API routes + the MCP server (`apps/ecom/app/api/**`).
- [x] Minimal admin dashboard — product grid + stock edit + Grab knob (`apps/ecom/app/*`).
- [x] `next build` green (types + routes verified).
- [x] **User:** new `fieldflow-ecom` Supabase project, `.env.local`, `schema.sql`, `pnpm seed`,
      `pnpm dev` — done 2026-10-11; live API round-trip verified (above).
- [x] **User:** set `ECOM_API_URL=http://localhost:3000` in `apps/orchestrator/.env` — done
      2026-10-11. Verified: orchestrator boots `inventory.rest`, uses `RestInventory`, live-read
      PCB-492 → `Noida:1` from Supabase. **Step 13 complete, end-to-end.**

## 6. Updates

- **2026-10-11 (later)** — Decision on Q5: use a **separate Supabase project** for e-com (not the
  orchestrator's), for clean separation of concerns / real-world fidelity. No code change — only
  `apps/ecom/.env.local` points at the new project. Steps are in `playbook.md` §3i.
- **2026-10-11** — Built end to end. Orchestrator adapter + factory + test land first (94 green).
  E-com app scaffolded (Next 15.5 + React 19 + @supabase/supabase-js 2 + mcp-handler 1.1 + zod).
  `next build` compiles clean. Live DB run gated on the user's Supabase creds (the one honest gap).

## 7. Explanation (plain-English walkthrough)

### 7.1 What changed

Two things. **(a)** The orchestrator gained a real inventory adapter: a `RestInventory` class that
reads and reserves stock over HTTP, plus a `build_inventory` factory that picks it automatically
when `ECOM_API_URL` is set (otherwise the old in-memory `FakeInventory`). **(b)** A brand-new
standalone app, `apps/ecom/` — a Next.js + Supabase service that *is* the inventory: a database, a
seed, an admin dashboard, a read/reserve API, and an MCP server.

Term notes (first use): **adapter** = a small class that talks to a real outside system behind the
same interface our fakes use. **Next.js** = a React web framework that also runs server code (our
API routes live inside it). **Supabase** = hosted Postgres (a managed SQL database). **MCP (Model
Context Protocol)** = a standard way an AI copilot calls tools / reads data. **NFR-5** = the
reliability requirement that two cases racing for the last part must not oversell — the loser is
refused.

### 7.2 Why it was needed

Decision A (2026-10-10) says inventory is a **separate source** from Salesforce: Salesforce owns the
service domain, a real e-com service owns product image + price + stock. Until now inventory was a
fake in the orchestrator's memory. This step makes it a real, external service the orchestrator
calls over the network — the thing that makes the "separate source" claim honest.

### 7.3 How it works, step by step

1. **Seed.** `scripts/seed.mjs` reads the orchestrator's `catalog.json` (14 models, 86 parts),
   applies the same stock rules as `catalog.py` (scarce = 1, consumable = 8, else = 3; a second
   "Delhi" location at 0), and upserts into `ecom_products` + `ecom_stock`. One consistent world.
2. **Read (find_part).** The orchestrator's `RestInventory.find_part("PCB-492")` does
   `GET /api/stock/PCB-492`; the route returns `{ partNo, locations: [{location, qty}] }`; the
   adapter returns the `locations` list — exactly the shape `FakeInventory` returned.
3. **Reserve.** `RestInventory.reserve("PCB-492")` does `POST /api/reserve {partNo, qty}`. The route
   calls the Postgres function `ecom_reserve`, which **locks** the best-stocked location
   (`SELECT ... FOR UPDATE`), decrements it, and returns true — or returns false if no location has
   enough. Two cases racing for the last unit: one wins, the other gets `{ ok: false }`. That
   refusal (not an oversell) is NFR-5, now enforced by the database, not an in-memory check.
4. **The Grab knob.** On the dashboard, "Grab" (or Set 0) calls `POST /api/stock {partNo, qty:0}`,
   which collapses the part to a single Noida row at that qty. In a demo you grab the scarce part
   right before the pipeline tries to reserve it → the race fires live on screen.
5. **MCP server.** `GET/POST /api/mcp` exposes two **read-only** tools (`list_products`,
   `get_stock`) over MCP. The future admin copilot (step #4) is the consumer. Reserve/set are *not*
   exposed — the guardrail: no LLM-invoked inventory writes.

### 7.4 Files / functions changed

**Orchestrator:**
- `app/tools/inventory.py` — added `RestInventory` (HTTP `find_part`/`reserve`, lazy httpx,
  injectable client for tests) + `build_inventory(settings)` (fake unless `ECOM_API_URL`).
- `app/main.py` — `app.state.inventory = build_inventory(settings)` (was `FakeInventory()`).
- `app/config.py` — added `ecom_api_url`. `.env.example` — added the `ECOM_API_URL` section.
- `tests/test_inventory_rest.py` — 3 tests (find_part mapping, reserve ok/refusal, mock-first factory).

**E-com (`apps/ecom/`, all new):**
- `supabase/schema.sql` — `ecom_products`, `ecom_stock`, and the atomic `ecom_reserve` function.
- `scripts/seed.mjs` — catalog → Supabase seeder (idempotent, self-loads `.env.local`).
- `lib/supabase.ts` — server-only client + `listProducts`/`stockFor`/`reserve`/`setStock`.
- `app/api/products`, `app/api/stock/[partNo]`, `app/api/reserve`, `app/api/stock`,
  `app/api/mcp` — the HTTP + MCP surface.
- `app/page.tsx`, `app/products-table.tsx`, `app/layout.tsx`, `app/globals.css` — the dashboard.
- `package.json`, `tsconfig.json`, `next.config.mjs`, `.env.example`, `.gitignore`, `README.md`.

### 7.5 Important decisions

- **Atomic reserve lives in SQL (`SELECT ... FOR UPDATE`), not app code.** It's the correct place to
  make the race safe; an app-level read-then-write would oversell under real concurrency.
- **The orchestrator never holds Supabase creds** — it only knows `ECOM_API_URL`. Clean blast
  radius: the inventory service's secrets stay in the inventory service.
- **MCP is read-only** — the one non-negotiable guardrail from the core design.
- **Service-role key, server-only.** All e-com API routes are server-side, so the service_role key
  (full DB access) never reaches the browser. No customer storefront means no public surface.
- **Rejected** a mock backing (you chose real Supabase) and deferring the MCP server (you chose now).

### 7.6 Tests / verification

- Orchestrator: `uv run pytest -q` → **94 passed**; `uv run ruff check .` → clean. (The 3 new
  inventory tests use `httpx.MockTransport`, so they run fully offline.)
- E-com: `pnpm install` clean; `pnpm build` → **compiled + type-checked successfully**, all 5 API
  routes + `/api/mcp` + the dashboard present.
- **Live round-trip VERIFIED 2026-10-11** against the new `fieldflow-ecom` Supabase project:
  `GET /api/products` → 86 products; `GET /api/stock/PCB-492` → `Noida:1, Delhi:0`;
  `POST /api/reserve` PCB-492 → `{ok:true}` then `{ok:false}` (the NFR-5 refusal, not an oversell);
  stock restored to 1. The new-format `sb_secret_…` key works with supabase-js.

### 7.7 Edge cases and limitations

- **Placeholder images** (`placehold.co`) need internet; fine for a demo, one line to swap for
  hosted brand assets. `ponytail:` noted in the seed.
- **`setStock` collapses to one Noida row** (mirrors `FakeInventory.set_stock`) — it's a demo knob,
  not a real multi-warehouse stock editor.
- **No auth on the dashboard** — POC, admin-only, not exposed publicly. Add a shared secret before
  any real deploy.
- **MCP auth is open** for the POC. `mcp-handler`'s `withMcpAuth` is the upgrade path when the
  copilot's ECA is wired (step #4).
- **The RAG corpus + Salesforce asset still read `catalog.json` directly** in the orchestrator — the
  e-com is the inventory source only. Unifying those is out of scope here.
