# FieldFlow e-com (inventory source)

The **separate inventory source** from Decision A (2026-10-10): Salesforce owns the service domain;
this service owns **product image + price + stock**. Next.js + Supabase, admin-only (no customer
storefront). It exposes a read/reserve HTTP API the orchestrator consumes, plus an MCP server the
future admin copilot will call.

## What's here

| Path | What it is |
|------|-----------|
| `supabase/schema.sql` | Tables (`ecom_products`, `ecom_stock`) + the atomic `ecom_reserve` SQL function. Run once in Supabase. |
| `scripts/seed.mjs` | Loads products + stock from the orchestrator's `catalog.json` (the single source of truth). Idempotent. |
| `lib/supabase.ts` | Server-only Supabase client + the data functions. |
| `app/page.tsx` + `products-table.tsx` | The admin dashboard: product grid, stock editor, **Grab** button (the NFR-5 knob). |
| `app/api/products` · `stock/[partNo]` · `reserve` · `stock` | The read/reserve/set API. |
| `app/api/mcp` | The e-com **MCP server** (read-only: `list_products`, `get_stock`). |

## HTTP contract (what the orchestrator's `RestInventory` calls)

- `GET  /api/stock/:partNo` → `{ partNo, locations: [{ location, qty }] }` — `find_part`
- `POST /api/reserve { partNo, qty? }` → `{ ok: boolean }` — `reserve` (atomic; lost race → `ok:false`)
- `POST /api/stock { partNo, qty }` → `{ ok, partNo, qty }` — admin **Grab/Set** knob (not the orchestrator)

## Run it

1. `cp .env.example .env.local` and fill `NEXT_PUBLIC_SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY`
   (Supabase dashboard → Settings → API).
2. Paste `supabase/schema.sql` into the Supabase SQL editor and run it.
3. `pnpm install` then `pnpm seed` (loads 86 parts from the catalog; scarce parts land at qty 1).
4. `pnpm dev` → dashboard at http://localhost:3000, API under `/api/*`, MCP at `/api/mcp`.

Point the orchestrator at it: set `ECOM_API_URL=http://localhost:3000` in
`apps/orchestrator/.env` and `RestInventory` swaps in for `FakeInventory` automatically.

## Guardrail

The MCP server is **read-only**. Inventory mutations (reserve) run through the deterministic
pipeline or a human-confirmed admin action — never an LLM-invoked MCP write.
