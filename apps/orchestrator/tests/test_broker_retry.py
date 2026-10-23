"""The retry-tier decision (AI-REL-01 / P0-5): 3 backoff tiers, then the DLQ. Pure — the RabbitMQ
TTL wiring itself is verified live against a real broker (needs infra)."""

from __future__ import annotations

from app.queue.broker import MAX_RETRIES, RETRY_TIERS, next_retry_key


def test_retry_tiers_then_dlq() -> None:
    assert next_retry_key(0) == "retry.5s"     # first failure → 5s backoff
    assert next_retry_key(1) == "retry.30s"    # second → 30s
    assert next_retry_key(2) == "retry.120s"   # third → 120s
    assert next_retry_key(3) is None           # retries spent → dead-letter
    assert next_retry_key(9) is None


def test_tiers_match_max_retries() -> None:
    assert MAX_RETRIES == len(RETRY_TIERS) == 3
    assert [t[2] for t in RETRY_TIERS] == [5_000, 30_000, 120_000]  # delays in ms, increasing
