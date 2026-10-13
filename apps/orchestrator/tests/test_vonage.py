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
from app.tools.vonage import (
    FakeVonage,
    VonageMessagesClient,
    actions_to_suggestions,
    build_vonage,
    card_to_rcs,
)
from app.webhooks.routes import parse_postback, status_recipient, verify_vonage_jwt
from fieldflow_contract import Card, CardAction, SlotOption, make_event
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
    assert cards[0]["suggestions"][0]["type"] == "reply"
    assert cards[0]["media_url"].startswith("https://")  # RCS requires media on every card


def test_payment_card_is_open_url_action():
    # RCS has no "action" suggestion type — the pay chip is an open_url. The standalone card ALSO
    # requires text + media_url + media_height + the rcs object + the open_url's description
    # (all missing → the #1020 422 that 500'd the parts/pay flow).
    card = Card(kind="payment", title="Approve & Pay ₹3,700", payUrl="https://rzp.io/i/x")
    msg = card_to_rcs("916394493446", card, "agent", "WO-9")
    c = msg["card"]
    assert c["text"] and c["media_url"].startswith("https://") and c["media_height"]
    assert msg["rcs"]["card_orientation"] and msg["rcs"]["image_alignment"]
    sugg = c["suggestions"][0]
    assert sugg["type"] == "open_url" and sugg["url"] == "https://rzp.io/i/x"
    assert sugg["description"]  # open_url needs a description


def test_confirmation_is_a_standalone_rich_card():
    # A card with NO slot options (confirmation) maps to a standalone rich card — never an empty
    # carousel (a 422). Vonage requires title + text + media_url + media_height + the rcs object.
    card = Card(kind="confirmation", title="You're all set", body="You're confirmed for TOMORROW.",
                actions=[CardAction(type="calendar", label="Add to calendar", value="TOMORROW"),
                         CardAction(type="pdf", label="Service report (PDF)", value="https://x/r.pdf")])
    msg = card_to_rcs("916394493446", card, "agent", "WO-9")
    assert msg["message_type"] == "card" and "carousel" not in msg
    c = msg["card"]
    assert c["text"] == "You're confirmed for TOMORROW." and c["media_url"].startswith("https://")
    assert c["media_height"] and msg["rcs"]["card_orientation"] and msg["rcs"]["image_alignment"]
    pdf = c["suggestions"][0]  # calendar omitted; the PDF open_url carries the required description
    assert pdf["type"] == "open_url" and pdf["url"] == "https://x/r.pdf" and pdf["description"]


def test_actions_map_to_rcs_suggestions():
    chips = actions_to_suggestions([
        CardAction(type="share_location", label="Share my location"),
        CardAction(type="dial", label="Call Rahul", value="+91-90000-00042"),
        CardAction(type="view", label="View appointment", value="https://x/case"),
        CardAction(type="calendar", label="Add to calendar", value="TODAY 15:00"),  # omitted
    ])
    # Only Vonage's valid flat chip types — a `type:"action"` is the #1020 422 that bit live.
    assert all(c["type"] != "action" for c in chips)
    assert chips[0] == {"type": "share_location", "text": "Share my location",
                        "postback_data": "share_location"}  # no `share_location:true` flag
    assert chips[1]["type"] == "dial" and chips[1]["phone_number"] == "+919000000042"  # E.164, no -
    assert chips[1]["fallback_url"]                                   # dial requires a fallback
    # open_url carries the required description
    assert chips[2] == {"type": "open_url", "text": "View appointment", "postback_data": "view",
                        "description": "View appointment", "url": "https://x/case"}
    assert len(chips) == 3                                            # calendar has no POC chip


def test_status_recipient_accepts_string_and_dict():
    # Vonage sends the status callback `to` as a bare string on RCS (a dict was assumed → 500 loop).
    assert status_recipient({"to": "916306026859"}) == "916306026859"
    assert status_recipient({"to": {"number": "916306026859"}}) == "916306026859"
    assert status_recipient({}) is None


# --- build_vonage arming -------------------------------------------------------------------------
def test_build_vonage_fake_unless_fully_armed(monkeypatch, tmp_path):
    for key in ("vonage_application_id", "vonage_private_key_path",
                "vonage_rcs_agent_id", "vonage_test_to"):
        monkeypatch.setattr(settings, key, "")
    assert isinstance(build_vonage(settings), FakeVonage)
    # App id + key + agent present but no test recipient → still fake (no accidental billed send).
    key_file = tmp_path / "private.key"
    key_file.write_text("dummy-pem")
    monkeypatch.setattr(settings, "vonage_application_id", "a391d76e")
    monkeypatch.setattr(settings, "vonage_private_key_path", str(key_file))
    monkeypatch.setattr(settings, "vonage_rcs_agent_id", "astrea_it")
    assert isinstance(build_vonage(settings), FakeVonage)
    monkeypatch.setattr(settings, "vonage_test_to", "916394493446")
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
