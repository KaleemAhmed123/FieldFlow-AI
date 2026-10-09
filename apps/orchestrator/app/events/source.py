"""The at-risk event SOURCE seam (build step 9c).

Today `/sim/appointment-at-risk` publishes the contract event straight onto RabbitMQ. In production
the trigger is a real Salesforce **Platform Event** (`Appointment_At_Risk__e`) delivered over the
**Pub/Sub API**. This module is the seam between the two: a source subscribes to Salesforce and
publishes the SAME contract event onto the SAME exchange, so the consumer, graph, policy and RCS
downstream never change — only *where* the event comes from.

Mock-first boundary (why this is safe to ship before the org exists):
- `platform_event_to_at_risk` (Salesforce payload -> our contract event) is pure and unit-tested
  offline with NO new deps — it is the reusable core.
- `build_event_source` returns None unless the Pub/Sub creds are set, so a keyless boot and every
  test keep `/sim` as the trigger.
- The real gRPC subscription body in `SalesforcePubSubSource.run` is the **gated live step**: it
  needs the provisioned org + the grpc/avro deps (same pattern as `uv add razorpay`). See
  docs/specs/field-service-recovery/salesforce-handoff.md §5.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, Protocol, get_args

from fieldflow_contract import AppointmentAtRisk, Reason

from app.logging import get_logger

log = get_logger("events")

_REASONS = set(get_args(Reason))  # the allowed at-risk reasons (the contract Literal)

Publish = Callable[[AppointmentAtRisk], Awaitable[None]]


def platform_event_to_at_risk(payload: dict[str, Any]) -> AppointmentAtRisk:
    """Map a Salesforce `Appointment_At_Risk__e` Platform Event payload to our contract event.

    Tolerant of the Salesforce `__c` custom-field suffix, so a hand-built test payload and the real
    org's payload both map. Raises ValueError on a payload missing the ids the case is keyed on — a
    malformed event must fail loud, not silently mis-route (the golden rule from the 9b live fire).
    """

    def field(*names: str, default: Any = None) -> Any:
        for n in names:
            v = payload.get(n)
            if v is not None:
                return v
        return default

    work_order_id = field("WorkOrderId__c", "workOrderId")
    appointment_id = field("AppointmentId__c", "appointmentId")
    if not work_order_id or not appointment_id:
        raise ValueError(f"at-risk event missing workOrderId/appointmentId: {payload!r}")

    reason = field("Reason__c", "reason", default="technician_delay")
    if reason not in _REASONS:
        log.warning("event.unknown_reason", reason=reason)  # keep going with a safe default
        reason = "technician_delay"

    delay = field("DelayMinutes__c", "delayMinutes", default=0)
    event = AppointmentAtRisk(
        correlationId=str(work_order_id),
        workOrderId=str(work_order_id),
        appointmentId=str(appointment_id),
        reason=reason,
        detail={"delayMinutes": int(delay)} if delay else {},
    )
    # Reuse Salesforce's own event uuid as our idempotency key, so a redelivered Pub/Sub event
    # dedupes at the consumer (NFR-2). Absent (a test payload) → the envelope's generated id stands.
    event_uuid = field("EventUuid", "eventId")
    if event_uuid:
        event.eventId = str(event_uuid)
    return event


class EventSource(Protocol):
    """A long-running trigger: subscribe somewhere, call `publish` for each at-risk event."""

    async def run(self, publish: Publish) -> None: ...
    async def stop(self) -> None: ...


class SalesforcePubSubSource:
    """Real trigger: subscribe to the `Appointment_At_Risk__e` Platform Event over Salesforce's
    Pub/Sub API (gRPC + Avro) and publish each as our contract event. GATED — only constructed when
    the creds are armed; the gRPC body lands with the provisioned org (salesforce-handoff.md §5)."""

    def __init__(self, settings: Any) -> None:
        self._login_url = settings.sf_login_url
        self._client_id = settings.sf_client_id
        self._client_secret = settings.sf_client_secret
        self._topic = settings.sf_pubsub_topic
        self._endpoint = settings.sf_pubsub_endpoint
        self._stopped = False

    async def run(self, publish: Publish) -> None:
        # The live step fills this in once the org exists (kept out now — unbuildable + untestable
        # without a real org, and the grpc/avro deps are heavy):
        #   1. OAuth client-credentials -> access token + instance url
        #   2. open a gRPC channel to self._endpoint, auth via call metadata
        #   3. GetSchema for the topic (Avro), then Subscribe to self._topic
        #   4. each event: Avro-decode -> platform_event_to_at_risk(payload) -> await publish(ev)
        raise RuntimeError(
            "SalesforcePubSubSource is armed but its gRPC subscription is the gated live step. "
            "Provision the org + Appointment_At_Risk__e, add the pubsub deps, then fill run(). "
            "Until then leave SF_* creds blank so /sim stays the trigger (salesforce-handoff.md)."
        )

    async def stop(self) -> None:
        self._stopped = True


def build_event_source(settings: Any) -> EventSource | None:
    """The one swap line: a real Pub/Sub source when the creds are ARMED, else None so `/sim` is the
    trigger (the offline default — every test and a keyless boot)."""
    if settings.sf_pubsub_armed:
        log.info("events.source.salesforce_pubsub", topic=settings.sf_pubsub_topic)
        return SalesforcePubSubSource(settings)
    return None
