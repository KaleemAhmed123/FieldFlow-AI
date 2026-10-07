"""The LangGraph checkpointer — where paused cases are stored so they can resume.

POC uses InMemorySaver: real interrupt/resume within the running process, zero infra, so the
tests and the live demo work with nothing to spin up.

ponytail: in-process only — a restart loses paused cases. Swap PostgresSaver
(`langgraph-checkpoint-postgres`, one dep) here when resume must survive a restart; nothing else
changes because the graph only ever sees `BaseCheckpointSaver`.
"""

from __future__ import annotations

from langgraph.checkpoint.memory import InMemorySaver


def make_checkpointer():
    return InMemorySaver()
