#!/usr/bin/env python
"""Seed a minimal Field Service demo chain into your REAL Salesforce org.

Why: so RestSalesforce's live reads (build step 12) return real records, and so you have an
appointment to fire the recovery flow against. It creates the smallest chain the Apex class
(FieldFlowRest.cls) reads: Account -> Contact (customer), Asset (in- and out-of-warranty),
ServiceResource (technician), WorkOrder, ServiceAppointment, AssignedResource.

How it authenticates: the SAME OAuth client-credentials creds the orchestrator uses
(SF_LOGIN_URL / SF_CLIENT_ID / SF_CLIENT_SECRET) — read from apps/orchestrator/.env, or the
environment (env wins). No new creds.

Run (from the repo root):
    uv run --with simple-salesforce python apps/salesforce-apex/seed_demo_data.py

Safe to re-run: each record is matched on a filterable field (the demo Account name, the WorkOrder
subject, the warranty checkbox, the appointment's parent), so a second run updates instead of
duplicating. Fail-loud: the required spine raises on error (so you see exactly what your org
rejected — usually a missing field or permission). The optional bits (technician link) only warn,
because the Apex reads already tolerate them being absent.

Assumptions (match the .cls A1-A4 — adjust here or tell me if your org differs):
  - A1  warranty = the custom checkbox Asset.Warranty_Active__c (create it before running).
  - A2  ServiceAppointment.ParentRecordId -> WorkOrder (carrying ContactId + AssetId).
  - FS  Field Service objects (WorkOrder/ServiceAppointment/ServiceResource/AssignedResource) exist
        and the integration user can create them.

# ponytail: one-off seed, not a migration tool — no schema discovery, no bulk API; a dozen records.
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ENV_PATH = Path(__file__).resolve().parents[1] / "orchestrator" / ".env"
MODEL = "Frostline Inverter Split AC XYZ-492"  # matches app/data/catalog.json + FakeSalesforce


def load_creds() -> tuple[str, str, str]:
    """SF_* from the environment first, then apps/orchestrator/.env. Fail loud if any is missing."""
    import os

    vals = {k: os.environ.get(k, "") for k in ("SF_LOGIN_URL", "SF_CLIENT_ID", "SF_CLIENT_SECRET")}
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, raw = line.partition("=")
            key = key.strip()
            if key in vals and not vals[key]:
                vals[key] = raw.split("#", 1)[0].strip().strip('"').strip("'")
    missing = [k for k, v in vals.items() if not v]
    if missing:
        sys.exit(f"Missing creds: {', '.join(missing)} (set them in {ENV_PATH} or the environment)")
    return vals["SF_LOGIN_URL"].rstrip("/"), vals["SF_CLIENT_ID"], vals["SF_CLIENT_SECRET"]


def get_token(login_url: str, client_id: str, client_secret: str) -> tuple[str, str]:
    """OAuth client-credentials -> (access_token, instance_url). Same flow as RestSalesforce."""
    data = urllib.parse.urlencode(
        {"grant_type": "client_credentials", "client_id": client_id, "client_secret": client_secret}
    ).encode()
    req = urllib.request.Request(f"{login_url}/services/oauth2/token", data=data)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310 (our own org URL)
            body = json.load(resp)
    except urllib.error.HTTPError as e:  # token errors are the usual first wall — show the body
        sys.exit(f"Token request failed ({e.code}): {e.read().decode(errors='replace')}")
    return body["access_token"], body["instance_url"].rstrip("/")


def main() -> None:
    try:
        from simple_salesforce import Salesforce
    except ImportError:
        sys.exit("Run with: uv run --with simple-salesforce python "
                 "apps/salesforce-apex/seed_demo_data.py")

    login_url, client_id, client_secret = load_creds()
    token, instance_url = get_token(login_url, client_id, client_secret)
    sf = Salesforce(instance_url=instance_url, session_id=token)
    print(f"Connected to {instance_url}\n")

    def esc(v: str) -> str:
        return str(v).replace("\\", "\\\\").replace("'", "\\'")

    def upsert(obj: str, where: str, fields: dict) -> str:
        """Create or update one record. `where` is a SOQL filter on FILTERABLE fields (Name,
        Subject, a checkbox, a lookup) to find an existing one — NOT a long-text field like
        Description, which Salesforce refuses to filter on. Makes re-runs idempotent."""
        found = sf.query(f"SELECT Id FROM {obj} WHERE {where} LIMIT 1")
        if found["totalSize"]:
            rid = found["records"][0]["Id"]
            getattr(sf, obj).update(rid, fields)
            print(f"  updated {obj:<20} {rid}")
            return rid
        rid = getattr(sf, obj).create(fields)["id"]
        print(f"  created {obj:<20} {rid}")
        return rid

    # --- required spine (raises on error — this is the data the reads need) -------------------
    print("Seeding...")
    account_id = upsert("Account", "Name = 'FieldFlow Demo Customer'",
                        {"Name": "FieldFlow Demo Customer"})
    contact_id = upsert("Contact", f"LastName = 'Ahmed' AND AccountId = '{account_id}'",
                        {"LastName": "Ahmed", "FirstName": "Kaleem", "AccountId": account_id,
                         "MobilePhone": "+91-90000-00000"})
    asset_where = f"Name = '{esc(MODEL)}' AND AccountId = '{account_id}' AND Warranty_Active__c = "
    asset_fields = {"Name": MODEL, "AccountId": account_id, "ContactId": contact_id}
    asset_id = upsert("Asset", asset_where + "true", {**asset_fields, "Warranty_Active__c": True})
    asset_oow_id = upsert("Asset", asset_where + "false",
                          {**asset_fields, "Warranty_Active__c": False})

    appointments: list[tuple[str, str]] = []
    sa_ids: list[str] = []
    cases = (("in-warranty", asset_id, "in-warranty (free part)"),
             ("out-of-warranty", asset_oow_id, "out-of-warranty (paid part)"))
    for _key, this_asset, label in cases:
        subject = f"FieldFlow demo WO ({label})"
        wo_id = upsert("WorkOrder", f"Subject = '{esc(subject)}'",
                       {"Subject": subject, "ContactId": contact_id,
                        "AssetId": this_asset, "AccountId": account_id})
        sa_id = upsert("ServiceAppointment", f"ParentRecordId = '{wo_id}'",
                       {"ParentRecordId": wo_id, "Status": "Scheduled"})
        number = sf.ServiceAppointment.get(sa_id)["AppointmentNumber"]
        appointments.append((number, label))
        sa_ids.append(sa_id)

    # --- optional technician (warn-only: the Apex getTechnician tolerates it being absent) ----
    # A user can own only ONE active ServiceResource, so reuse an existing one if the org already
    # has it (our demo org's integration user is already a resource); only create when none exists
    # and we can find a user who isn't already a resource.
    try:
        existing = sf.query("SELECT Id, Name FROM ServiceResource "
                            "WHERE IsActive = true ORDER BY CreatedDate LIMIT 1")
        if existing["totalSize"]:
            row = existing["records"][0]
            resource_id = row["Id"]
            print(f"  reusing ServiceResource    {resource_id}  ({row['Name']})")
        else:
            free = sf.query("SELECT Id FROM User WHERE IsActive = true AND Id NOT IN "
                            "(SELECT RelatedRecordId FROM ServiceResource) "
                            "ORDER BY CreatedDate LIMIT 1")
            resource_id = sf.ServiceResource.create(
                {"Name": "Rahul Kumar", "IsActive": True, "ResourceType": "T",
                 "RelatedRecordId": free["records"][0]["Id"]})["id"]
            print(f"  created ServiceResource    {resource_id}")
        for sa_id in sa_ids:
            exists = sf.query(f"SELECT Id FROM AssignedResource WHERE ServiceAppointmentId = "
                              f"'{sa_id}' AND ServiceResourceId = '{resource_id}' LIMIT 1")
            if not exists["totalSize"]:
                sf.AssignedResource.create(
                    {"ServiceAppointmentId": sa_id, "ServiceResourceId": resource_id})
                print(f"  linked  technician -> {sa_id}")
    except Exception as e:  # noqa: BLE001 — optional enrichment, never block the spine
        print(f"\n  ! technician link skipped ({type(e).__name__}): {e}")
        print("    (reads still work; the technician read just returns null — fine for the demo)")

    print("\nDone. Fire the recovery flow against either AppointmentNumber:")
    for number, label in appointments:
        print(f"  {number:<12} {label}")
    print("\nSmoke-test a read first — see the Apex README §5 for the curl.")


if __name__ == "__main__":
    main()
