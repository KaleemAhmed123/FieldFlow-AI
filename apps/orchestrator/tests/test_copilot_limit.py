"""The copilot rate limiter (AI-SEC-02 / P0-4). Pure, clock injected — no network, no model."""

from __future__ import annotations

from app.copilot.limit import CopilotLimiter


def test_per_minute_cap_blocks_burst_then_recovers() -> None:
    lim = CopilotLimiter(per_min=2, per_day=0)  # 2/min, daily off
    t = 1000.0
    assert lim.allow(t) and lim.allow(t + 1)   # first two in the window are fine
    assert not lim.allow(t + 2)                # third within the minute → blocked
    assert lim.allow(t + 61)                   # window slid past → allowed again


def test_per_day_cap_resets_next_day() -> None:
    lim = CopilotLimiter(per_min=0, per_day=3)
    t = 1000.0
    assert all(lim.allow(t + i) for i in range(3))  # 3 allowed
    assert not lim.allow(t + 3)                      # 4th blocked
    assert lim.allow(t + 86400)                      # next UTC day → budget resets


def test_zero_disables_the_caps() -> None:
    lim = CopilotLimiter(per_min=0, per_day=0)
    assert all(lim.allow(1000.0) for _ in range(100))
