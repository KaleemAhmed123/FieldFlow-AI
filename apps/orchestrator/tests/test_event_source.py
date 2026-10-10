"""Step 9c — the Salesforce at-risk trigger, proven offline.

The pure mapper is the reusable core (Salesforce payload -> our contract event); the source stays
None unless the Pub/Sub creds are armed, so /sim remains the trigger in every test. No org, no deps.
"""

from __future__ import annotations

import pytest
from app.config import Settings
from app.events import build_event_source, platform_event_to_at_risk


def test_maps_salesforce_custom_field_payload() -> None:
    ev = platform_event_to_at_risk(
        {
            "WorkOrderId__c": "WO-555",
            "AppointmentId__c": "SA-19281",
            "Reason__c": "part_missing",
            "DelayMinutes__c": 0,
            "EventUuid": "sf-evt-1",
        }
    )
    assert ev.event == "appointment.at_risk"
    assert ev.correlationId == "WO-555" and ev.workOrderId == "WO-555"
    assert ev.appointmentId == "SA-19281"
    assert ev.reason == "part_missing"
    assert ev.eventId == "sf-evt-1"  # SF's own uuid reused as the idempotency key (NFR-2)


def test_maps_plain_payload_and_delay() -> None:
    ev = platform_event_to_at_risk(
        {
            "workOrderId": "WO-1",
            "appointmentId": "SA-1",
            "reason": "technician_delay",
            "delayMinutes": 45,
        }
    )
    assert ev.detail == {"delayMinutes": 45}


def test_unknown_reason_falls_back_to_safe_default() -> None:
    ev = platform_event_to_at_risk(
        {"workOrderId": "WO-1", "appointmentId": "SA-1", "reason": "aliens"}
    )
    assert ev.reason == "technician_delay"


def test_missing_ids_fail_loud() -> None:
    with pytest.raises(ValueError):
        platform_event_to_at_risk({"reason": "part_missing"})


def test_source_is_none_when_unarmed() -> None:
    # Blank SF creds (the offline default) → no real subscriber; /sim stays the trigger.
    s = Settings(sf_login_url="", sf_client_id="", sf_client_secret="")
    assert build_event_source(s) is None


def test_creds_alone_arm_rest_but_not_the_trigger() -> None:
    # OQ1: the 3 creds arm the REST reads, but the still-stubbed gRPC trigger stays OFF until it is
    # explicitly enabled — so going live on reads never starts the unfinished subscriber task.
    s = Settings(
        sf_login_url="https://x.my.salesforce.com", sf_client_id="id", sf_client_secret="sec"
    )
    assert s.sf_rest_armed is True
    assert s.sf_pubsub_armed is False
    assert build_event_source(s) is None


def test_source_built_when_armed_and_enabled() -> None:
    s = Settings(
        sf_login_url="https://x.my.salesforce.com", sf_client_id="id", sf_client_secret="sec",
        sf_pubsub_enabled=True,
    )
    assert build_event_source(s) is not None
