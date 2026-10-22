"""Salesforce read/action backing behind an interface. Fake-vs-REST stays swappable.

Split concern-wise (one method per object) so the graph composes context from granular reads and
the decision trace's `toolsUsed` is real. The Toolbox (app/tools/registry.py) wraps these as the
tool surface; the action tool runs the authority ladder before `reschedule` is applied.

Two implementations behind one Protocol:
  - FakeSalesforce — in-memory demo org (offline default, every test).
  - RestSalesforce — the real org via the Apex REST class in apps/salesforce-apex/ (build step 12),
    armed only when the client-credentials creds are set. `build_salesforce` is the one swap line
    (same convention as build_vonage / build_gateway). Reads go live first; reschedule is the one
    mutation and is gated on the Apex class being deployed.

FakeSalesforce resolves one demo appointment to its linked customer/asset/technician — the same
appointment → related-records shape the Apex REST reads return. Unknown ids return None so an action
tool can refuse.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any, Protocol
from urllib.parse import quote, urlencode
from zoneinfo import ZoneInfo

from app.logging import get_logger

if TYPE_CHECKING:
    import httpx

log = get_logger("salesforce")


class SalesforceTools(Protocol):
    def get_appointment(self, appointment_id: str) -> dict | None: ...
    def get_customer(self, customer_id: str) -> dict | None: ...
    def get_asset(self, asset_id: str) -> dict | None: ...
    def get_technician(self, resource_id: str) -> dict | None: ...
    def get_slots(self, appointment_id: str) -> list[dict]: ...
    def reschedule(
        self, appointment_id: str, slot_id: str, slot_label: str | None = None,
        start_time: str | None = None, end_time: str | None = None,
    ) -> dict: ...
    def record_payment(
        self, receipt: dict, appointment_id: str | None = None
    ) -> dict: ...


class FakeSalesforce:
    """In-memory demo org. One appointment links to a customer, asset and technician."""

    def __init__(self) -> None:
        # Step 7b: flip this (via /sim/fault) to simulate Salesforce being down — every read then
        # raises, the consumer handler fails, and the message dead-letters to events.dlq.
        self.down: bool = False
        self._payments: dict[str, dict] = {}  # paymentId -> stored payment (idempotent by key)
        # Real-availability offline twin: empty by default so the graph falls back to the proposer's
        # canned slots (unchanged offline behaviour). A test seeds this to exercise the scheduler.
        self._slots: list[dict] = []
        self._appointments: dict[str, dict] = {
            "SA-19281": {
                "appointmentId": "SA-19281",
                "customerId": "CON-1",
                "assetId": "AST-1",
                "resourceId": "SR-1",
                "slaWindowMinutes": 120,
                "caseState": "OPEN",
            },
            # Out-of-warranty appointment (Step 6): fire against this to drive the PAID commerce
            # flow — the asset's warranty is expired, so a part is chargeable (OQ2).
            "SA-OOW": {
                "appointmentId": "SA-OOW",
                "customerId": "CON-1",
                "assetId": "AST-OOW",
                "resourceId": "SR-1",
                "slaWindowMinutes": 120,
                "caseState": "OPEN",
            },
        }
        self._customers: dict[str, dict] = {
            "CON-1": {"name": "Kaleem Ahmed", "phone": "+91-90000-00000"},
        }
        # Asset models match the product catalog (app/data/catalog.json) so the proposer can ground
        # on the asset's real parts. The canonical demo asset is the XYZ-492.
        self._assets: dict[str, dict] = {
            "AST-1": {"model": "Frostline Inverter Split AC XYZ-492", "warranty": "active"},
            "AST-OOW": {"model": "Frostline Inverter Split AC XYZ-492", "warranty": "expired"},
        }
        self._technicians: dict[str, dict] = {
            "SR-1": {"name": "Rahul Kumar", "skills": ["inverter-ac"], "territory": "Noida",
                     "phone": "+91-90000-00042"},  # enables the one-tap "Call technician" (slice 2)
        }

    def _guard(self) -> None:
        if self.down:
            raise RuntimeError("salesforce unavailable")  # Step 7b: → handler fails → DLQ

    def get_appointment(self, appointment_id: str) -> dict | None:
        self._guard()
        appt = self._appointments.get(appointment_id)
        return dict(appt) if appt else None

    def get_customer(self, customer_id: str) -> dict | None:
        self._guard()
        cust = self._customers.get(customer_id)
        return dict(cust) if cust else None

    def get_asset(self, asset_id: str) -> dict | None:
        self._guard()
        asset = self._assets.get(asset_id)
        return dict(asset) if asset else None

    def get_technician(self, resource_id: str) -> dict | None:
        self._guard()
        tech = self._technicians.get(resource_id)
        return dict(tech) if tech else None

    def get_slots(self, appointment_id: str) -> list[dict]:
        """Real-availability offline twin: returns whatever a test seeded on `_slots` (empty by
        default, so the graph uses its canned slots). The real engine lives in RestSalesforce."""
        self._guard()
        return [dict(s) for s in self._slots]

    def reschedule(
        self, appointment_id: str, slot_id: str, slot_label: str | None = None,
        start_time: str | None = None, end_time: str | None = None,
    ) -> dict:
        """Apply the chosen slot (fake). The Toolbox action ran the authority ladder first.
        `slot_label`/`start_time`/`end_time` are ignored here — they only matter to RestSalesforce,
        which books the concrete start/end the real org needs."""
        return {"appointmentId": appointment_id, "slotId": slot_id, "status": "RESCHEDULED"}

    def record_payment(self, receipt: dict, appointment_id: str | None = None) -> dict:
        """Store a captured payment in the in-memory demo org. Idempotent by paymentId — a retried
        capture overwrites the same key (mirrors RestSalesforce's external-id upsert)."""
        self._guard()
        payment_id = receipt.get("paymentId")
        self._payments[payment_id] = {**receipt, "appointmentId": appointment_id}
        return {"paymentId": payment_id, "status": "RECORDED", "recordId": payment_id}


# --- Real org via the Apex REST surface (build step 12) ---------------------------------------

# Slot labels the proposer emits, e.g. "TODAY 15:00-17:00" / "TOMORROW 09:00-11:00". The day word
# + the HH:MM-HH:MM range are the only time info we have, so the reschedule mutation parses them.
_LABEL_RE = re.compile(
    r"(TODAY|TOMORROW)\s+(\d{1,2}):(\d{2})\s*-\s*(\d{1,2}):(\d{2})", re.IGNORECASE
)


def slot_label_to_times(
    label: str, tz_name: str, now: datetime | None = None
) -> tuple[str, str]:
    """Turn a human slot label into (startISO, endISO) in **UTC**, so Salesforce and every other
    system agree on the one instant (OQ2 — no naive/floating datetimes crossing the wire).

    The label is wall-clock in `tz_name` (the business timezone, e.g. Asia/Kolkata). We build a
    timezone-aware local datetime for today/tomorrow, then convert to UTC and format as ISO-8601
    with a `Z` suffix — the canonical form Salesforce's Apex `JSON.deserialize(..., Datetime)`
    accepts unambiguously. Raises ValueError on an unparseable label (fail loud, never mis-time).

    # ponytail: assumes a same-day 2-hour window (slots never cross midnight) and no DST gotchas
    # (India has none); ZoneInfo handles DST correctly for other zones if a slot catalog arrives.
    """
    m = _LABEL_RE.search(label or "")
    if not m:
        raise ValueError(f"cannot parse slot label into times: {label!r}")
    day, sh, sm, eh, em = (
        m.group(1).upper(), int(m.group(2)), int(m.group(3)), int(m.group(4)), int(m.group(5)),
    )
    tz = ZoneInfo(tz_name)
    base = (now.astimezone(tz) if now else datetime.now(tz))
    if day == "TOMORROW":
        base += timedelta(days=1)
    start = base.replace(hour=sh, minute=sm, second=0, microsecond=0)
    end = base.replace(hour=eh, minute=em, second=0, microsecond=0)
    return _to_utc_z(start), _to_utc_z(end)


def _to_utc_z(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_iso(s: str) -> datetime:
    """Parse an ISO-8601 instant tolerant of the forms Salesforce emits: a trailing ``Z`` and a
    numeric offset without a colon (``+0000``). Apex ``JSON.serialize`` of a Datetime gives
    ``2026-10-22T09:00:00.000+0000`` — ``datetime.fromisoformat`` wants ``+00:00``, so normalise."""
    s = s.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    m = re.search(r"([+-]\d{2})(\d{2})$", s)
    if m:
        s = s[: m.start()] + m.group(1) + ":" + m.group(2)
    return datetime.fromisoformat(s)


def slot_time_fields(
    *, start: str | None, label: str | None, tz_name: str, now: datetime | None = None
) -> dict | None:
    """Derive the time fields policy needs from a slot's ISO `start` or its `label` (AI-BEH-01).

    Returns ``{"startMinutes": int, "hour": int}`` where:
      - startMinutes = whole minutes from `now` to the slot start (NEGATIVE = the slot is past);
      - hour         = the slot's start hour (0-23) in the business tz, for the working-hours check.

    Returns ``None`` when neither a parseable `start` nor `label` is available — the caller drops
    that slot rather than offering a time it can't stand behind (also stops a malformed time from
    crashing later at reschedule). A real FSL slot has `start`; a canned/LLM slot has `label`.
    """
    ref = now.astimezone(UTC) if now else datetime.now(UTC)
    try:
        if start:
            dt = _parse_iso(start)
        elif label:
            start_iso, _ = slot_label_to_times(label, tz_name, now)
            dt = _parse_iso(start_iso)
        else:
            return None
    except (ValueError, TypeError):
        return None
    return {
        "startMinutes": round((dt - ref).total_seconds() / 60),
        "hour": dt.astimezone(ZoneInfo(tz_name)).hour,
    }


def format_slot_label(start_iso: str, end_iso: str, tz_name: str) -> str:
    """A real slot's (start, end) ISO instants → a short human label in the business timezone, e.g.
    ``"Wed 22 Oct, 09:00-11:00"``. Display only; the exact instants still travel as ISO for the
    booking. Unlike the canned "TODAY/TOMORROW" labels, real slots span any day, so name the day."""
    tz = ZoneInfo(tz_name)
    s = _parse_iso(start_iso).astimezone(tz)
    e = _parse_iso(end_iso).astimezone(tz)
    return f"{s:%a %d %b}, {s:%H:%M}-{e:%H:%M}"


class RestSalesforce:
    """The real org behind the same Protocol, over the Apex REST class (apps/salesforce-apex/).

    Auth = OAuth client-credentials (server-to-server, no user): one POST returns an access_token +
    the org's instance_url, cached in memory and refetched once on a 401 (OQ4 — token expiry). Reads
    GET `/services/apexrest/fieldflow/<kind>/<id>` and return the SAME shapes as FakeSalesforce (the
    Apex class mirrors them), so the graph and tests don't change. reschedule POSTs concrete UTC
    times derived from the slot label (OQ2). httpx is injectable for offline tests.
    """

    def __init__(
        self, *, login_url: str, client_id: str, client_secret: str, tz_name: str,
        scheduling_policy_id: str = "", operating_hours_id: str = "", slots_max: int = 6,
        timeout: float = 20.0, client: httpx.Client | None = None,
    ) -> None:
        self._login_url = login_url.rstrip("/")
        self._client_id, self._client_secret = client_id, client_secret
        self._tz_name = tz_name
        self._policy_id = scheduling_policy_id
        self._oh_id = operating_hours_id
        self._slots_max = slots_max
        self._timeout = timeout
        self._client = client  # injected in tests; else built lazily
        self._token: str | None = None
        self._instance_url: str | None = None

    def _http(self) -> httpx.Client:
        if self._client is None:
            import httpx

            self._client = httpx.Client(timeout=self._timeout)
        return self._client

    def _authenticate(self) -> None:
        resp = self._http().post(
            f"{self._login_url}/services/oauth2/token",
            data={"grant_type": "client_credentials",
                  "client_id": self._client_id, "client_secret": self._client_secret},
        )
        resp.raise_for_status()
        body = resp.json()
        self._token = body["access_token"]
        self._instance_url = str(body["instance_url"]).rstrip("/")
        log.info("salesforce.authenticated", instance_url=self._instance_url)

    def _call(self, method: str, path: str, json: dict | None = None) -> httpx.Response:
        """One request with the bearer token; on a 401 (expired token) re-auth once and retry."""
        resp = None
        for attempt in (1, 2):
            if self._token is None:
                self._authenticate()
            resp = self._http().request(
                method, f"{self._instance_url}{path}",
                headers={"Authorization": f"Bearer {self._token}"}, json=json,
            )
            if resp.status_code == 401 and attempt == 1:
                log.info("salesforce.token_expired_refetch")
                self._token = None
                continue
            break
        assert resp is not None  # loop always assigns before break
        return resp

    def _get(self, kind: str, id_: str) -> dict | None:
        resp = self._call("GET", f"/services/apexrest/fieldflow/{kind}/{quote(str(id_))}")
        if resp.status_code == 404:  # Apex 404s an unknown id → None, so an action tool can refuse
            return None
        if resp.status_code >= 400:
            log.error("salesforce.read_rejected", kind=kind,
                      status=resp.status_code, body=resp.text)
        resp.raise_for_status()
        return resp.json()

    def get_appointment(self, appointment_id: str) -> dict | None:
        return self._get("appointment", appointment_id)

    def get_customer(self, customer_id: str) -> dict | None:
        return self._get("customer", customer_id)

    def get_asset(self, asset_id: str) -> dict | None:
        return self._get("asset", asset_id)

    def get_technician(self, resource_id: str) -> dict | None:
        return self._get("technician", resource_id)

    def get_slots(self, appointment_id: str) -> list[dict]:
        """Real availability from Field Service's own scheduler via the Apex `/slots` endpoint
        (FSL.AppointmentBookingService.GetSlots). Returns a list of {start, end, grade}; [] when the
        ids aren't configured, the appointment is unknown, or the engine finds nothing — the graph
        then falls back to its canned slots. Fails SOFT (logs, returns []) so a scheduling hiccup
        never dead-ends a recovery."""
        if not (self._policy_id and self._oh_id):
            return []  # not configured → fall back to canned (slotsAuthority="fallback")
        params = urlencode({"policyId": self._policy_id, "operatingHoursId": self._oh_id,
                            "max": str(self._slots_max)})
        resp = self._call(
            "GET", f"/services/apexrest/fieldflow/slots/{quote(str(appointment_id))}?{params}",
        )
        if resp.status_code >= 400:
            log.error("salesforce.slots_rejected", status=resp.status_code, body=resp.text)
            return []  # fail soft → canned fallback
        data = resp.json()
        return data if isinstance(data, list) else []

    def reschedule(
        self, appointment_id: str, slot_id: str, slot_label: str | None = None,
        start_time: str | None = None, end_time: str | None = None,
    ) -> dict:
        """The one mutation: move the appointment to the chosen slot's real times. The authority
        ladder already ran in the Toolbox. A real scheduler slot passes `start_time`/`end_time`
        (concrete ISO instants) directly; a canned slot passes only `slot_label`, which we parse."""
        if start_time and end_time:
            start, end = start_time, end_time
        elif slot_label:
            start, end = slot_label_to_times(slot_label, self._tz_name)
        else:
            raise ValueError(f"reschedule needs start/end or a slot label; slotId={slot_id!r}")
        resp = self._call(
            "POST", "/services/apexrest/fieldflow/reschedule",
            json={"appointmentId": appointment_id, "startTime": start, "endTime": end},
        )
        if resp.status_code >= 400:
            log.error("salesforce.reschedule_rejected", status=resp.status_code, body=resp.text)
        resp.raise_for_status()
        # Keep slotId in the result so `executed` looks the same as the fake's shape to the panel.
        return {"slotId": slot_id, **resp.json()}

    def record_payment(self, receipt: dict, appointment_id: str | None = None) -> dict:
        """POST the captured payment to the Apex `/payment` endpoint, which upserts a
        FieldFlow_Payment__c on Payment_Id__c (idempotent) and links it to the appointment."""
        body = {
            "paymentId": receipt.get("paymentId"),
            "paymentRef": receipt.get("paymentRef"),
            "orderId": receipt.get("orderId"),
            "amountPaise": receipt.get("amountPaise"),
            "currency": receipt.get("currency"),
            "status": receipt.get("status"),
            "appointmentId": appointment_id,
        }
        resp = self._call("POST", "/services/apexrest/fieldflow/payment", json=body)
        if resp.status_code >= 400:
            log.error("salesforce.payment_rejected", status=resp.status_code, body=resp.text)
        resp.raise_for_status()
        return resp.json()


def build_salesforce(settings: Any) -> SalesforceTools:
    """The one swap line: the real Apex REST org when the client-credentials creds are set, else
    FakeSalesforce (the offline default — every test + a keyless boot). Reads can go live the moment
    the creds land; the reschedule mutation additionally needs the Apex class deployed."""
    if not settings.sf_rest_armed:
        return FakeSalesforce()
    log.info("salesforce.live", login_url=settings.sf_login_url)
    return RestSalesforce(
        login_url=settings.sf_login_url, client_id=settings.sf_client_id,
        client_secret=settings.sf_client_secret, tz_name=settings.sf_timezone,
        scheduling_policy_id=settings.sf_scheduling_policy_id,
        operating_hours_id=settings.sf_operating_hours_id, slots_max=settings.sf_slots_max,
    )
