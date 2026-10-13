"""Build step 14 — the admin copilot tool-calling loop, proven offline.

No Groq key, no network, no MCP SDK: a fake Groq client scripts (tool call -> final answer) and a
fake MCP source returns canned tool output. We prove the loop executes the chosen tool, feeds the
result back, grounds the final answer, records `toolsUsed`, aliases Groq-illegal tool names, and
answers with no tools when none are armed.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

from app.copilot.chat import _alias, run_copilot


class FakeSource:
    """A stand-in MCP client: lists one tool, records the call, returns canned text."""

    def __init__(self, name: str, output: str) -> None:
        self._name, self._output = name, output
        self.called: list[tuple[str, dict]] = []

    async def list_tools(self) -> list[dict]:
        return [{"name": self._name, "description": "stock of a part",
                 "inputSchema": {"type": "object", "properties": {"partNo": {"type": "string"}}}}]

    async def call_tool(self, name: str, arguments: dict) -> Any:
        self.called.append((name, arguments))
        return self._output


def _toolcall(call_id: str, name: str, arguments: str) -> SimpleNamespace:
    return SimpleNamespace(id=call_id, function=SimpleNamespace(name=name, arguments=arguments))


def _resp(content: str | None, tool_calls: list | None) -> SimpleNamespace:
    msg = SimpleNamespace(content=content, tool_calls=tool_calls)
    return SimpleNamespace(choices=[SimpleNamespace(message=msg)])


class FakeGroq:
    """Scripts a sequence of create() responses; records the kwargs of each call."""

    def __init__(self, script: list) -> None:
        self._script, self.n, self.seen = script, 0, []
        self.chat = SimpleNamespace(completions=self)

    def create(self, **kwargs) -> SimpleNamespace:
        self.seen.append(kwargs)
        r = self._script[self.n]
        self.n += 1
        return r


def test_loop_runs_tool_then_grounds_answer() -> None:
    src = FakeSource("get_stock", "PCB-492: 1 in Noida")
    # 1st model turn: ask to call get_stock. 2nd turn: a final answer, no tools.
    groq = FakeGroq([
        _resp(None, [_toolcall("c1", "get_stock", '{"partNo": "PCB-492"}')]),
        _resp("There is 1 PCB-492 in stock in Noida.", None),
    ])
    out = asyncio.run(run_copilot(
        "how many PCB-492 in stock?", sources={"ecom": src}, groq_client=groq, model="m"))

    assert out["answer"] == "There is 1 PCB-492 in stock in Noida."
    assert src.called == [("get_stock", {"partNo": "PCB-492"})]  # real tool ran, parsed args
    assert out["toolsUsed"] == [
        {"name": "get_stock", "args": {"partNo": "PCB-492"}, "result": "PCB-492: 1 in Noida"}]
    # the tool schema reached Groq on the first turn
    assert groq.seen[0]["tools"][0]["function"]["name"] == "get_stock"
    # the tool result was fed back as a tool-role message before the final answer
    assert any(m.get("role") == "tool" and "Noida" in m.get("content", "")
               for m in groq.seen[1]["messages"])


class DeadSource:
    """A source whose token/connection is dead — every call raises."""

    async def list_tools(self) -> list[dict]:
        raise RuntimeError("invalid_grant: expired refresh token")

    async def call_tool(self, name: str, arguments: dict):  # noqa: ANN201
        raise RuntimeError("invalid_grant: expired refresh token")


def test_dead_source_is_skipped_not_fatal() -> None:
    # Salesforce token is dead, e-com is fine — the copilot must still answer, not 500.
    good = FakeSource("get_stock", "PCB-492: 1 in Noida")
    groq = FakeGroq([
        _resp(None, [_toolcall("c1", "get_stock", '{"partNo": "PCB-492"}')]),
        _resp("There is 1 in stock.", None),
    ])
    out = asyncio.run(run_copilot(
        "stock?", sources={"salesforce": DeadSource(), "ecom": good},
        groq_client=groq, model="m"))

    assert out["answer"] == "There is 1 in stock."
    assert out["sourcesUnavailable"] == ["salesforce"]  # the dead one is reported, not fatal
    assert good.called  # e-com still ran
    # Groq was only offered the working source's tool
    assert [f["function"]["name"] for f in groq.seen[0]["tools"]] == ["get_stock"]


class BoomGroq:
    """A Groq client whose create() always raises — stands in for a 413/429/outage."""

    def __init__(self, exc: Exception) -> None:
        self._exc = exc
        self.chat = SimpleNamespace(completions=self)

    def create(self, **kwargs):  # noqa: ANN003, ANN201
        raise self._exc


def test_llm_rate_limit_is_graceful_not_a_500() -> None:
    # A Groq 413/429 must become a friendly answer, never a 500 (a 500 also drops the CORS header).
    boom = BoomGroq(RuntimeError("413 rate_limit_exceeded: tokens per minute (TPM): Limit 8000"))
    out = asyncio.run(run_copilot("total items?", sources={}, groq_client=boom, model="m"))
    assert "free tier" in out["answer"].lower()
    assert out["toolsUsed"] == []


def test_answers_without_tools_when_none_armed() -> None:
    groq = FakeGroq([_resp("I have no tools to answer that.", None)])
    out = asyncio.run(run_copilot("hi", sources={}, groq_client=groq, model="m"))
    assert out["answer"] == "I have no tools to answer that."
    assert out["toolsUsed"] == []
    assert "tools" not in groq.seen[0]  # no tools param sent when nothing is armed


def test_long_salesforce_name_is_aliased_but_routes_back() -> None:
    long_name = "FFCopilot_CustomerAppointmentsapex_FFCopilot_CustomerAppointments"  # 65 chars
    assert len(long_name) > 64
    src = FakeSource(long_name, "2 appointments")
    groq = FakeGroq([
        # the model calls the ALIAS Groq was given, not the raw 65-char name
        _resp(None, [_toolcall("c1", _alias(long_name, set()), "{}")]),
        _resp("Found 2 appointments.", None),
    ])
    out = asyncio.run(
        run_copilot("appts?", sources={"salesforce": src}, groq_client=groq, model="m"))

    alias_sent = groq.seen[0]["tools"][0]["function"]["name"]
    assert len(alias_sent) <= 64  # Groq-legal
    assert src.called == [(long_name, {})]  # routed back to the real tool
    assert out["toolsUsed"][0]["name"] == long_name  # trace shows the real name
    assert out["answer"] == "Found 2 appointments."
