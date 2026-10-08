"""Prometheus counters, wired as we build (not retrofitted) so Grafana shows real numbers."""

from __future__ import annotations

from prometheus_client import Counter

events_processed = Counter("fieldflow_events_processed_total", "Events processed OK")
events_duplicate = Counter("fieldflow_events_duplicate_total", "Events ignored as duplicates")
events_failed = Counter("fieldflow_events_failed_total", "Events that errored (→ DLQ)")
cards_sent = Counter("fieldflow_cards_sent_total", "RCS cards 'sent' (FakeVonage in the spine)")
sms_fallbacks = Counter("fieldflow_sms_fallbacks_total", "RCS→SMS fallbacks (card undelivered)")
dlq_replays = Counter("fieldflow_dlq_replays_total", "Messages replayed from the DLQ")
