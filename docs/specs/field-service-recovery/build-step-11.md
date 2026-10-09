# Build Step 11 — dependency-health endpoint (`GET /health/deps`)

## 1. Task

- **Name:** Dependency-health endpoint — one call reports whether every external dep is reachable/configured.
- **Status:** in progress
- **Started:** 2026-10-09
- **Last updated:** 2026-10-09

## 2. What you asked for

- Add **one new deep endpoint — `GET /health/deps`** — a single call that reports the health of every
  external thing we use.
- Keep the existing `/health` + `/ready` **cheap** — liveness/readiness must **not** hit the network.
  The new route is the deep one.
- Check each dep **concurrently** (`asyncio.gather`), each with a **short timeout**, and **never throw** —
  one dead dep returns `"down"`, the route still returns **200** with a JSON body.
- Return **names + status + latencyMs** only. **Never leak keys/secrets.**
- Deps, grouped (names from `.env.example`):
  - **REQUIRED** (pull overall to `down` if failing):
    - `postgres` (`DATABASE_URL`) → `SELECT 1`
    - `rabbitmq` (`RABBITMQ_URL`) → is `app.state.broker` connection open? broker `None` → down/unavailable
  - **OPTIONAL / DEGRADABLE** (can only pull overall to `degraded`, they have fallbacks):
    - `groq`, `gemini` → deep check = the FREE `models.list()`, **not** a completion
    - `jina` → do **not** embed on every poll (billable). Default = key-present + reachability only
    - `logfire` → config-present only
  - **ARMED-OR-FAKE** (report configured state, never up/down; reuse the code's existing rules):
    - `vonage` → `armed` vs `fake` via the all-four-set rule in `build_vonage`
    - `razorpay` → `test-mode` vs `fake` by whether `RAZORPAY_KEY_ID` starts with `rzp_test_`
- **COST GUARD:** default run = cheap (config present + DB/queue ping). Gate the billable/real external
  pings behind `?deep=1`, **and** cache the result ~15–30s so the panel's ~5s poll can't hammer/spend.
- **Overall status** = worst-of the REQUIRED checks; optional ones only downgrade to `degraded`.
- **Response shape:**
  ```json
  { "status": "ok|degraded|down",
    "checks": { "postgres": {"status":"ok","latencyMs":12}, "rabbitmq": {"status":"ok","latencyMs":3},
                "groq": {"status":"skipped","detail":"key set; deep check only"},
                "jina": {"status":"skipped","detail":"key set; not pinged (billable)"},
                "vonage": {"status":"fake","detail":"not armed"}, "razorpay": {"status":"test-mode"},
                "logfire": {"status":"ok"} } }
  ```
- Add **one** offline test (fake each dep client; a down dep → `down`/`degraded` but route still 200 and
  leaks no secrets). Update `playbook.md` + this Explanation in the same change.

## 3. Open questions — ANSWERED

**OQ1 — default (cheap) vs `?deep=1` behaviour.** *(the requirements had a small internal conflict: the
cost-guard line put `models.list` in the cheap default, the per-dep line called it the deep check.)*
→ **Answer (2026-10-09): "see systems availability — pick what should be."** Decision: the **cheap default
makes zero third-party API calls** — only `SELECT 1` (Postgres) + RabbitMQ connection check (our own infra)
+ config-present for everything else (groq/gemini/jina report `skipped`). **`?deep=1`** adds the real
third-party pings: groq/gemini `models.list()` (free) and the jina HEAD reachability (never embeds).
*Why:* the panel can poll the cheap route as often as it likes and never spend a credit or hammer a vendor;
you get true external availability on demand via `?deep=1`.

**OQ2 — cache TTL.** → **Answer: 30 seconds.** Env-tunable (`HEALTH_DEPS_CACHE_TTL_S=30`). Cache is keyed by
the `deep` flag, so the cheap and deep results are cached separately.

**OQ3 — wire into the panel's TopBar health dot now, or defer?** → **Answer: defer.** This endpoint is for
**dev/debugging** now; panel wiring (a deps popover) is a later, separate step. Keeps "backend 70 green,
panel untouched" true.

**OQ4 — new module `app/health.py` vs inline in `routes.py`.** → **Answer: new file.** Keeps `routes.py`
thin and lets the test import `check_deps` directly without spinning up HTTP.

## 4. Plan

**Approach:** one pure async function `check_deps(...)` that fans out 8 checks with `asyncio.gather`, each
wrapped so it can **never** raise (timeout or error → that dep is `down`/`skipped`, the whole call still
returns a dict). Overall status = worst-of REQUIRED, then OPTIONAL can knock `ok`→`degraded`; ARMED-OR-FAKE
are informational. A module-level cache (keyed by the `deep` flag, 30s TTL) sits in front so repeat polls
return the last body.

**Secret-safety rule:** every failure path returns a **generic** `detail` (`"unreachable"`,
`"models.list failed"`) — **never** `str(exc)`, because a DB/driver error can contain the connection URL
*with the password*. Keys are never put in the body; only `status` + `latencyMs` + a safe `detail`.

**Files to touch:**
- **new** `app/health.py` — `check_deps(*, sessionmaker, broker, vonage, razorpay, settings, deep, ttl, use_cache)` + the per-dep helpers + the cache.
- `app/api/routes.py` — add `GET /health/deps` (reads `?deep`, calls `check_deps`, passes the live `app.state` deps).
- `app/queue/broker.py` — add a one-line `is_open` property (so health doesn't reach into `broker._conn`).
- `app/config.py` — add `logfire_token: str = ""` (today `LOGFIRE_TOKEN` is silently ignored by
  `extra="ignore"`) and `health_deps_cache_ttl_s: float = 30.0`.
- `tests/test_health_deps.py` — the one offline test.
- `playbook.md` — the new endpoint + the `?deep` flag + two sample outputs.
- this file — section 7 Explanation (same change as the code).

**Reused, not rebuilt:** `vonage` armed/`razorpay` test-mode are read by `isinstance` on the already-built
`app.state` client — the arming rule lives in `build_vonage`/`build_gateway`; we do not duplicate it.

**Deliberately NOT changing:** `/health`, `/ready`, `/metrics`, the graph, the consumer, any send/pay path,
and the control panel. Backend stays green (70 → 71 with the new test).

**Alternatives rejected:**
- *Inline in `routes.py`* — rejected (OQ4): harder to test, bloats the read API.
- *`models.list` in the cheap default* — rejected (OQ1): a 5s poll would make live vendor calls; deep-gated instead.
- *Reach into `broker._conn.is_closed` from health* — rejected: a one-line `is_open` property is cleaner and private-safe.

## 5. Tasks

- [x] Write sections 1–5 (this file) before any code.
- [x] `app/health.py` — `check_deps` + per-dep helpers + 30s cache.
- [x] `broker.is_open` property.
- [x] `config.py` — `logfire_token` + `health_deps_cache_ttl_s`.
- [x] `GET /health/deps` route.
- [x] `tests/test_health_deps.py` (one offline test).
- [x] `uv run pytest -q` → 71 passed; `uv run ruff check .` clean; `import app.main` OK.
- [x] Update `playbook.md` + section 7 Explanation (same change).

## 6. Updates

- **2026-10-09** — Step planned; OQ1–OQ4 answered by the user (cheap default = zero third-party calls,
  `?deep=1` for real pings; 30s cache; dev/debug only, defer panel; new file). Implemented and verified:
  **71 passed**, ruff clean, `import app.main` OK.

## 7. Explanation

### 1. What changed
A new read-only endpoint, **`GET /health/deps`**, now reports the health of all 8 external deps in one call.
`/health` and `/ready` are unchanged (still cheap, no network). A small new module `app/health.py` holds the
logic; `routes.py` gained a thin route; `broker.py` gained an `is_open` property; `config.py` gained two
settings. One offline test was added.

### 2. Why it was needed
Before this, there was no single place to ask "is everything we depend on actually reachable?" You had to
infer it from logs. For a POC you demo to partners, one endpoint that says `ok / degraded / down` per dep is
the fastest way to spot a dead key, a down queue, or a mis-set URL — without spending LLM/RCS credits to find
out.

### 3. How it works, step by step
1. A request hits `GET /health/deps` (optionally `?deep=1`).
2. The route reads the live deps off `app.state` (broker, vonage, razorpay) + the global DB session factory,
   and calls `check_deps(...)`.
3. **Cache first:** if a result for this `deep` flag was computed in the last 30s, it's returned with
   `"cached": true` — so a 5s panel poll never does real work more than twice a minute.
4. **Otherwise, fan-out:** `asyncio.gather` runs all 8 checks at once. Each check is wrapped so a timeout or
   any error returns a `down`/`skipped` dict instead of raising — the gather can never blow up the route.
   - `postgres`: `SELECT 1` (2s timeout) → `ok` + `latencyMs`, else `down`.
   - `rabbitmq`: `broker is None` → `down`; else report `broker.is_open`.
   - `groq`/`gemini`: no key → `skipped "not configured"`; key but **cheap** → `skipped "deep check only"`;
     key + **deep** → free `models.list()` in a thread (4s timeout) → `ok`, else `down`.
   - `jina`: no key → `skipped`; key but **cheap** → `skipped "not pinged (billable)"`; key + **deep** →
     an **unauthenticated HEAD** to `api.jina.ai` (reachability only, never embeds) → `ok`, else `down`.
   - `logfire`: token set → `ok "configured"`, else `skipped "not configured"` (never touches the network).
   - `vonage`/`razorpay`: `isinstance` on the already-built client → `armed`/`fake`, `test-mode`/`fake`.
5. **Overall status:** start `ok`; if any OPTIONAL dep is `down` → `degraded`; if any REQUIRED dep
   (`postgres`/`rabbitmq`) is not `ok` → `down` (required wins). ARMED-OR-FAKE never change the overall.
6. The body is cached (keyed by `deep`) and returned. FastAPI serialises the dict → **HTTP 200**, always.

### 4. Files / functions changed
- **`app/health.py` (new):** `check_deps(...)` (orchestrator + cache) and `_check_postgres / _check_rabbitmq /
  _check_groq / _check_gemini / _check_jina / _check_logfire / _check_vonage / _check_razorpay` (per-dep,
  each returns a small status dict and never raises). `_overall(checks)` computes worst-of. `_CACHE` is the
  module-level `{deep: (timestamp, body)}` store; `reset_cache()` clears it (used by the test).
- **`app/api/routes.py`:** new `health_deps(request, deep: bool=False)` route — wires `app.state` deps into
  `check_deps` and passes the TTL from settings.
- **`app/queue/broker.py`:** `is_open` property — `True` when the robust connection exists and isn't closed.
- **`app/config.py`:** `logfire_token: str = ""` (so `LOGFIRE_TOKEN` is actually read) and
  `health_deps_cache_ttl_s: float = 30.0`.
- **`tests/test_health_deps.py` (new):** forces Postgres down with a fake sessionmaker whose `execute`
  raises a message *containing a fake secret*; asserts overall `down`, route returns a dict (→ 200), and the
  secret appears **nowhere** in the serialised body.

### 5. Important decisions
- **Cheap default = zero third-party calls** (OQ1): the frequent poll only touches our own infra (DB + queue);
  real vendor pings are opt-in via `?deep=1`. Protects the Vonage/LLM credits.
- **Generic `detail` on every failure** (security): never `str(exc)` — DB errors leak the password-bearing URL.
- **Pure, injected `check_deps`**: all deps are arguments (not globals), so the test needs no HTTP server.
- **`isinstance` to read vonage/razorpay state**: reuses the arming rule already encoded by `build_vonage` /
  `build_gateway` instead of re-deriving it from env.

### 6. Tests / verification
- New `tests/test_health_deps.py`: Postgres forced down → overall `down`, route still returns a dict (200),
  and a planted secret does not appear in the body.
- Full suite: `uv run pytest -q` → **71 passed**. `uv run ruff check .` → clean. `uv run python -c "import
  app.main"` → OK. (All offline; no keys, no network.)

### 7. Edge cases and limitations
- **Deep pings cost a round-trip, not money:** `models.list()` is free; the jina HEAD is unauthenticated and
  never embeds. Still, they're network calls — hence 4s timeouts + the 30s cache.
- **Cache is per-process + in-memory:** fine for the single-process POC; a multi-worker deploy would cache per
  worker (acceptable — it's a health probe, not a source of truth).
- **`rabbitmq` reports the connection flag, not a live round-trip:** `is_open` reflects the robust
  connection's state; it does not open a fresh test channel each call (cheaper, and enough for the demo).
- **No auth on the endpoint:** it's a dev/debug tool and leaks no secrets, but it does reveal which deps are
  configured — put it behind the gateway/VPN before any real exposure.
