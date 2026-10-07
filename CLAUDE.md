# FieldFlow AI — project rules for Claude

AI field-service recovery POC. **One idea:** AI proposes, deterministic policy decides, humans
approve risk; RCS is the customer control plane.

Full context: [`docs/specs/field-service-recovery/`](docs/specs/field-service-recovery/) — start
at `context/00-overview.md`, then `scaffold.md` for what's built.

## HARD RULES — explain-and-wait (added 2026-10-08 by the tech lead)

These outrank everything below. The user is the tech lead managing this project, not necessarily
deep in the jargon.

1. **Explain in the plain, teaching style.** Simple words, point form, one-line meaning for every
   technical term the first time it appears, a why-it-matters for each choice, worked examples /
   small diagrams where they help. No jargon dumps. This is the style the user confirmed on
   2026-10-08 — keep using it for every explanation.
2. **Do NOT move until the user answers.** When an open question is on the table, stop. No file
   edits, no building, no "I'll just start the easy part." Wait for an explicit go on every open
   question first.
3. **Always surface what the USER must do from their side.** In every plan / status, call out
   their action items explicitly: env setup, external service setup (Supabase, CloudAMQP, Groq,
   Razorpay, Vonage), Salesforce / e-com org + access work, testing they should run, resources to
   request, and **which boring, low-risk, well-scoped tasks to escalate to junior devs** vs keep
   for themselves. They are managing the project — treat them like a tech lead who needs the
   delegation map, not just the code.

## The playbook is the home for commands & how-to-run

**[`playbook.md`](playbook.md) (repo root) is the single source for every command, curl, env/run
step, demo flow, and continuation prompt.** When something operational changes (a new command,
endpoint, demo step, env requirement, build-step status), **update `playbook.md` in the same
change** — don't let commands drift into chat-only or scatter across docs. In replies, point the
user to `playbook.md` rather than re-pasting long command lists; a short inline snippet is fine,
the authoritative copy lives there.

## How to work here

- **Speed over production-grade complexity.** It's a POC to ship fast. Cut prod complexity that
  isn't core to the demo (skip inbound webhooks → use `/sim`; managed free tiers; defer
  alembic/auth/dashboards). Keep the hard parts that *are* the story: idempotency, policy, DLQ,
  decision trace, observability.
- **Managed free tiers, not local Docker:** Supabase (Postgres+pgvector), CloudAMQP, Groq/Gemini,
  Logfire. Everything is env-driven (`apps/orchestrator/.env.example`).
- **Mock-first.** Build against FakeVonage / FakeSalesforce behind interfaces; swap real later.
- **Keep the user in the loop.** Compact, skimmable chat replies. Say clearly and explicitly when
  you need a decision from them. Detail goes in files, not long chat walls.

## Updating the context docs — ask first

**After any big task, do NOT silently rewrite the context docs**
(`docs/specs/field-service-recovery/context/**`). Tell the user what's now stale and **ask for
permission** before updating them. Small inline fixes to a doc you're actively working in are
fine; wholesale context refreshes are gated on a yes.

## Don't

- Don't let the LLM mutate state directly — it only proposes; the policy engine decides.
- Don't put real customer data anywhere — fake everything.
- Don't name personal/other projects in the context docs — present patterns as part of *this*
  system, so any new reader understands it standalone.
