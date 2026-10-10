"""Build step 12 — the real Salesforce adapter (Apex REST), proven offline.

No org, no network: httpx.MockTransport drives the real client code path with canned responses that
match apps/salesforce-apex/FieldFlowRest.cls. Covers the OAuth token fetch, the read mapping, 404 →
None, the 401-refetch (OQ4), the slot-label → UTC conversion (OQ2) + the reschedule body, and the
build_salesforce arming gate.
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import httpx
import pytest
from app.config import Settings
from app.tools.salesforce import (
    FakeSalesforce,
    RestSalesforce,
    build_salesforce,
    slot_label_to_times,
)

TZ = "Asia/Kolkata"
TOKEN_PATH = "/services/oauth2/token"
APEX = "/services/apexrest/fieldflow"


def _rest(handler) -> RestSalesforce:
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return RestSalesforce(
        login_url="https://login.my.salesforce.com", client_id="id", client_secret="sec",
        tz_name=TZ, client=client,
    )


def _token_response() -> httpx.Response:
    return httpx.Response(
        200, json={"access_token": "tok-1", "instance_url": "https://inst.my.salesforce.com"}
    )


# --- slot label → UTC (OQ2) -------------------------------------------------------------------

def test_label_to_utc_today() -> None:
    # 15:00 IST (UTC+5:30) == 09:30 UTC. now is before the slot, same day.
    now = datetime(2026, 10, 12, 8, 0, tzinfo=ZoneInfo(TZ))
    start, end = slot_label_to_times("TODAY 15:00-17:00", TZ, now=now)
    assert start == "2026-10-12T09:30:00Z"
    assert end == "2026-10-12T11:30:00Z"


def test_label_to_utc_tomorrow_rolls_the_date() -> None:
    now = datetime(2026, 10, 12, 8, 0, tzinfo=ZoneInfo(TZ))
    start, end = slot_label_to_times("TOMORROW 09:00-11:00", TZ, now=now)
    assert start == "2026-10-13T03:30:00Z"  # 09:00 IST next day == 03:30 UTC
    assert end == "2026-10-13T05:30:00Z"


def test_unparseable_label_fails_loud() -> None:
    with pytest.raises(ValueError):
        slot_label_to_times("whenever you like", TZ)


# --- reads -----------------------------------------------------------------------------------

def test_read_authenticates_then_maps_appointment() -> None:
    appt = {"appointmentId": "SA-19281", "customerId": "003x", "assetId": "02ix",
            "resourceId": "0Hnx", "slaWindowMinutes": 120, "caseState": "Scheduled"}

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path == TOKEN_PATH:
            return _token_response()
        assert req.url.path == f"{APEX}/appointment/SA-19281"
        assert req.headers["Authorization"] == "Bearer tok-1"
        return httpx.Response(200, json=appt)

    sf = _rest(handler)
    assert sf.get_appointment("SA-19281") == appt


def test_unknown_id_returns_none() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path == TOKEN_PATH:
            return _token_response()
        return httpx.Response(404, json={"error": "asset not found"})

    assert _rest(handler).get_asset("AST-nope") is None


def test_token_is_fetched_once_and_cached() -> None:
    calls = {"token": 0, "read": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path == TOKEN_PATH:
            calls["token"] += 1
            return _token_response()
        calls["read"] += 1
        return httpx.Response(200, json={"name": "Kaleem Ahmed", "phone": "+91-90000-00000"})

    sf = _rest(handler)
    sf.get_customer("003x")
    sf.get_customer("003x")
    assert calls == {"token": 1, "read": 2}  # OQ4: one auth, reused across reads


def test_expired_token_refetched_once_on_401() -> None:
    state = {"tokens": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path == TOKEN_PATH:
            state["tokens"] += 1
            return _token_response()
        # First authed call sees the stale token → 401; after the re-auth it succeeds.
        if state["tokens"] == 1:
            return httpx.Response(401, json={"error": "Session expired"})
        return httpx.Response(200, json={"model": "XYZ-492", "warranty": "active"})

    sf = _rest(handler)
    assert sf.get_asset("02ix") == {"model": "XYZ-492", "warranty": "active"}
    assert state["tokens"] == 2  # re-authenticated exactly once


# --- reschedule (the mutation) ---------------------------------------------------------------

def test_reschedule_posts_utc_times_and_keeps_slotid() -> None:
    sent = {}

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path == TOKEN_PATH:
            return _token_response()
        assert req.method == "POST" and req.url.path == f"{APEX}/reschedule"
        import json as _json
        sent.update(_json.loads(req.content))
        return httpx.Response(200, json={"appointmentId": sent["appointmentId"],
                                         "status": "RESCHEDULED"})

    sf = _rest(handler)
    out = sf.reschedule("SA-19281", "t-today-1", "TODAY 11:00-13:00")
    assert sent["appointmentId"] == "SA-19281"
    assert sent["startTime"].endswith("Z") and sent["endTime"].endswith("Z")  # UTC ISO-8601
    assert out["slotId"] == "t-today-1" and out["status"] == "RESCHEDULED"  # fake-shape parity


def test_reschedule_without_label_fails_loud() -> None:
    sf = _rest(lambda req: _token_response())
    with pytest.raises(ValueError):
        sf.reschedule("SA-19281", "t-today-1")  # no label → can't know the time


# --- the arming gate -------------------------------------------------------------------------

def test_build_salesforce_is_fake_when_unarmed() -> None:
    assert isinstance(build_salesforce(Settings(sf_login_url="")), FakeSalesforce)


def test_build_salesforce_is_rest_when_creds_set() -> None:
    s = Settings(sf_login_url="https://x.my.salesforce.com", sf_client_id="id",
                 sf_client_secret="sec")
    assert isinstance(build_salesforce(s), RestSalesforce)
