"""Groq provider (primary): llama-3.3-70b-versatile with JSON-object output.

The `groq` SDK is imported lazily inside the call, so this module imports fine without the package
and the whole test suite stays offline. Only `build_proposer` wires this in, and only when
GROQ_API_KEY is set. The exact SDK call shape is verified at the gated live Groq call (the last
Step 5 task), not by any offline test.
"""

from __future__ import annotations

import logfire

from app.llm.proposer import Proposal, RateLimited, build_prompt, parse_proposal


def groq_propose(settings, reason: str, context: dict, knowledge: list) -> Proposal:
    import groq  # lazy: not needed unless a live Groq call actually happens

    client = groq.Groq(api_key=settings.groq_api_key, timeout=settings.llm_timeout_s,
                       max_retries=settings.llm_max_retries)
    system, user = build_prompt(reason, context, knowledge)
    # The groq SDK has no Logfire auto-instrumentor (unlike google-genai), so emit the standard
    # gen_ai.* span attributes by hand — that's what the Logfire LLM panel reads for token usage.
    with logfire.span(
        "groq chat {request_model}", request_model=settings.groq_model,
        **{"gen_ai.system": "groq", "gen_ai.request.model": settings.groq_model},
    ) as span:
        try:
            resp = client.chat.completions.create(
                model=settings.groq_model,
                messages=[{"role": "system", "content": system},
                          {"role": "user", "content": user}],
                response_format={"type": "json_object"},
                temperature=settings.llm_temperature,
                top_p=settings.llm_top_p,
                max_tokens=settings.llm_max_tokens,
            )
        except groq.RateLimitError as exc:  # HTTP 429 → surface Retry-After, let the ladder fall
            retry_after = None
            headers = getattr(getattr(exc, "response", None), "headers", {}) or {}
            if (ra := headers.get("retry-after")) is not None:
                try:
                    retry_after = float(ra)
                except ValueError:
                    retry_after = None
            raise RateLimited(retry_after) from exc
        usage = getattr(resp, "usage", None)
        if usage is not None:
            span.set_attributes({
                "gen_ai.response.model": getattr(resp, "model", settings.groq_model),
                "gen_ai.usage.input_tokens": getattr(usage, "prompt_tokens", 0),
                "gen_ai.usage.output_tokens": getattr(usage, "completion_tokens", 0),
            })
        return parse_proposal(resp.choices[0].message.content, "groq", reason, context)
