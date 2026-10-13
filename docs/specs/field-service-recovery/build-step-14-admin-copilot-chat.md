# Build step 14 — Admin Copilot Chat

## 1. Task

- **Name:** Admin Copilot Chat — the agentic read path.
- **Status:** Shipped (code + tests + panel). SF live-verify pending one user re-login.
- **Started:** 2026-10-13
- **Last updated:** 2026-10-13

## 2. What you asked for

- Build the admin copilot on top of the MCP plumbing from step 12 (the `/copilot/tools` route + the
  8 deployed `FFCopilot_*` Salesforce tools).
- An admin types a plain-English question → an LLM does **tool-calling** over MCP tools → a grounded
  answer that actually called a real tool.
- Decisions settled in planning:
  - **e-com tools via the e-com MCP** (`/api/mcp`), symmetric with Salesforce — not a REST wrapper.
  - **Groq-only** tool-calling this slice (a Gemini fallback is a later seam).
  - **A panel chat tab now** (not curl-only).
- Constraints (house rules): read-only (the copilot never mutates — "AI proposes, policy decides"
  stays intact); keep tests green + ruff clean; update `playbook.md` + this spec in the same change;
  no billed sends / payments / pushes without an explicit go.

## 3. Open questions (answered)

1. **e-com tools: MCP or REST wrapper?** → **e-com MCP.** Symmetric with SF; shows the real MCP
   story; the e-com `/api/mcp` is already live and open (no auth).
2. **LLM providers this slice?** → **Groq-only.** The existing proposer ladder does NOT do
   tool-calling (it returns a structured `Proposal`), so this is new code; Groq (OpenAI-compatible)
   is the cleanest first target. Gemini uses a different tool schema → deferred.
3. **Interface?** → **Panel chat tab now** (OpsDock → "Copilot"), plus the `POST /copilot/chat` API.
4. **Memory?** → **Single-turn** (stateless). Each question stands alone; tools ground it.
5. **Tool scope?** → all 8 SF + 2 e-com; each source is optional (uses whatever is armed).

## 4. Plan

- **Reuse:** `SalesforceMcpClient` (token refresh + session), `build_mcp_client`, `/copilot/tools`,
  the Groq SDK setup pattern, `settings` (keys/model).
- **New:** the tool-calling loop (the proposer ladder can't do it), an e-com MCP client, the route,
  the panel tab.
- **Generalize the MCP session** so one loop reaches both servers: a shared `_McpReach` base
  (list/call over Streamable HTTP) with per-source `_headers()` — Bearer for SF, empty for e-com.
- **Rejected:** wrapping e-com REST as hand-written tools (asymmetric, hides the MCP story);
  building a token store for refresh-token durability (POC — re-login on restart is fine).

Files: `app/mcp/client.py` (session + `EcomMcpClient` + `build_ecom_mcp_client`), `app/copilot/*`
(the loop), `app/config.py` (`ecom_mcp_url`), `app/api/routes.py` (`POST /copilot/chat`),
`app/main.py` (wire `app.state.ecom_mcp`), `tests/test_copilot_chat.py`,
`apps/control-panel/src/{lib/api.ts, components/CopilotChat.tsx, components/OpsDock.tsx}`, `playbook.md`.

## 5. Tasks

- [x] 1. Verify the SF Hosted MCP connection live (`/copilot/tools` lists the 8 tools).
- [x] 2. Fix the MCP client for `mcp` SDK 2.3.0 (renamed `streamable_http_client`, 2-tuple transport,
  its own `httpx2` client) + add the e-com MCP client + the `ecom_mcp_url` config.
- [x] 3. The Groq tool-calling loop (`app/copilot/chat.py`) with name aliasing + a step cap.
- [x] 4. `POST /copilot/chat` → `{available, answer, toolsUsed[, truncated]}`.
- [x] 5. Panel "Copilot" tab (chat bubbles + a per-answer tools-used trace + starter questions).
- [x] 6. Offline tests (fake Groq + fake MCP): loop runs a tool, grounds the answer, aliases long
  names, answers with no tools when none armed.
- [x] 7. Docs: playbook §3k + this spec.

## 6. Updates

**2026-10-13 — built.**
- Live-verified the SF MCP (8 tools) and e-com MCP (2 tools: `list_products`, `get_stock`) over the
  real servers. SF tool names come back ~65 chars → **aliasing is required** (Groq caps names at 64).
- Live end-to-end against real Groq + e-com: the model called `get_stock`, guessed the wrong arg
  (`part_number`), got the MCP validation error back, **self-corrected to `partNo`**, and answered
  from real data. Proves the whole loop.
- **Gotcha found: SF refresh-token rotation.** A verification refresh rotated the token; the copy in
  `.env` went stale (`invalid_grant`). Added rotation-capture in `access_token()` (keeps the new
  token in-memory). A restart still needs a fresh `python -m app.mcp.login`. User action item: one
  re-login to re-arm SF (e-com unaffected — no auth).
- Backend: `uv run pytest -q` → 112 passed; `uv run ruff check .` clean. Panel `pnpm build` passes.

**2026-10-13 (later) — live debugging on Render + two follow-up fixes.**
- Deployed to Render; **e-com chat works end-to-end** there. Found + fixed real bugs under live fire:
  1. **SDK field rename** — `mcp` 2.3.0 exposes the tool schema as `input_schema` (alias `inputSchema`);
     our `getattr(t, "inputSchema")` blanked every schema, so Groq guessed argument names (e-com
     tolerated it, SF rejected with `JSON_PARSER_ERROR`). Fixed to read `input_schema` with a fallback.
  2. **One bad source took down the whole copilot** — a dead SF token made `_gather` raise, 500-ing
     even e-com. Now each source is gathered independently; a failing one is skipped and reported in
     `sourcesUnavailable`, the rest still answer. Panel shows an "unavailable" note.
  3. **Forced refresh-token rotation** — the SF ECA has "Enable Refresh Token Rotation" locked ON
     ("contact Support" — can't disable). So every refresh mints a new token and kills the old one;
     the env copy goes stale after the first call, and any restart/redeploy boots with a dead token.
     **Fix: durable token persistence.** New `app_secrets` table + `app/db/secrets.py`; the SF client
     flags a rotation (`pop_rotated_token`), the copilot routes save it, and boot restores the latest
     from the DB (`set_refresh_token`) instead of the stale env value. The env token is only needed
     for the very first call after this lands; the DB self-heals every restart thereafter.
- 115 tests green, ruff clean. User action: re-mint once (`python -m app.mcp.login`), put it in Render
  env, deploy — the first call persists it and it survives restarts from then on.

**2026-10-13 (later still) — LIVE on Render, then two polish fixes from real use.**
- Verified the full copilot on Render: e-com `get_stock`, SF `AppointmentHealth` (arg) and SF
  `StatusCounts` (no-arg) all return real data, `sourcesUnavailable: None` — the token persistence
  holds across the rotations. The panel **Copilot tab** works end-to-end.
- **413 on big queries → graceful.** "total items in inventory" made the model call `list_products`
  (all 86 parts) → the next Groq request was ~11k tokens, over the free tier's **8k tokens/min** →
  413 → uncaught → **500** → the 500 lacked the CORS header so the browser *blamed CORS*. Fix:
  `run_copilot` now wraps every Groq call (`_llm_create`/`_LlmError`) and returns a friendly message
  instead of raising; tool results fed back are capped (`_TOOL_RESULT_CAP`) so one big list can't
  blow the budget. The copilot never 500s now.
- **Scrollbars.** The Radix `ScrollArea` used the default `type="hover"`, so scrollbars only appeared
  on hover and users couldn't tell panes were scrollable. Switched to `type="auto"` + a more visible
  thumb (global, affects every pane). 116 tests green, ruff clean, panel builds.

## 7. Explanation

### What changed
A new **admin copilot chat**: ask a plain-English question in the control panel's "Copilot" tab (or
`POST /copilot/chat`); **Groq** decides which tools to call, we run them over the live Salesforce +
e-com **MCP** servers, and the model answers from the real results. Each answer shows the tools it
used — a mini decision-trace.

### Why it was needed
Step 12 deployed the Salesforce MCP tools and a discovery route, but nothing *used* them. This is the
agentic read path: open-ended questions where the LLM must discover and pick tools — distinct from
the deterministic recovery pipeline, where Python calls named tools and the LLM never chooses.

### How it works, step by step
1. The route gathers the armed sources: `app.state.mcp` (Salesforce, if `SF_MCP_*` armed) and
   `app.state.ecom_mcp` (e-com, derived from `ECOM_API_URL` + `/api/mcp`).
2. `run_copilot` lists every source's tools, aliases Groq-illegal names (SF's are too long), and
   sends them to Groq as function definitions with their JSON-Schema arguments.
3. Groq replies either with a final answer (done) or with tool calls. For each call we route the
   alias back to its real tool + source, run it over MCP, and feed the result back as a `tool`
   message. A failing tool returns its error text instead of crashing the chat.
4. Loop up to 5 steps (a hard cap). If Groq keeps calling tools, a final no-tools turn forces an
   answer (`truncated: true`).
5. The reply is `{answer, toolsUsed:[{name, args, result}]}`. The panel renders the answer bubble
   and the tools-used trace underneath.

### Files / functions changed
- `app/mcp/client.py` — `_open_session` (SDK-2.3.0 Streamable-HTTP), `_McpReach` base
  (`list_tools`/`call_tool`, now including each tool's `inputSchema`), `SalesforceMcpClient`
  (OAuth + rotation-capture), new `EcomMcpClient`, `build_ecom_mcp_client`.
- `app/copilot/chat.py` — `run_copilot` (the loop), `_alias`, `_gather`, `_content_to_text`,
  `build_groq_client`.
- `app/api/routes.py` — `POST /copilot/chat` + `CopilotAsk` body.
- `app/main.py` — `app.state.ecom_mcp = build_ecom_mcp_client(settings)`.
- `app/config.py` — `ecom_mcp_url`.
- `apps/control-panel` — `lib/api.ts` (`copilotChat` + types), `components/CopilotChat.tsx`,
  `components/OpsDock.tsx` (the tab).
- `tests/test_copilot_chat.py`, `playbook.md` (§3k), this spec.

### Important decisions
- **e-com over MCP, not REST** — symmetric, shows the MCP story, zero new creds.
- **Groq-only first** — the proposer ladder can't do tool-calling; Groq is the cleanest first target.
- **Name aliasing** — the only non-obvious correctness detail: SF's hosted MCP returns ~65-char tool
  names and Groq rejects names > 64 chars, so we alias and map back.
- **Rotation-capture over a token store** — smallest fix that survives a running server; a restart
  re-logins (POC ceiling).

### Tests / verification
- `uv run pytest -q` → **112 passed**; `uv run ruff check .` → clean; `pnpm build` → passes.
- Live: SF (8 tools) + e-com (2 tools) listed over the real servers; a real Groq run answered a
  stock question by calling `get_stock` and self-correcting its arguments.

### Edge cases and limitations
- **SF restart needs a re-login** if the `.env` refresh token was already rotated away (e-com
  unaffected).
- **Groq-only**: a Groq outage has no Gemini fallback yet (the next seam).
- **Single-turn**: no conversation memory — follow-ups don't see prior answers.
- **Tool-name collisions** across sources are last-wins (none today; SF and e-com names differ).
- The e-com MCP is **open (no auth)** — fine for the POC's fake data; not production posture.
