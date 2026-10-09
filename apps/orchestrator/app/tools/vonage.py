"""The RCS send surface, behind an interface so the real Vonage swaps in without touching callers.

Spine uses FakeVonage: it records the card instead of sending real RCS. The real Vonage Messages
API client (build step 9b) drops in behind the same Protocol — one wiring line in main.py changes.

Mock-first + a safe default: `build_vonage` returns FakeVonage unless the real send is fully ARMED
(application id + private key + agent id AND a test recipient), so real creds can sit in .env during
offline dev without a send ever firing by accident.
"""

from __future__ import annotations

import time
import uuid
from pathlib import Path
from typing import Protocol
from urllib.parse import quote

from fieldflow_contract import Card

from app.logging import get_logger

log = get_logger("vonage")

MAX_SUGGESTIONS = 4  # Vonage RCS allows at most 4 suggestions per card.

# RCS requires an image on every carousel card (a text-only card is a 422). Minimalist theme: dark
# slate background, light text, the slot label rendered on it. Swap for a branded/hosted asset
# later. ponytail: placeholder image service, fine for the POC; one line to change.
CARD_MEDIA_BASE = "https://placehold.co/800x400/111827/f9fafb/png"


def _card_media(label: str) -> str:
    return f"{CARD_MEDIA_BASE}?text={quote(label)}"


class VonageClient(Protocol):
    def send_card(self, to: str, card: Card) -> dict: ...
    def send_sms(self, to: str, text: str) -> dict: ...


class FakeVonage:
    """Records 'sent' cards + SMS in memory + returns the payload the panel renders."""

    def __init__(self) -> None:
        self.sent: list[dict] = []
        self.sms: list[dict] = []  # Step 7a: the RCS→SMS fallback lands here offline

    def send_card(self, to: str, card: Card) -> dict:
        payload = {"to": to, "card": card.model_dump(mode="json")}
        self.sent.append(payload)
        log.info("fake_vonage.send_card", to=to, kind=card.kind, options=len(card.options))
        return payload

    def send_sms(self, to: str, text: str) -> dict:
        payload = {"to": to, "sms": text}
        self.sms.append(payload)
        log.info("fake_vonage.send_sms", to=to, chars=len(text))
        return payload


def card_to_rcs(to: str, card: Card, agent_id: str, correlation_id: str) -> dict:
    """Map our internal Card → a Vonage Messages API RCS payload.

    - A carousel of slots → one card per slot, each with a single `suggested_reply` whose
      `postback_data = "correlationId|slotId|version"`. Vonage echoes that string back verbatim on
      the inbound webhook, so the webhook alone knows which case, which slot, and which offer
      version (the stale-reply guard, NFR-6). Capped at 4 cards (the RCS suggestion limit).
    - A payment card → a single `suggested_action` open-url to the Razorpay short link (one tap →
      the hosted pay page). No postback: payment is confirmed by the Razorpay poll, not a webhook.

    # ponytail: the exact RCS wire shape (message_type card/carousel + suggestions) is per Vonage's
    # docs; it is the one spot to re-confirm at the gated live fire and is easy to adjust here.
    """
    base = {"from": agent_id, "to": to, "channel": "rcs"}
    if card.kind == "payment":
        return {**base, "message_type": "card", "card": {
            "title": card.title[:200],
            "suggestions": [{
                "type": "action", "text": "Approve & Pay",
                "postback_data": f"{correlation_id}|pay", "url": card.payUrl,
            }],
        }}
    cards = [{
        "title": o.label[:200],
        "text": " · ".join(p for p in (o.technician, o.note) if p)[:2000],
        "media_url": _card_media(o.label),  # RCS requires media on every carousel card
        "media_height": "MEDIUM",           # required with media_url (SHORT|MEDIUM for carousel)
        "media_description": o.label[:100],
        "suggestions": [{
            "type": "reply", "text": "Choose",
            "postback_data": f"{correlation_id}|{o.slotId}|{card.version}",
        }],
    } for o in card.options[:MAX_SUGGESTIONS]]
    return {**base, "message_type": "carousel", "carousel": {"cards": cards},
            "rcs": {"card_width": "MEDIUM"}}  # required for carousel; pairs with MEDIUM height


class VonageMessagesClient:
    """Real Vonage Messages API over RCS. Auth is a short-lived JWT (RS256) signed with the Vonage
    application's private key — RCS senders are tied to an application, so Basic auth can't identify
    the agent. `jwt`/`httpx` are imported lazily so offline imports stay dependency-free.

    The call site passes the correlationId as `to` (FakeVonage treats it as a label); the real send
    goes to the one configured test device (`vonage_test_to`) and embeds that correlationId in the
    card's postback, so the inbound webhook can resume the right case.
    """

    def __init__(self, *, application_id: str, private_key: str, agent_id: str, to: str,
                 url: str, timeout: float = 20.0) -> None:
        self._app_id, self._private_key = application_id, private_key
        self._agent_id, self._to, self._url, self._timeout = agent_id, to, url, timeout

    def _headers(self) -> dict:
        import jwt  # lazy: runtime dep (pyjwt[crypto]); offline never hits this
        now = int(time.time())
        token = jwt.encode(
            {"application_id": self._app_id, "iat": now, "exp": now + 60, "jti": str(uuid.uuid4())},
            self._private_key, algorithm="RS256",
        )
        return {"Authorization": f"Bearer {token}"}

    def _post(self, payload: dict, kind: str) -> dict:
        import httpx  # lazy: runtime dep added at the gated live fire; offline never hits this
        resp = httpx.post(self._url, json=payload, timeout=self._timeout, headers=self._headers())
        if resp.status_code >= 400:  # surface Vonage's exact complaint, don't swallow it
            log.error("vonage.rejected", kind=kind, status=resp.status_code,
                      body=resp.text, sent=payload)
        resp.raise_for_status()
        return resp.json()

    def send_card(self, to: str, card: Card) -> dict:
        correlation_id = to  # the call site passes correlationId here; the device is self._to
        payload = card_to_rcs(self._to, card, self._agent_id, correlation_id)
        data = self._post(payload, "card")
        log.info("vonage.send_card", to=self._to, kind=card.kind,
                 message_uuid=data.get("message_uuid"))
        return {"to": self._to, "card": card.model_dump(mode="json"),
                "messageUuid": data.get("message_uuid")}

    def send_sms(self, to: str, text: str) -> dict:
        """Step 7a fallback: the same options as a plain SMS when the RCS card didn't deliver."""
        payload = {"from": self._agent_id, "to": self._to, "channel": "sms",
                   "message_type": "text", "text": text}
        data = self._post(payload, "sms")
        log.info("vonage.send_sms", to=self._to, message_uuid=data.get("message_uuid"))
        return {"to": self._to, "sms": text, "messageUuid": data.get("message_uuid")}


def build_vonage(settings) -> VonageClient:
    """Pick the client from settings. Real send is ARMED only when the application id, its private
    key file, the agent id AND a test recipient are all set; otherwise FakeVonage (the safe offline
    default) — so real creds can sit in .env without a billed send firing until the test number is
    deliberately set right before a demo."""
    private_key = ""
    if settings.vonage_private_key_path:
        try:
            private_key = Path(settings.vonage_private_key_path).read_text()
        except OSError as exc:
            log.error("vonage.private_key_unreadable", path=settings.vonage_private_key_path,
                      error=str(exc))
    armed = all((settings.vonage_application_id, private_key,
                 settings.vonage_rcs_agent_id, settings.vonage_test_to))
    if not armed:
        if settings.vonage_application_id:
            log.info("vonage.fake", reason="application/key/agent/test_to incomplete; not armed")
        return FakeVonage()
    log.info("vonage.live", to=settings.vonage_test_to)
    return VonageMessagesClient(
        application_id=settings.vonage_application_id, private_key=private_key,
        agent_id=settings.vonage_rcs_agent_id, to=settings.vonage_test_to,
        url=settings.vonage_messages_url,
    )
