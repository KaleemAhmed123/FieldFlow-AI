"""Logfire metrics — the cheap aggregates (counts + latency) that ride alongside the traces.

Logfire (not Prometheus): nobody scrapes a /metrics endpoint on the Render free tier, so these push
straight to the Logfire project with everything else — one pane of glass. Offline / tests have no
token, so every `.add()` / `.record()` is a safe no-op.

Counters created at import time (the documented Logfire pattern). Labels are passed as attributes at
the call site, e.g. `decisions.add(1, {"outcome": "APPROVED"})`.
"""

from __future__ import annotations

import logfire

events_processed = logfire.metric_counter(
    "fieldflow.events_processed", unit="1", description="Events processed OK")
events_duplicate = logfire.metric_counter(
    "fieldflow.events_duplicate", unit="1", description="Events ignored as duplicates")
events_failed = logfire.metric_counter(
    "fieldflow.events_failed", unit="1", description="Events that errored (→ DLQ)")
cards_sent = logfire.metric_counter(
    "fieldflow.cards_sent", unit="1", description="RCS cards sent")
sms_fallbacks = logfire.metric_counter(
    "fieldflow.sms_fallbacks", unit="1", description="RCS→SMS fallbacks (card undelivered)")
dlq_replays = logfire.metric_counter(
    "fieldflow.dlq_replays", unit="1", description="Messages replayed from the DLQ")

# End-to-end handling time per attempt (seconds). Logfire derives p50/p95 for the dashboard.
event_latency = logfire.metric_histogram(
    "fieldflow.event_seconds", unit="s", description="End-to-end event handling time")

# AI-OBS-01 signals — wired at the call site with an attribute (provider / outcome), so one metric
# breaks down by dimension instead of a metric per value.
proposer_fallback = logfire.metric_counter(
    "fieldflow.proposer_fallback", unit="1",
    description="Proposals that fell back off the primary provider (attr: provider)")
decisions = logfire.metric_counter(
    "fieldflow.decisions", unit="1",
    description="Pipeline decisions by policy outcome (attr: outcome)")
