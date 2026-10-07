"""structlog JSON logging + a correlation id carried through async calls via contextvars.

Every log line for one recovery case carries its correlationId, so a case can be followed
end to end — the single most useful thing to wire from line one.
"""

from __future__ import annotations

import logging
from contextvars import ContextVar

import structlog

correlation_id: ContextVar[str | None] = ContextVar("correlation_id", default=None)


def _inject_correlation_id(_logger, _method, event_dict):
    cid = correlation_id.get()
    if cid is not None:
        event_dict["correlationId"] = cid
    return event_dict


def configure_logging(level: str = "INFO") -> None:
    logging.basicConfig(format="%(message)s", level=getattr(logging, level.upper(), logging.INFO))
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            _inject_correlation_id,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, level.upper(), logging.INFO)
        ),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str = "fieldflow"):
    return structlog.get_logger(name)
