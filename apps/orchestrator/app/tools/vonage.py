"""The RCS send surface, behind an interface so the real Vonage swaps in without touching callers.

Spine uses FakeVonage: it records the card instead of sending real RCS. Real Vonage Messages API
goes here later (R1 must clear first).
"""

from __future__ import annotations

from typing import Protocol

from fieldflow_contract import Card

from app.logging import get_logger

log = get_logger("vonage")


class VonageClient(Protocol):
    def send_card(self, to: str, card: Card) -> dict: ...


class FakeVonage:
    """Records 'sent' cards in memory + returns the payload the panel renders."""

    def __init__(self) -> None:
        self.sent: list[dict] = []

    def send_card(self, to: str, card: Card) -> dict:
        payload = {"to": to, "card": card.model_dump(mode="json")}
        self.sent.append(payload)
        log.info("fake_vonage.send_card", to=to, kind=card.kind, options=len(card.options))
        return payload
