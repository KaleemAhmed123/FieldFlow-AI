# Build Step 8 — Control panel (the demo UI partners see)

## 1. Task

- **Name:** Step 8 — React control panel (comprehensive, premium, "hacker vibe").
- **Status:** in progress.
- **Started:** 2026-10-09.
- **Last updated:** 2026-10-09.

Build the operator UI in `apps/control-panel/` that makes the whole system's one idea obvious:
**AI proposes → deterministic policy decides → a human approves risk → RCS is the customer control
plane.** The **decision trace** ("show your work") is the hero of the screen.

## 2. What you asked for (your words, kept)

- React + Vite + TypeScript per scaffold §2. Panel **polls** the API today.
- **Comprehensive, component-rich, premium**, with a minimalist **hacker vibe**: dark,
  terminal/monospace accents, restrained palette, crisp density, subtle motion.
- This is what we **demo to Vonage partners** — richness is deliberate; do NOT ponytail components
  away. Ponytail still governs clean code (no dead abstractions, readable, maintainable).
- Views to cover: live case list · case detail with the **full decision trace** · RCS card preview
  (carousel + "Approve & Pay") · human-approval + quote-approval actions · live SLA/status timeline
  · the `/tools` surface (reads vs actions) · a failure-demo control deck (fire-at-risk by reason,
  customer-reply, payment, delivery-status→SMS fallback, fault toggle, DLQ peek + replay) · a
  metrics strip from `/metrics`.
- Keep the backend's **70 tests green** — don't change backend behaviour to suit the UI without
  telling you.
- Types come from `packages/contract` — **generate/mirror**, don't hand-duplicate.
- CORS origin is `http://localhost:5173` (already set on the backend).

## 3. Open questions — ANSWERED 2026-10-09

| # | Question | Your answer | What we're doing |
|---|----------|-------------|------------------|
| Q1 | Component approach (shadcn vs hand-rolled)? | Yes shadcn; keep it organized/readable/maintainable | Tailwind + a few **shadcn/ui primitives copied in** (Dialog, Tabs, Tooltip, ScrollArea, etc.), on Radix. We own the source → full control of the hacker skin. Strict folder structure (`ui/`, `components/`, `hooks/`, `lib/`). |
| Q2 | Polling vs SSE/WebSocket? | Polling; add SSE now if it's not a big task | **Polling now** via TanStack Query, behind a `useLiveCases` transport seam. **Real SSE deferred** — proper push needs a backend broadcast bus wired into the case service (a backend change that risks the 70 green tests); fake-SSE (server-side polling) adds cost for ~no gain. The seam makes SSE a small isolated follow-up. |
| Q3 | v1 view scope? | Recommended (all) | Ship **all** views, in priority order A → B → C (see Plan). |
| Q4 | Grafana in scope? | Yes add (the metrics strip) | **In-panel metrics strip** (parse `/metrics`, tiles + sparkline via Recharts). **Grafana deferred** as optional later debt. |
| Q5 | Fixtures vs live backend for UI dev? | Your choice | **Both:** build against captured fixtures, flip to live with `VITE_USE_FIXTURES`. Fixtures let every state (incl. paused/approval/failure) render with no RabbitMQ; the flag swaps to the real API for the demo. |

**Setup defaults taken (named, reversible):**
- **Package manager = pnpm** (installed; faster, strict). Lockfile generated this step.
- **Brand = neutral premium hacker theme** (no partner assets supplied yet; reskin later via theme
  tokens if assets arrive).
- **Node 24** present — fine for Vite 5 (needs ≥18). No action.

## 4. Plan

### Approach
- **Touch only `apps/control-panel/` + docs.** Backend untouched → 70 tests stay green.
- **Data layer:** one poll of `GET /cases` already returns the **full** decision trace for every
  case (same `_view` as `/cases/{id}` — [api/routes.py](../../../apps/orchestrator/app/api/routes.py)),
  so a single query powers both the list and the detail hero (no N+1). TanStack Query caches +
  refetches on an interval; mutations (the `/sim/*` POSTs) invalidate the cache so the UI updates.
- **Types:** `contract.gen.ts` is **generated** from `packages/contract/schema/*.json` via
  `json-schema-to-typescript` (satisfies "don't hand-duplicate" for Card/SlotOption/CaseView). The
  decision trace's inner keys are `dict[str, Any]` on the backend (untyped by design), so a single
  hand-written `DecisionTrace` type in `lib/trace.ts` covers them — the one thing that can't be
  generated, with a comment saying why.
- **Theme (fully manageable, dark + light):** every color is a **CSS variable token** defined once
  (`index.css`) under `:root` (light) and `[data-theme="dark"]` (dark = default hacker vibe).
  `tailwind.config.js` maps **semantic names** (`bg`, `surface`, `muted`, `accent`, `border`,
  `ok`/`warn`/`risk`) to those vars, so components use tokens, never raw colors. A persisted
  `ThemeProvider` + toggle switches dark/light. Reskin = edit the one token block. Monospace display
  font (JetBrains Mono) for accents, a clean sans for body.
- **Design skills applied:** frontend-design, minimalist-ui, enterprise-ux (dense operator layout),
  ui-ux-pro-max, shadcn, dataviz (confidence + metrics charts), advanced-frontend-architecture
  (state/data-fetching).

### Files to touch (all under `apps/control-panel/`)
```
package.json                    add deps (query, radix/shadcn pieces, recharts, lucide, clsx, tw-merge)
tailwind.config.js              hacker dark theme tokens
postcss.config.js               (unchanged)
index.css                       fonts, CSS vars, base layer
src/
  main.tsx                      QueryClientProvider + App
  App.tsx                       layout shell: header, left case rail, main stage, right ops dock
  lib/
    api.ts                      typed client for every endpoint (reads + sim mutations)
    fixtures.ts                 captured sample responses + VITE_USE_FIXTURES flag
    contract.gen.ts             GENERATED from packages/contract/schema (do not edit)
    trace.ts                    hand-typed DecisionTrace + status model + helpers
    metrics.ts                  parse Prometheus text → {name,value,labels}[]
    cn.ts                       clsx + tailwind-merge helper
  hooks/
    useLiveCases.ts             polling seam (SSE drop-in later)
    useTools.ts  useDlq.ts  useMetrics.ts
    useSim.ts                   mutation hooks for /sim/* (invalidate on success)
  components/
    ui/                         shadcn primitives (button, dialog, tabs, tooltip, badge, card, ...)
    Layout.tsx  TopBar.tsx
    CaseList.tsx  CaseRow.tsx
    CaseDetail.tsx              THE HERO container
    DecisionTrace.tsx           reason[] · knowledgeSources[] · toolsUsed[] · confidence · policy · removed[]
    ConfidenceMeter.tsx         dataviz: the 5-factor breakdown
    RcsCardPreview.tsx          carousel + Approve & Pay (phone frame)
    StatusTimeline.tsx          SLA / status progression
    ApprovalActions.tsx         human-approval + quote-approval (calls /sim/approve)
    ToolsSurface.tsx            reads vs actions from /tools
    FailureDeck.tsx             fire-by-reason, reply, payment, delivery-status, fault, DLQ peek+replay
    MetricsStrip.tsx            tiles + sparkline from /metrics
scripts/ (repo)                 gen-types (json-schema-to-typescript) wired to `make types`
```

### Alternatives rejected
- **Heavy component lib (MUI/Chakra):** fights the custom hacker look, bloats bundle. Rejected for
  shadcn primitives we own.
- **Real SSE/WebSocket now:** needs backend broadcast wiring that risks the green tests; deferred
  behind the `useLiveCases` seam.
- **Per-case detail fetch (`/cases/{id}`):** unnecessary — `/cases` already carries the full trace.
- **Hand-duplicating all TS types:** the contract schema is the source; only the untyped trace is
  hand-written.
- **Grafana:** separate server + dashboards-as-JSON + docker; the in-panel strip tells the story in
  the same UI. Deferred.

## 5. Tasks

- [x] 1. Tooling: deps in `package.json`, **pnpm lockfile**, theme tokens (dark+light),
      fonts (IBM Plex Sans + JetBrains Mono), CSS base, `@` import alias. *(QueryClient = part of
      task 2, not yet wired.)*
- [~] 2. Data layer: `contract.gen.ts` **generated** (per-schema modules under `lib/contract/` +
      curated re-export) + `cn.ts` **done**. **TODO:** `api.ts`, `trace.ts` (hand-typed
      DecisionTrace), `metrics.ts`, `fixtures.ts` + flag, the Query hooks, QueryClient in `main.tsx`.
- [ ] 3. shadcn `ui/` primitives + `Layout` shell (top bar, case rail, main stage, ops dock).
- [ ] 4. **CaseList + CaseDetail hero** — `DecisionTrace` + `ConfidenceMeter` + `RcsCardPreview` +
      `StatusTimeline`. (Priority A — the core narrative.)
- [ ] 5. `ApprovalActions` (human + quote approval) wired to `/sim/approve`. (Priority A.)
- [ ] 6. `FailureDeck` + `ToolsSurface`. (Priority B — operator power.)
- [ ] 7. `MetricsStrip` from `/metrics`. (Priority C — glance.)
- [ ] 8. Verify: `pnpm build` + typecheck clean; run live (`make dev` + `make panel`) and against
      fixtures; a Playwright screenshot. Update `playbook.md` (how to run the panel) and write the
      §7 Explanation here.

### Resume notes (for the next session — read before coding)

- **Checkpoint is GREEN:** `cd apps/control-panel && pnpm install && pnpm typecheck && pnpm build`
  all pass. `pnpm run types` regenerates the contract types. The **old** `src/App.tsx` +
  `src/api.ts` are still the live app (untouched) so the build stays coherent — replace them in
  task 3/4, don't delete until the new shell lands.
- **Exact trace shape (confirmed from `app/graph/build.py` + `app/llm/confidence.py`):**
  `decision` · `reason: string[]` · `knowledgeSources: {source,locator,link,score,snippet}[]` ·
  `toolsUsed: string[]` · `confidence: number` · `confidenceBreakdown: {final, factors{prior,
  headroom,grounding,data,llm}, weights{...}}` · `explanation` · `llmProvider` · `degraded` ·
  `rateLimitNote` · `policyResult` · `removed: {slotId,reason}[]` · `commerce?: {quote,order,
  paymentLink,payment}`. **This is what `lib/trace.ts` must type by hand** (backend types it as
  `dict[str,Any]`, so it is NOT in the JSON Schema — only Card/SlotOption/CaseView are generated).
- **`/cases` already returns the full trace per case** (same `_view` as `/cases/{id}`) → one poll
  powers list + detail, no per-case fetch.
- **Canonical statuses** (for the timeline): `LOADING → OPTIONS_SENT → (AWAITING_APPROVAL) →
  EXECUTED → [QUOTE_BUILT → (AWAITING_QUOTE_APPROVAL) → ORDER_CREATED → PAYMENT_PENDING → PAID] →
  VERIFIED → CLOSED`; `PAUSED`/`REJECTED` are side states. (`OFFER_RESCHEDULE` is the decision
  label, not a status.)
- **pnpm quirk (already solved):** esbuild's postinstall is gated by a supply-chain allowlist in
  `apps/control-panel/pnpm-workspace.yaml` (`allowBuilds: {esbuild: true}` + `onlyBuiltDependencies`).
  Keep that file; without it `pnpm install` errors `ERR_PNPM_IGNORED_BUILDS` and Vite can't run.
- **Backend untouched** → its 70 tests are still green (not re-run this session; no backend files
  changed).

## 6. Updates

- **2026-10-09** — Spec created; OQ1–Q5 answered (above). Build starting mock-first with fixtures;
  polling now, SSE seam for later. Backend not touched.
- **2026-10-09** — Package manager confirmed **pnpm**. Theme requirement sharpened: **dark + light
  both first-class and fully token-driven** (one CSS-variable block, Tailwind mapped to semantic
  tokens, persisted toggle); dark is the default. Reskin/relight = edit the one token block.
- **2026-10-09 (checkpoint — foundation built, paused for account switch).** Shipped task 1 + part
  of task 2 and reached a GREEN build. Added: `package.json` (deps installed via pnpm),
  `pnpm-workspace.yaml` (esbuild build-script allowlist), `tailwind.config.js` (semantic token →
  CSS-var mapping, fonts, motion keyframes), `src/index.css` (dark+light token block, base, grid
  backdrop, reduced-motion), `vite.config.ts` + `tsconfig.json` (`@/` alias), `src/lib/cn.ts`,
  `scripts/gen-types.mjs` + the **generated** `src/lib/contract.gen.ts` (+ `src/lib/contract/*.ts`).
  `pnpm typecheck` + `pnpm build` pass. Old `App.tsx`/`api.ts` still live so nothing is half-wired.
  **Next:** finish the data layer (`api.ts`, `trace.ts`, `metrics.ts`, `fixtures.ts`, hooks,
  QueryClient), then the shell + views. See the Resume notes under §5.

## 7. Explanation

_(Added when the step ships — the 7-section post-implementation walkthrough.)_
