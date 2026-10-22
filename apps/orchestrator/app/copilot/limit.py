"""Rate limit for the admin copilot (AI-SEC-02 / P0-4).

Each /copilot/chat call spends Groq tokens, so cap it: a per-minute sliding window (burst control)
plus a per-day budget (free-tier guard). Over either → the caller is refused and no Groq call is
made.

ponytail: in-process counters, one shared instance. Fine for the single Render dyno; swap for Redis
if the orchestrator ever runs more than one instance. Clock is injectable so the logic is testable.
"""

from __future__ import annotations

import time
from collections import deque


class CopilotLimiter:
    """Allow a call only if under both the per-minute and per-day caps. A cap of 0 disables it."""

    def __init__(self, per_min: int, per_day: int) -> None:
        self._per_min = per_min
        self._per_day = per_day
        self._recent: deque[float] = deque()  # call timestamps in the last 60s
        self._day = ""
        self._day_count = 0

    def allow(self, now: float | None = None) -> bool:
        now = time.time() if now is None else now
        day = time.strftime("%Y-%m-%d", time.gmtime(now))
        if day != self._day:  # new UTC day → reset the daily budget
            self._day, self._day_count = day, 0

        if self._per_min > 0:
            cutoff = now - 60
            while self._recent and self._recent[0] < cutoff:
                self._recent.popleft()
            if len(self._recent) >= self._per_min:
                return False
        if self._per_day > 0 and self._day_count >= self._per_day:
            return False

        self._recent.append(now)
        self._day_count += 1
        return True
