# Testing Guide (for junior devs) — FieldFlow AI

**Who this is for:** a developer new to the codebase who wants to *learn the system by testing it*.
**Status:** covers shipped phases — Spine, Step 1 (policy + flow), Step 2 (tools + §3 reasons),
Step 4 (RAG). Step 5 (Groq) tests get added when that ships.
**Commands live in [`../../../playbook.md`](../../../playbook.md) §2** — this doc is the *why* and the
*what to test*, not a command dump.

---

## 0. The one mental model

> **The LLM proposes. Deterministic policy decides. A human approves risk. Tools do the real
> actions and may refuse.**

Almost every test exists to protect **one** of those four promises. Before you read or write a test,
ask: *which promise does this guard?* If you can't name one, the test probably isn't worth writing.

**How we test (house rules):**
- **Mock-first, zero infra.** Tests spin up their own in-memory SQLite + fake Salesforce / Vonage /
  inventory / knowledge store. **No `.env`, no Supabase, no Jina, no internet.** A test that needs a
  real key is not a unit test — it's a *smoke test* (see §6).
- **Deterministic.** Same input → same output, every run. The fake embedder is token-overlap, not
  real AI, so retrieval results never wobble.
- **One assert per promise.** A test should fail for exactly one reason. If it can fail for three,
  split it.

---

## 1. Vocabulary (one line each)

- **Positive test** — the good path: valid input → expected success.
- **Negative test** — bad/hostile input → a *controlled* refusal (not a crash).
- **Edge case** — the boundary where behaviour flips (exactly at the SLA limit, last unit of stock,
  a reply one version too old).
- **Fixture** — reusable test setup (our DB + fakes), defined once in
  [`conftest.py`](../../../apps/orchestrator/tests/conftest.py) and injected by name.
- **NFR** — Non-Functional Requirement: a cross-cutting promise (NFR-2 idempotency, NFR-4 human
  approval, NFR-5 no oversell, NFR-6 no stale action).
- **Idempotent** — doing it twice has the same effect as once (the same event never makes two cases).

---

## 2. What each test file already proves

Read these first — they are worked examples of the patterns you'll copy.

### Phase 1 — Spine
| File | Promise | Kind |
|------|---------|------|
| [`test_spine_e2e.py`](../../../apps/orchestrator/tests/test_spine_e2e.py) | one event → one case + a carousel card + a decision trace + one audit row | positive |
| [`test_idempotency.py`](../../../apps/orchestrator/tests/test_idempotency.py) | **NFR-2:** the *same* event twice = one case, one card (second returns `"duplicate"`) | edge |

### Phase 2 — Step 1 (policy engine + the LangGraph flow)
| File | Promise | Kind |
|------|---------|------|
| [`test_policy.py`](../../../apps/orchestrator/tests/test_policy.py) | removes a wrong-skill slot + an out-of-SLA slot, keeps the valid one → `PARTIAL` | positive + negative |
| `test_policy.py` | every option illegal → `DENIED`, nothing offered | negative |
| `test_policy.py` | `needs_human()`: low confidence **or** `DENIED` → human; confident + legal → auto | edge (the gate) |
| [`test_decision_flow.py`](../../../apps/orchestrator/tests/test_decision_flow.py) | **NFR-4:** low confidence pauses at human approval; nothing sent until approved | positive |
| `test_decision_flow.py` | rejected approval → case `REJECTED`, customer never messaged | negative |
| `test_decision_flow.py` | **NFR-5:** part taken mid-flight → atomic reserve fails → recompute + re-offer (loaner only) | edge |
| `test_decision_flow.py` | **NFR-6:** a reply tagged with a stale version → rejected → re-sent | edge |
| `test_decision_flow.py` | happy path → `CLOSED` | positive |

### Phase 3 — Step 2 (Toolbox / tool surface) + §3 (reasons → archetypes)
| File | Promise | Kind |
|------|---------|------|
| [`test_tools.py`](../../../apps/orchestrator/tests/test_tools.py) | a read tool returns data | positive |
| `test_tools.py` | unknown tool / missing arg → refused with a reason, **not an exception** | negative |
| `test_tools.py` | reserve refuses when stock is gone; two reserves on one unit → only one wins (no oversell) | edge |
| `test_tools.py` | reschedule refuses an unknown appointment; executes a valid one | positive + negative |
| `test_tools.py` | `describe()` keeps read/action kinds; `toolsUsed` in the trace is the **real** call list | positive |
| `test_decision_flow.py` | a cosmetic reason inherits its archetype (`safety_risk`→complex→human; `wrong_part_shipped`→parts→2 options) | positive |

### Phase 4 — Step 4 (RAG / knowledge)
| File | Promise | Kind |
|------|---------|------|
| [`test_rag.py`](../../../apps/orchestrator/tests/test_rag.py) | retrieval returns the relevant chunk **with citation metadata** (source, locator, link) | positive |
| `test_rag.py` | a warranty question retrieves the warranty doc | positive |
| `test_rag.py` | ingest is **idempotent** (re-run adds nothing) | edge |
| `test_rag.py` | **incremental:** insert a section in the middle → only that one chunk is embedded | edge |
| `test_rag.py` | the decision trace carries real `knowledgeSources` | positive |

---

## 3. How to run (pointer)

Full list in [`playbook.md`](../../../playbook.md) §2. The three you'll use constantly:

```bash
cd apps/orchestrator
uv run pytest -q                      # everything, fast (~1s). Target: all green.
uv run pytest tests/test_policy.py -q # one file while you work on it
uv run pytest -q -k "stale or race"   # one scenario by keyword
uv run ruff check .                   # lint gate: "All checks passed!"
```

**Acceptance for any change:** `pytest -q` all green **and** `ruff check .` clean. A red test is the
truth; a green suite with a skipped assert is a lie.

---

## 4. The pattern to copy when you write a new test

1. **Pick the promise** it guards (§0).
2. **Reuse a fixture** from `conftest.py` by putting its name in the test signature — `graph`,
   `toolbox`, `vonage`, `inventory`, `knowledge`, `sessionmaker`. You don't build setup; you ask for it.
3. **Drive the system the way the app does:** `case_service.handle_event(...)` to start,
   `case_service.resume_case(...)` to simulate the customer tap or the operator decision.
4. **Assert on observable state**, not internals: the `Case.status`, `vonage.sent`, the
   `decision_trace`, the card's options. (See any test in `test_decision_flow.py`.)
5. **One reason to fail.** Name the test after the promise: `test_<thing>_<expected>`.

**Trigger a specific archetype** with the event `reason`:
`technician_delay`→delay (auto), `part_missing`→parts (2-option carousel), `asset_complex`→complex
(human approval). Cosmetic reasons (`safety_risk`, `wrong_part_shipped`, …) inherit their archetype.

---

## 5. Gaps to fill — your actual tasks (each is one small test)

These are **not yet covered** and are perfect learning tasks. Each names the promise, the setup, and
the assert so you can't get lost. Add them to the file in brackets.

**Policy boundaries** `[test_policy.py]`
1. **SLA exact boundary** — a slot with `startMinutes == slaWindowMinutes` (e.g. 120/120). Should it
   be **kept** or removed? Decide, then lock it with a test. *(Boundary bugs hide here.)*
2. **Warranty expired** — `asset.warranty = "expired"` with a chargeable part option. Assert policy's
   handling matches the warranty doc's "out-of-warranty path."
3. **Unknown required skill** vs **no required skill** — a slot with `requiredSkill` omitted should
   pass; one with a skill the tech lacks should be removed. (Half is covered; add the omitted case.)

**Tools** `[test_tools.py]`
4. **Reserve more than stock** — `set_stock("CAP-492", 1)`, then `reserve(qty=2)`. Assert refusal, and
   that stock is **unchanged** (no partial reserve).
5. **Reschedule on a terminal case** — confirm on an appointment already `CLOSED`/`REJECTED`. Assert a
   clean refusal with a reason.

**Flow** `[test_decision_flow.py]`
6. **Unknown slotId reply** — customer taps a slot that isn't offered. Assert re-offer (not crash, not
   execute). *(The code path exists; prove it.)*
7. **Reply after close** — resume a case that's already `CLOSED`. Assert it's rejected safely.

**RAG / resilience** `[test_rag.py]`
8. **Knowledge failure degrades, never breaks (R9)** — inject a store whose `retrieve()` raises; run a
   full event. Assert the case still reaches `OPTIONS_SENT` with `knowledgeSources == []`. *(This is the
   most valuable test here — it proves the brain survives a dead library.)*
9. **Editing a chunk re-embeds only that chunk** — like the incremental test, but change text inside an
   existing section; assert exactly one add + one delete.

**Idempotency** `[test_idempotency.py]`
10. **Two different events = two cases** — the mirror of the existing test; proves we don't over-dedupe.

---

## 6. Live smoke tests (separate from unit tests — need real keys)

Unit tests never touch Supabase or Jina. The **live** paths are proven once, by hand, when creds are
present. These are **gated** (they hit real accounts / cost money) — run only on the tech lead's go.

- **RAG live smoke** (done 2026-10-08): `uv run python scripts/ingest_knowledge.py` then a real
  `retrieve()`. See [`build-step-4.md`](build-step-4.md) Updates.
- **Groq live smoke** (Step 5, pending): one real proposal call, with the fallback path exercised by
  killing the key. Will be documented in `build-step-5.md` + playbook when Step 5 lands.

---

## 7. Checklist before you say "done"

- [ ] New behaviour has **one** test that fails if the behaviour breaks.
- [ ] Positive **and** negative covered (does it also refuse the bad input cleanly?).
- [ ] The boundary/edge is pinned (off-by-one, last unit, stale version).
- [ ] `uv run pytest -q` all green, `uv run ruff check .` clean.
- [ ] No real keys, no network, no sleep-based timing in a unit test.
