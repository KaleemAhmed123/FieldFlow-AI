"""Vonage RCS (Step 9b), fully offline:
  - Card → RCS payload mapping (carousel postback + payment open-url),
  - build_vonage arming (fake unless key+secret+agent+test_to all set),
  - webhook JWT signature verify (stdlib HS256 + payload_hash) and postback parsing,
  - the send→tap→resume round-trip + message_uuid dedup, via the real graph on fakes.
No network, no Vonage creds — the real send/webhook path is exercised by the gated live fire."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json

from app.config import settings
from app.db.models import AuditLog, Case
from app.services import case_service
from app.tools.vonage import FakeVonage, VonageMessagesClient, build_vonage, card_to_rcs
from app.webhooks.routes import parse_postback, verify_vonage_jwt
from fieldflow_contract import Card, SlotOption, make_event
from sqlalchemy import func, select


async def _case(sessionmaker, cid: str) -> Case:
    async with sessionmaker() as s:
        return (await s.execute(select(Case).where(Case.correlation_id == cid))).scalar_one()


# --- Card → RCS mapping --------------------------------------------------------------------------
def test_carousel_embeds_correlation_slot_version_and_caps_at_four():
    opts = [SlotOption(slotId=f"s{i}", label=f"L{i}", technician="Tech", note="Same tech")
            for i in range(5)]
    card = Card(kind="carousel", title="t", options=opts, version=2)
    msg = card_to_rcs("+919000000000", card, "astrea_it_services", "WO-9")
    cards = msg["carousel"]["cards"]
    assert msg["channel"] == "rcs" and msg["from"] == "astrea_it_services"
    assert len(cards) == 4  # RCS allows at most 4 suggestions
    assert cards[0]["suggestions"][0]["postback_data"] == "WO-9|s0|2"
    assert cards[0]["suggestions"][0]["type"] == "suggested_reply"


def test_payment_card_is_open_url_action():
    card = Card(kind="payment", title="Approve & Pay ₹3,700", payUrl="https://rzp.io/i/x")
    sugg = card_to_rcs("+919000000000", card, "agent", "WO-9")["card"]["suggestions"][0]
    assert sugg["type"] == "suggested_action" and sugg["url"] == "https://rzp.io/i/x"


# --- build_vonage arming -------------------------------------------------------------------------
def test_build_vonage_fake_unless_fully_armed(monkeypatch):
    for key in ("vonage_api_key", "vonage_api_secret", "vonage_rcs_agent_id", "vonage_test_to"):
        monkeypatch.setattr(settings, key, "")
    assert isinstance(build_vonage(settings), FakeVonage)
    # Keys present but no test recipient → still fake (a billed send must not arm by accident).
    monkeypatch.setattr(settings, "vonage_api_key", "2b000002")
    monkeypatch.setattr(settings, "vonage_api_secret", "secret")
    monkeypatch.setattr(settings, "vonage_rcs_agent_id", "astrea_it_services")
    assert isinstance(build_vonage(settings), FakeVonage)
    monkeypatch.setattr(settings, "vonage_test_to", "+919000000000")
    assert isinstance(build_vonage(settings), VonageMessagesClient)


# --- Webhook signature verify (stdlib HS256 + payload_hash) --------------------------------------
def _sign(secret: str, claims: dict) -> str:
    def seg(obj: dict) -> str:
        return base64.urlsafe_b64encode(json.dumps(obj).encode()).rstrip(b"=").decode()
    head, pay = seg({"alg": "HS256", "typ": "JWT"}), seg(claims)
    sig = base64.urlsafe_b64encode(
        hmac.new(secret.encode(), f"{head}.{pay}".encode(), hashlib.sha256).digest()
    ).rstrip(b"=").decode()
    return f"{head}.{pay}.{sig}"


def test_verify_vonage_jwt_accepts_valid_and_rejects_tampered():
    body = b'{"message_uuid":"m1","message_type":"reply"}'
    token = _sign("sign_secret", {"payload_hash": hashlib.sha256(body).hexdigest()})
    assert verify_vonage_jwt(token, body, "sign_secret") is True
    assert verify_vonage_jwt(token, body, "wrong_secret") is False      # bad signature
    assert verify_vonage_jwt(token, b'{"evil":1}', "sign_secret") is False  # body tampered
    assert verify_vonage_jwt(token, body, "") is True                   # blank secret → skip (dev)
    assert verify_vonage_jwt("not.a.jwt.x", body, "sign_secret") is False


def test_parse_postback():
    assert parse_postback("WO-1|s2|3") == {"correlationId": "WO-1", "slotId": "s2", "version": 3}
    assert parse_postback("missing-parts") is None
    assert parse_postback("a|b|notnum") is None


# --- Send → tap → resume round-trip (the real contract, on fakes) --------------------------------
async def test_inbound_postback_resumes_case_and_dedupes(sessionmaker, graph):
    event = make_event(work_order_id="WO-RCS", reason="technician_delay")
    async with sessionmaker() as s:
        await case_service.handle_event(s, event, graph=graph)
    case = await _case(sessionmaker, "WO-RCS")
    assert case.status == "OPTIONS_SENT"

    # The real client would build this postback from the sent carousel; the webhook parses it back.
    slot = case.sent_card["card"]["options"][0]["slotId"]
    pb = parse_postback(f"WO-RCS|{slot}|{case.version}")
    async with sessionmaker() as s:
        first = await case_service.resume_case(
            s, pb["correlationId"], {"slotId": pb["slotId"], "version": pb["version"]},
            graph=graph, idempotency_key="msg-uuid-1")
    assert first["status"] == "ok"
    assert (await _case(sessionmaker, "WO-RCS")).status != "OPTIONS_SENT"  # the tap advanced it

    # Same message_uuid fired twice (Vonage retry) → dropped, no re-run.
    async with sessionmaker() as s:
        again = await case_service.resume_case(
            s, pb["correlationId"], {"slotId": pb["slotId"], "version": pb["version"]},
            graph=graph, idempotency_key="msg-uuid-1")
    assert again["status"] == "duplicate"


# --- Status callback is recorded on the trail ----------------------------------------------------
async def test_record_delivery_status_writes_audit(sessionmaker, vonage):
    async with sessionmaker() as s:
        await case_service.record_delivery_status(
            s, vonage, message_uuid="m-xyz", status="delivered", to="+919000000000")
    async with sessionmaker() as s:
        rows = (await s.execute(
            select(func.count()).select_from(AuditLog).where(AuditLog.kind == "delivery_status")
        )).scalar_one()
    assert rows == 1
