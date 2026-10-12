"""Step 9c live path — the Salesforce HTTP-callout endpoint POST /webhooks/sf/at-risk.

The Apex trigger POSTs an at-risk ServiceAppointment here; the endpoint maps it (reusing the tested
`platform_event_to_at_risk`) and publishes onto the same exchange /sim uses. Proven offline against
a tiny app + a fake broker — no org, no RabbitMQ. Guards: shared-secret header, malformed-payload.
"""

from __future__ import annotations

from app.config import settings
from app.webhooks import router
from fastapi import FastAPI
from fastapi.testclient import TestClient


class FakeBroker:
    def __init__(self) -> None:
        self.published: list[tuple[str, dict]] = []

    async def publish(self, routing_key: str, body: dict) -> None:
        self.published.append((routing_key, body))


def _client(broker: FakeBroker | None) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.state.broker = broker
    return TestClient(app)


def test_publishes_mapped_event(monkeypatch) -> None:
    monkeypatch.setattr(settings, "sf_hook_secret", "")  # offline: no secret required
    broker = FakeBroker()
    r = _client(broker).post(
        "/webhooks/sf/at-risk",
        json={"WorkOrderId__c": "WO-9", "AppointmentId__c": "SA-0003",
              "Reason__c": "part_missing", "EventUuid": "sf-9"},
    )
    assert r.status_code == 200 and r.json()["correlationId"] == "WO-9"
    assert len(broker.published) == 1
    routing_key, body = broker.published[0]
    assert routing_key == "appointment.at_risk"
    assert body["workOrderId"] == "WO-9" and body["appointmentId"] == "SA-0003"
    assert body["reason"] == "part_missing" and body["eventId"] == "sf-9"  # SF uuid → idempotency


def test_rejects_bad_secret(monkeypatch) -> None:
    monkeypatch.setattr(settings, "sf_hook_secret", "topsecret")
    broker = FakeBroker()
    r = _client(broker).post(
        "/webhooks/sf/at-risk",
        headers={"X-FieldFlow-Secret": "wrong"},
        json={"workOrderId": "WO-1", "appointmentId": "SA-1"},
    )
    assert r.status_code == 401 and broker.published == []


def test_good_secret_passes(monkeypatch) -> None:
    monkeypatch.setattr(settings, "sf_hook_secret", "topsecret")
    broker = FakeBroker()
    r = _client(broker).post(
        "/webhooks/sf/at-risk",
        headers={"X-FieldFlow-Secret": "topsecret"},
        json={"workOrderId": "WO-1", "appointmentId": "SA-1", "reason": "technician_delay"},
    )
    assert r.status_code == 200 and len(broker.published) == 1


def test_malformed_payload_fails_loud(monkeypatch) -> None:
    monkeypatch.setattr(settings, "sf_hook_secret", "")
    broker = FakeBroker()
    r = _client(broker).post("/webhooks/sf/at-risk", json={"reason": "part_missing"})  # no ids
    assert r.status_code == 400 and broker.published == []
