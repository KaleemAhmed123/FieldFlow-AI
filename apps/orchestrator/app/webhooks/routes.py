"""Real Vonage webhooks (build step 9b) — the real counterpart of /sim/*.

POST /webhooks/inbound  → the customer's RCS suggested-reply tap resumes the paused case.
POST /webhooks/status   → delivered/read/failed callbacks are recorded on the case (the Step-7
                          RCS→SMS fallback will consume them).

Robustness (OQ5): every callback's Vonage JWT is signature-verified (HMAC-SHA256 with the account
signature secret) + a payload_hash body check; inbound is deduped by `message_uuid` (reuses the
IdempotencyKey table via resume_case); handlers return 200 fast. The signature check is stdlib only
(hmac/hashlib/base64) — no JWT library needed. /sim/* stays the offline twin; both hit resume_case.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json

from fastapi import APIRouter, Request, Response

from app.config import settings
from app.db.session import get_sessionmaker
from app.logging import get_logger
from app.services import case_service

router = APIRouter(prefix="/webhooks", tags=["webhooks"])
log = get_logger("webhooks")


def _b64url_decode(seg: str) -> bytes:
    return base64.urlsafe_b64decode(seg + "=" * (-len(seg) % 4))


def verify_vonage_jwt(token: str, body: bytes, secret: str) -> bool:
    """True if `token` is a valid Vonage webhook JWT for `body`.

    Vonage signs webhooks HS256 with the account signature secret and includes a `payload_hash`
    claim (SHA-256 of the body) to defeat replay/tampering. A blank secret disables the check (dev
    convenience) — fine offline; set VONAGE_SIGNATURE_SECRET before exposing the tunnel.
    """
    if not secret:
        return True
    try:
        header_b64, payload_b64, sig_b64 = token.split(".")
    except ValueError:
        return False
    expected = hmac.new(secret.encode(), f"{header_b64}.{payload_b64}".encode(),
                        hashlib.sha256).digest()
    if not hmac.compare_digest(expected, _b64url_decode(sig_b64)):
        return False
    try:
        claims = json.loads(_b64url_decode(payload_b64))
    except ValueError:
        return False
    ph = claims.get("payload_hash")
    return not (ph and ph != hashlib.sha256(body).hexdigest())


def parse_postback(data: str) -> dict | None:
    """'correlationId|slotId|version' → the resume payload; None if malformed."""
    parts = (data or "").split("|")
    if len(parts) != 3 or not parts[2].isdigit():
        return None
    return {"correlationId": parts[0], "slotId": parts[1], "version": int(parts[2])}


def _bearer(request: Request) -> str:
    header = request.headers.get("authorization", "")
    return header[7:] if header[:7].lower() == "bearer " else ""


@router.post("/inbound")
async def inbound(request: Request) -> Response:
    """A real customer tap. Verify → parse the postback → resume the case (deduped by message_uuid).
    Always 200: an unverified/garbage callback is logged and dropped, never retried into error."""
    body = await request.body()
    if not verify_vonage_jwt(_bearer(request), body, settings.vonage_signature_secret):
        log.info("webhook.inbound.unverified")
        return Response(status_code=200)
    data = json.loads(body or b"{}")
    if data.get("message_type") != "reply":
        return Response(status_code=200)  # ignore plain text / other inbound for now
    pb = parse_postback((data.get("reply") or {}).get("id", ""))
    if pb is None:
        log.info("webhook.inbound.bad_postback")
        return Response(status_code=200)
    async with get_sessionmaker()() as session:
        await case_service.resume_case(
            session, pb["correlationId"], {"slotId": pb["slotId"], "version": pb["version"]},
            graph=request.app.state.graph, idempotency_key=data.get("message_uuid"),
        )
    return Response(status_code=200)


@router.post("/status")
async def status(request: Request) -> Response:
    """A delivery-status callback (delivered/read/failed). Verify → record on the case + trail."""
    body = await request.body()
    if not verify_vonage_jwt(_bearer(request), body, settings.vonage_signature_secret):
        return Response(status_code=200)
    data = json.loads(body or b"{}")
    async with get_sessionmaker()() as session:
        await case_service.record_delivery_status(
            session, request.app.state.vonage, message_uuid=data.get("message_uuid"),
            status=data.get("status"), to=(data.get("to") or {}).get("number"),
        )
    return Response(status_code=200)
