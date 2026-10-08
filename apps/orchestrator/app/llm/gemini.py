"""Gemini provider (cross-provider fallback): gemini-2.5-flash with a JSON response schema.

Uses `google-genai` (the current unified SDK; `google-generativeai` is deprecated). Lazy import,
same as the Groq provider, so tests run without the package. A different provider than Groq on
purpose: a Groq rate-limit or outage shouldn't take the fallback down too. Verified live at the
gated step, not offline.
"""

from __future__ import annotations

from app.llm.proposer import PROPOSAL_SCHEMA, Proposal, build_prompt, parse_proposal


def gemini_propose(settings, reason: str, context: dict, knowledge: list) -> Proposal:
    from google import genai  # lazy: not needed unless a live Gemini call actually happens
    from google.genai import types

    client = genai.Client(api_key=settings.gemini_api_key)
    system, user = build_prompt(reason, context, knowledge)
    resp = client.models.generate_content(
        model=settings.gemini_model,
        contents=f"{system}\n\n{user}",
        config=types.GenerateContentConfig(
            temperature=settings.llm_temperature,
            top_p=settings.llm_top_p,
            max_output_tokens=settings.llm_max_tokens,
            response_mime_type="application/json",
            response_schema=PROPOSAL_SCHEMA,
        ),
    )
    return parse_proposal(resp.text, "gemini", reason)
