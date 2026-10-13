"""Admin copilot: NL question -> Groq tool-calling over MCP tools -> grounded answer (step 14).

Groq picks tools; we execute them over the SF + e-com MCP servers and feed results back until Groq
answers (or a hard step cap trips). READ-ONLY: the tools only read; the copilot never mutates — the
guardrail. Single-turn (no history) and Groq-only this slice — a Gemini fallback is a later seam.
The returned `toolsUsed` is a mini decision-trace: the same 'show your work' idea as the pipeline.
"""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any

from app.logging import get_logger

log = get_logger("copilot")

_MAX_STEPS = 5  # ponytail: hard cap so a confused model can't tool-call forever

_SYSTEM = (
    "You are FieldFlow's admin copilot for field-service operations and spare-parts inventory. "
    "Answer the operator's question using ONLY the provided tools and their results — never "
    "invent data. The tools are READ-ONLY; never claim you changed anything. If no tool fits the "
    "question, say so plainly. Keep answers short and factual."
)


def _alias(name: str, taken: set[str]) -> str:
    """A Groq-safe function name (<=64 chars, [A-Za-z0-9_-]). Salesforce's hosted MCP mangles tool
    names into ~65-char strings that Groq rejects, so we alias them and map back when calling."""
    base = re.sub(r"[^A-Za-z0-9_-]", "_", name)[:60] or "tool"
    alias, i = base, 1
    while alias in taken:
        alias = f"{base[:56]}_{i}"
        i += 1
    taken.add(alias)
    return alias


def _content_to_text(content: Any) -> str:
    """Flatten MCP tool content blocks (or a plain string) to text for the model."""
    if isinstance(content, str):
        return content
    parts = []
    for c in content or []:
        t = getattr(c, "text", None)
        parts.append(t if t is not None else str(c))
    return "\n".join(p for p in parts if p)


async def _gather(
    sources: dict[str, Any],
) -> tuple[list[dict], dict[str, tuple[Any, str]], list[str]]:
    """List tools from every source. A source that fails (e.g. a dead Salesforce token) is skipped,
    not fatal — the copilot still answers from the sources that work. Returns (Groq tool schemas,
    alias -> (source, real name), names of unavailable sources)."""
    schemas: list[dict] = []
    route: dict[str, tuple[Any, str]] = {}
    taken: set[str] = set()
    down: list[str] = []
    for label, src in sources.items():
        try:
            tools = await src.list_tools()
        except Exception as exc:  # one bad source must not take the whole copilot down
            log.warning("copilot.source_unavailable", source=label, error=str(exc))
            down.append(label)
            continue
        for t in tools:
            alias = _alias(t["name"], taken)
            route[alias] = (src, t["name"])
            schemas.append({"type": "function", "function": {
                "name": alias, "description": t.get("description", ""),
                "parameters": t.get("inputSchema") or {"type": "object", "properties": {}},
            }})
    return schemas, route, down


def _result(answer: str, used: list, down: list, *, truncated: bool = False) -> dict:
    out: dict = {"answer": answer, "toolsUsed": used}
    if down:
        out["sourcesUnavailable"] = down
    if truncated:
        out["truncated"] = True
    return out


# ponytail: cap each tool result fed back to the model so one big list (e.g. all 86 parts) can't
# blow Groq's free-tier ~8k tokens/min budget and 413 the turn. Raise it if you leave the free tier.
_TOOL_RESULT_CAP = 2500


class _LlmError(Exception):
    """A model-call failure (rate limit, size, outage) carrying a user-facing message."""


def _friendly_llm_error(exc: Exception) -> str:
    m = str(exc).lower()
    if any(k in m for k in ("rate_limit", "too large", "413", "429", "tokens per minute", "tpm")):
        return ("That needed more data than the model's free tier allows (Groq ~8k tokens/min). "
                "Ask something narrower — e.g. the stock of one part — or upgrade the Groq tier.")
    return "The copilot couldn't reach the model just now. Please try again."


async def _llm_create(groq_client: Any, **kwargs) -> Any:
    """Call Groq off the event loop; turn any failure into an _LlmError (never a 500)."""
    try:
        return await asyncio.to_thread(groq_client.chat.completions.create, **kwargs)
    except Exception as exc:  # Groq 413/429, network, bad request — all handled gracefully
        log.warning("copilot.llm_error", error=str(exc))
        raise _LlmError(_friendly_llm_error(exc)) from exc


async def run_copilot(
    message: str, *, sources: dict[str, Any], groq_client: Any, model: str,
) -> dict:
    """One single-turn copilot answer. `sources` = {label: McpClient}; empty → the model answers
    from nothing (or says it needs a tool). Returns {answer, toolsUsed[, truncated]}. A model
    error (rate limit, size) returns a friendly message — it never raises to a 500."""
    schemas, route, down = await _gather(sources)
    messages: list[dict] = [{"role": "system", "content": _SYSTEM},
                            {"role": "user", "content": message}]
    used: list[dict] = []
    try:
        return await _run_loop(message, messages, schemas, route, down, used, groq_client, model)
    except _LlmError as exc:
        return _result(str(exc), used, down)


async def _run_loop(message, messages, schemas, route, down, used, groq_client, model):  # noqa: ANN001, ANN201
    for _ in range(_MAX_STEPS):
        kwargs: dict = {"model": model, "messages": messages, "temperature": 0}
        if schemas:
            kwargs["tools"] = schemas
            kwargs["tool_choice"] = "auto"
        resp = await _llm_create(groq_client, **kwargs)
        msg = resp.choices[0].message
        calls = msg.tool_calls or []
        if not calls:
            return _result(msg.content or "", used, down)
        # OpenAI/Groq require the assistant message that requested the calls before the results.
        messages.append({
            "role": "assistant", "content": msg.content or "",
            "tool_calls": [{"id": tc.id, "type": "function",
                            "function": {"name": tc.function.name,
                                         "arguments": tc.function.arguments}} for tc in calls],
        })
        for tc in calls:
            alias = tc.function.name
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            target = route.get(alias)
            if target is None:
                text, real = f"error: unknown tool {alias}", alias
            else:
                src, real = target
                try:
                    text = _content_to_text(await src.call_tool(real, args))
                except Exception as exc:  # a tool failure must not crash the chat
                    log.warning("copilot.tool_failed", tool=real, error=str(exc))
                    text = f"error calling tool: {type(exc).__name__}: {exc}"
            used.append({"name": real, "args": args, "result": text[:2000]})
            model_text = text if len(text) <= _TOOL_RESULT_CAP else \
                text[:_TOOL_RESULT_CAP] + "\n…[truncated — too long for the model's token budget]"
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": model_text})
    # Step cap reached — one last call with no tools to force a final answer.
    resp = await _llm_create(groq_client, model=model, messages=messages, temperature=0)
    return _result(resp.choices[0].message.content or "", used, down, truncated=True)


def build_groq_client(settings: Any) -> Any:
    """Lazy Groq client for the copilot (imported only when a live call happens)."""
    import groq

    return groq.Groq(api_key=settings.groq_api_key, timeout=settings.llm_timeout_s,
                     max_retries=settings.llm_max_retries)
