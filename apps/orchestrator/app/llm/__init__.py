"""LLM layer (build step 5): the proposer ladder + the evidence-weighted confidence score.

The one rule holds: the LLM only *proposes*. Everything here produces an untrusted `Proposal`
that the deterministic policy still validates, and a confidence score the LLM can only lower,
never inflate, past the human-approval gate.
"""
