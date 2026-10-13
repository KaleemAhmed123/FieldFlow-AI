"""The admin copilot (build step 14): the AGENTIC read path.

NL question -> Groq tool-calling over the SF + e-com Hosted MCP servers -> grounded answer. Distinct
from the deterministic recovery pipeline (which never lets the LLM choose). Read-only guardrail:
the copilot's tools only read; it never mutates state.
"""

from app.copilot.chat import build_groq_client, run_copilot

__all__ = ["build_groq_client", "run_copilot"]
