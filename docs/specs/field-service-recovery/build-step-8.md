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
- [x] 2. Data layer: `contract.gen.ts` **generated**, `cn.ts`, `api.ts` (all endpoints + fixtures
      toggle), `trace.ts` (hand-typed DecisionTrace + status model + helpers), `metrics.ts`
      (Prometheus parser → tiles), `fixtures.ts` (in-memory twin + `VITE_USE_FIXTURES`), Query hooks
      (`useLiveCases` seam, `useOps`, `useSim`), QueryClient + ThemeProvider in `main.tsx`.
- [x] 3. shadcn `ui/` primitives (button, badge, panel, tooltip, tabs, scroll-area, dialog) +
      `TopBar`/`PipelineStrip`/`ThemeToggle` + the 3-pane shell in `App.tsx`.
- [x] 4. **CaseList + CaseDetail hero** — `DecisionTrace` + `ConfidenceMeter` + `RcsCardPreview` +
      `StatusTimeline`. (Priority A — the core narrative.)
- [x] 5. `ApprovalActions` (human + quote approval) wired to `/sim/approve`. (Priority A.)
- [x] 6. `FailureDeck` + `ToolsSurface` in the tabbed `OpsDock`. (Priority B.)
- [x] 7. `MetricsStrip` from `/metrics` (tiles). (Priority C.)
- [x] 8. Verified: `pnpm typecheck` + `pnpm build` clean; ran in fixtures mode and screenshotted
      dark + light + the approval + metrics states via Playwright; Approve advanced a case live.
      Playbook §9 updated; §7 Explanation below.

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
- **2026-10-09 (SHIPPED).** Tasks 2–8 done — full data layer, shadcn `ui/` primitives, 3-pane
  shell, the decision-trace hero (confidence ring + factor bars + knowledge + tools + removed +
  commerce), RCS preview, lifecycle timeline, approval actions, failure deck, tools surface, metrics
  tiles. Dark + light both work (token-driven). `pnpm typecheck` + `pnpm build` green; verified in
  fixtures mode via Playwright (dark/light/approval/metrics) and Approve advanced a case live.
  `recharts` left installed for a future metrics time-series (only unused dep). Backend untouched.
  §7 Explanation written.
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

### 1. What changed
A full React + Vite + TypeScript control panel now lives in `apps/control-panel/`, replacing the
thin spine UI. It is a dense, dark-by-default (light-capable) operator console that makes the one
story obvious and puts the **decision trace** at the centre of the screen. It talks to the live
orchestrator by polling, and can also run entirely on captured fixtures with no backend.

### 2. Why it was needed
This is the UI the Vonage partners see. The backend already proves the idea (AI proposes → policy
decides → human approves risk → RCS is the control plane); the panel had to **show** it — the
reasons, the cited knowledge, the tools called, the confidence maths, and what policy removed —
rather than dump JSON.

### 3. How it works, end to end
- **Boot:** `main.tsx` wraps the app in `ThemeProvider` (sets `<html data-theme>`, persisted) and a
  TanStack Query `QueryClientProvider` (TanStack Query = a data-fetching library that caches server
  data and refetches on a timer).
- **Live data:** `useLiveCases` polls `GET /cases` every 1.5s. That one response already carries the
  full decision trace for every case, so it powers both the list and the detail — no per-case fetch.
  `useOps` polls `/tools`, `/dlq`, `/metrics`; `useHealth` drives the Live/Offline dot.
- **Actions:** `useSim` exposes every `/sim/*` call as a mutation; on success it invalidates the
  polled queries so the UI catches up on the next tick.
- **Layout:** a three-pane shell — case rail (left), the case detail with the decision-trace hero
  (centre), and a tabbed ops dock (right: Simulate / Tools / Metrics). A top bar shows the brand, the
  always-on pipeline strip (the four stages, lit up to where the selected case is), the live/fixtures
  state, and the theme toggle.
- **The hero (`DecisionTrace`):** the model's proposal prose, the `ConfidenceMeter` (an SVG ring for
  the final score + the five weighted factor bars), the deterministic `reason[]`, cited
  `knowledgeSources[]` with scores, `toolsUsed[]` tagged read vs action, policy-`removed[]` slots,
  the commerce quote, and a raw-JSON dialog.
- **Customer side:** `RcsCardPreview` renders the sent card in a phone frame; tapping a slot calls
  `/sim/customer-reply` (the offline twin of the RCS webhook). `StatusTimeline` shows the lifecycle
  with the current step and any "waiting for approval" pause. `ApprovalActions` shows the
  Approve/Reject gate only when the case is paused (low-confidence/risk or high-value quote).
- **Ops dock:** `FailureDeck` fires at-risk by reason, re-fires for idempotency, toggles the
  Salesforce fault, peeks/replays the DLQ, and fires a delivery-status → SMS fallback; `ToolsSurface`
  lists the reads vs actions from `/tools`; `MetricsStrip` parses `/metrics` into tiles.

### 4. Files / functions
- **`lib/`:** `contract.gen.ts` (generated envelope types), `trace.ts` (hand-typed `DecisionTrace`,
  status model, helpers — the one thing the schema can't generate), `api.ts` (typed client + the
  `VITE_USE_FIXTURES` switch), `fixtures.ts` (in-memory twin), `metrics.ts` (Prometheus parser),
  `theme.tsx` (dark/light provider), `cn.ts`.
- **`hooks/`:** `useLiveCases` (the polling seam), `useOps`, `useSim`.
- **`components/ui/`:** button, badge, panel, tooltip, tabs, scroll-area, dialog (Radix + tokens).
- **`components/`:** TopBar, PipelineStrip, ThemeToggle, CaseList, CaseDetail, DecisionTrace,
  ConfidenceMeter, RcsCardPreview, StatusTimeline, ApprovalActions, OpsDock, FailureDeck,
  ToolsSurface, MetricsStrip. `App.tsx` is the shell.
- **Theme:** `index.css` (token block, dark + light) + `tailwind.config.js` (semantic token map,
  fonts, motion).

### 5. Important decisions
- **Polling, behind a `useLiveCases` seam** — real SSE deferred (it needs a backend broadcast bus
  that would risk the 70 green tests). Swapping to SSE later touches only that one hook.
- **Hand-rolled, token-driven charts** (SVG ring + CSS bars) over a chart lib for the confidence
  view, so they flip with the theme and match the terminal aesthetic. `recharts` stays installed for
  a likely future metrics time-series (the only dep not yet used).
- **Fixtures as a real in-memory twin**, not just static reads, so the whole demo (incl. the failure
  deck and approvals) works offline for dev and as a fallback.
- **Types generated from the contract**, with only the free-form decision trace hand-typed.
- **Backend untouched** — its 70 tests stay green.

### 6. Tests / verification
- `pnpm typecheck` → clean. `pnpm build` → green (1719 modules, ~118 KB gzip JS).
- Ran in fixtures mode via Playwright at 1440×900: screenshotted the dark default, the light theme,
  the paused-approval case, and the metrics tiles — all render correctly.
- Clicked **Approve** on a paused case → it advanced `AWAITING_APPROVAL → OPTIONS_SENT` live,
  confirming the mutation → fixture transition → query-invalidation → re-render loop.
- Only console noise was a favicon 404, now fixed with an inline SVG icon.

### 7. Edge cases & limitations
- **No real-time push yet** — polling has up to ~1.5s latency (fine for a demo; SSE is the upgrade).
- **Fixture transitions are shallow** — they flip statuses believably but don't run the real policy
  engine; the live backend is the source of truth.
- **Desktop-first** — the 3-pane grid is tuned for ≥1280px; below that it stacks into one scroll
  (usable, not optimised). This is an operator console, by design.
- **Live `/sim/*` demos need the queue up** (CloudAMQP or `make up`); fixtures need nothing.
- **Grafana deferred** — the in-panel metrics strip covers the demo.
