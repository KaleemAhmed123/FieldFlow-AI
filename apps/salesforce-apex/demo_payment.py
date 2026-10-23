#!/usr/bin/env python
"""Demo driver for the SF reschedule + payment write-back — for recording the video.

Exercises the SAME live Apex endpoints the orchestrator's pipeline uses, on one appointment, with a
clean reset between takes. Reuses the SF_* creds from apps/orchestrator/.env (via deploy_sf.py).

Commands (run from the repo root):
    uv run python apps/salesforce-apex/demo_payment.py show SA-0002         # schedule + linked payments
    uv run python apps/salesforce-apex/demo_payment.py reschedule SA-0002   # -> tomorrow 10:00-12:00 IST
    uv run python apps/salesforce-apex/demo_payment.py pay SA-0002          # write a captured payment
    uv run python apps/salesforce-apex/demo_payment.py reset SA-0002        # clear schedule + delete payments

Typical video take: `reset` (clean slate) -> show the appointment empty in the UI -> `reschedule` ->
refresh (Scheduled Start/End now set) -> `pay` -> refresh (FieldFlow Payments related list shows the row).
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timedelta, timezone

from deploy_sf import data_api, data_query, get_token, load_creds

IST = timedelta(hours=5, minutes=30)  # India has no DST, so a fixed offset is exact (no tzdata dep)
APEX = "/services/apexrest/fieldflow"


def apex_post(token: str, instance: str, path: str, body: dict) -> dict:
    """POST to an Apex REST endpoint (reschedule / payment), same as the orchestrator does."""
    req = urllib.request.Request(
        f"{instance}{APEX}{path}", data=json.dumps(body).encode(), method="POST",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310 (our own org URL)
            return json.loads(resp.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        return {"error": e.read().decode(errors="replace")}


def _appt_id(token: str, instance: str, number: str) -> str:
    rows = data_query(token, instance,
                      f"SELECT Id FROM ServiceAppointment WHERE AppointmentNumber = '{number}'")
    if not rows:
        sys.exit(f"appointment {number} not found")
    return rows[0]["Id"]


def show(token: str, instance: str, number: str) -> None:
    rows = data_query(token, instance,
                      "SELECT SchedStartTime, SchedEndTime, Status FROM ServiceAppointment "
                      f"WHERE AppointmentNumber = '{number}'")
    a = rows[0]
    print(f"{number}: status={a['Status']}  start={a['SchedStartTime']}  end={a['SchedEndTime']}")
    pays = data_query(token, instance,
                      "SELECT Name, Payment_Id__c, Amount_Paise__c, Currency_Code__c, Status__c "
                      "FROM FieldFlow_Payment__c WHERE Service_Appointment__r.AppointmentNumber = "
                      f"'{number}'")
    if not pays:
        print("  payments: NONE")
    for p in pays:
        rupees = (p["Amount_Paise__c"] or 0) / 100
        print(f"  payment {p['Name']}: {p['Payment_Id__c']}  "
              f"{p['Currency_Code__c']} {rupees:,.2f}  {p['Status__c']}")


def reschedule(token: str, instance: str, number: str) -> None:
    # Tomorrow 10:00-12:00 IST (what a customer tapping the part-fit slot would pick), -> UTC Z.
    day = (datetime.now(timezone.utc).replace(tzinfo=None) + IST + timedelta(days=1)).date()

    def utc_z(hour: int) -> str:
        ist_local = datetime(day.year, day.month, day.day, hour, 0)
        return (ist_local - IST).strftime("%Y-%m-%dT%H:%M:%SZ")

    out = apex_post(token, instance, "/reschedule",
                    {"appointmentId": number, "startTime": utc_z(10), "endTime": utc_z(12)})
    print(f"reschedule {number} -> 10:00-12:00 IST tomorrow: {out}")


def pay(token: str, instance: str, number: str) -> None:
    # A captured payment shaped exactly like the gateway receipt the pipeline would hand the Apex
    # endpoint. ₹3,700 = price-book CAP-492 (₹3,200) + labour (₹500).
    ids = {"paymentId": "pay_" + uuid.uuid4().hex[:12],
           "paymentRef": "plink_" + uuid.uuid4().hex[:12],
           "orderId": "ord_" + uuid.uuid4().hex[:12]}
    out = apex_post(token, instance, "/payment",
                    {**ids, "amountPaise": 370000, "currency": "INR", "status": "captured",
                     "appointmentId": number})
    print(f"pay {number} (INR 3,700 captured): {out}")


def reset(token: str, instance: str, number: str) -> None:
    sa_id = _appt_id(token, instance, number)
    # Clear the schedule (unschedule) so the UI shows an empty Scheduled Start/End for the next take.
    status, _ = data_api("PATCH", token, instance, f"/sobjects/ServiceAppointment/{sa_id}",
                         {"SchedStartTime": None, "SchedEndTime": None})
    print(f"cleared schedule on {number}: HTTP {status}")
    # Delete the demo payments linked to this appointment.
    pays = data_query(token, instance,
                      f"SELECT Id FROM FieldFlow_Payment__c WHERE Service_Appointment__c = '{sa_id}'")
    for p in pays:
        st, _ = data_api("DELETE", token, instance, f"/sobjects/FieldFlow_Payment__c/{p['Id']}")
        print(f"  deleted payment {p['Id']}: HTTP {st}")
    if not pays:
        print("  no payments to delete")


COMMANDS = {"show": show, "reschedule": reschedule, "pay": pay, "reset": reset}


def main(argv: list[str]) -> None:
    if len(argv) < 2 or argv[0] not in COMMANDS:
        sys.exit(__doc__)
    token, instance = get_token(*load_creds())
    COMMANDS[argv[0]](token, instance, argv[1])


if __name__ == "__main__":
    main(sys.argv[1:])
