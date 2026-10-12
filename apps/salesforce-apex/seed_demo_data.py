#!/usr/bin/env python
"""Seed a RICH, realistic Field Service demo into your REAL Salesforce org.

Catalog-driven: for EVERY model in app/data/catalog.json it creates an in-warranty and an
out-of-warranty chain (Account + Contact customer, Asset, WorkOrder, ServiceAppointment, assigned
technician), so the recovery flow can fire real-world cases across all 14 appliance models. The RAG
corpus (14 service manuals) and the e-com (86 parts) already cover these same models — so a fired
case connects end to end: real asset -> real manual (RAG) -> real parts (e-com) -> rich AI options.

How it authenticates: the SAME OAuth client-credentials creds the orchestrator uses
(SF_LOGIN_URL / SF_CLIENT_ID / SF_CLIENT_SECRET) — read from apps/orchestrator/.env or the
environment (env wins). No new creds.

Run (from the repo root):
    uv run --with simple-salesforce python apps/salesforce-apex/seed_demo_data.py
    uv run --with simple-salesforce python apps/salesforce-apex/seed_demo_data.py --clean

Idempotent: every record matches on a filterable field (Account name, WO subject, the warranty
checkbox, the appointment's parent), so a re-run UPDATES instead of duplicating. Fail-loud on the
required spine. `--clean` removes the FieldFlow demo chain (Appointments/WOs/Assets/Contacts/
Accounts tagged for the demo) so you can reset.

Assumptions (match FieldFlowRest.cls A1-A4 — adjust here or tell me if your org differs):
  - A1  warranty = the custom checkbox Asset.Warranty_Active__c (create it before running).
  - A2  ServiceAppointment.ParentRecordId -> WorkOrder (carrying ContactId + AssetId).
  - FS  Field Service objects exist and the integration user can create them.
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
ENV_PATH = REPO / "orchestrator" / ".env"
CATALOG = REPO / "orchestrator" / "app" / "data" / "catalog.json"
TAG = "FFDemo"  # stamped on every demo record so --clean can find them

# A pool of distinct customers (reused across the 28 appointments). First is Kaleem (the live-fire one).
CUSTOMERS = [
    ("Kaleem", "Ahmed", "+91-90000-00001"),
    ("Priya", "Nair", "+91-90000-00002"),
    ("Imran", "Khan", "+91-90000-00003"),
    ("Sneha", "Reddy", "+91-90000-00004"),
    ("Vikram", "Singh", "+91-90000-00005"),
    ("Meera", "Iyer", "+91-90000-00006"),
    ("Arjun", "Mehta", "+91-90000-00007"),
    ("Fatima", "Sheikh", "+91-90000-00008"),
    ("Rohan", "Das", "+91-90000-00009"),
    ("Divya", "Pillai", "+91-90000-00010"),
]
# A pool of technicians (one active ServiceResource per free user). Names only; the recovery flow's
# richness comes from the asset model + reason, and policy doesn't hard-gate on technician skill.
TECHNICIANS = ["Rahul Kumar", "Anjali Verma", "Suresh Patel", "Kavya Rao", "Deepak Joshi", "Neha Gupta"]

# Suggested reason per case for the fire menu, chosen to show every archetype + the commerce path.
# (The reason is fired at demo time via /sim, not stored in Salesforce.)
REASONS_IN = ["part_missing", "technician_delay", "part_missing", "traffic_weather",
              "part_missing", "customer_access_issue", "part_missing"]          # in-warranty -> free part / delay
REASONS_OUT = ["additional_fault_found", "asset_complex", "part_missing", "safety_risk",
               "wrong_part_shipped", "warranty_dispute", "technician_no_show"]  # out-of-warranty -> paid / human
_EXPECT = {
    "part_missing": "part reschedule (free if in-warranty, PAID quote if not) + inventory race",
    "additional_fault_found": "newly-found fault -> chargeable -> Approve & Pay",
    "technician_delay": "simple reschedule, no part", "traffic_weather": "simple reschedule, no part",
    "customer_access_issue": "simple reschedule, no part", "technician_no_show": "simple reschedule",
    "wrong_part_shipped": "re-order the right part", "asset_complex": "low confidence -> HUMAN approval",
    "safety_risk": "forced HUMAN approval (risk-tiered)", "warranty_dispute": "forced HUMAN approval",
}


def load_creds() -> tuple[str, str, str]:
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
    data = urllib.parse.urlencode(
        {"grant_type": "client_credentials", "client_id": client_id, "client_secret": client_secret}
    ).encode()
    req = urllib.request.Request(f"{login_url}/services/oauth2/token", data=data)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310 (our own org URL)
            body = json.load(resp)
    except urllib.error.HTTPError as e:
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

    if "--clean" in sys.argv:
        clean(sf, esc)
        return

    def upsert(obj: str, where: str, fields: dict, create_only: tuple[str, ...] = ()) -> str:
        """Create or update one record. `where` filters on FILTERABLE fields to find an existing one.
        `create_only` drops fields Salesforce refuses to UPDATE (e.g. ServiceAppointment.ParentRecordId)."""
        found = sf.query(f"SELECT Id FROM {obj} WHERE {where} LIMIT 1")
        if found["totalSize"]:
            rid = found["records"][0]["Id"]
            upd = {k: v for k, v in fields.items() if k not in create_only}
            if upd:
                getattr(sf, obj).update(rid, upd)
            return rid
        return getattr(sf, obj).create(fields)["id"]

    models = json.loads(CATALOG.read_text(encoding="utf-8"))["models"]
    print(f"Seeding {len(models)} models x 2 (in/out warranty) = {len(models) * 2} appointments...\n")

    # --- customers (Account + Contact) --------------------------------------------------------
    customer_ids: list[tuple[str, str, str]] = []  # (account_id, contact_id, full_name)
    for first, last, phone in CUSTOMERS:
        acct_name = f"{TAG}: {first} {last}"
        acct = upsert("Account", f"Name = '{esc(acct_name)}'", {"Name": acct_name})
        con = upsert("Contact", f"LastName = '{esc(last)}' AND AccountId = '{acct}'",
                     {"LastName": last, "FirstName": first, "AccountId": acct, "MobilePhone": phone})
        customer_ids.append((acct, con, f"{first} {last}"))
    print(f"  customers: {len(customer_ids)}")

    # --- technicians (one ServiceResource per free user; reuse by name on re-run) --------------
    tech_ids = ensure_technicians(sf, esc)
    print(f"  technicians: {len(tech_ids)}")

    # --- the 28 chains: Asset -> WorkOrder -> ServiceAppointment -> AssignedResource -----------
    rows: list[tuple[str, str, str, str]] = []  # (number, model, warranty, suggested_reason)
    case = 0
    for mi, m in enumerate(models):
        model_name, model_id = m["name"], m["modelId"]
        for wi, (warranty_active, tag) in enumerate(((True, "in-warranty"), (False, "out-of-warranty"))):
            acct_id, con_id, cust = customer_ids[case % len(customer_ids)]
            tech_id = tech_ids[case % len(tech_ids)]
            asset_name = f"{model_name}"
            asset_where = (f"Name = '{esc(asset_name)}' AND AccountId = '{acct_id}' "
                           f"AND Warranty_Active__c = {'true' if warranty_active else 'false'}")
            asset_id = upsert("Asset", asset_where,
                              {"Name": asset_name, "AccountId": acct_id, "ContactId": con_id,
                               "Warranty_Active__c": warranty_active})
            subject = f"{TAG} {model_id} {tag} ({cust})"
            wo_id = upsert("WorkOrder", f"Subject = '{esc(subject)}'",
                           {"Subject": subject, "ContactId": con_id, "AssetId": asset_id,
                            "AccountId": acct_id})
            sa_id = upsert("ServiceAppointment", f"ParentRecordId = '{wo_id}'",
                           {"ParentRecordId": wo_id, "Status": "Scheduled"},
                           create_only=("ParentRecordId",))
            exists = sf.query(f"SELECT Id FROM AssignedResource WHERE ServiceAppointmentId = '{sa_id}' "
                              f"AND ServiceResourceId = '{tech_id}' LIMIT 1")
            if not exists["totalSize"]:
                sf.AssignedResource.create(
                    {"ServiceAppointmentId": sa_id, "ServiceResourceId": tech_id})
            number = sf.ServiceAppointment.get(sa_id)["AppointmentNumber"]
            reason = (REASONS_IN if warranty_active else REASONS_OUT)[mi % len(REASONS_IN)]
            rows.append((number, model_id, tag, reason))
            case += 1
            print(f"  [{case:>2}/{len(models) * 2}] {number:<12} {model_id:<10} {tag:<16} -> {reason}")

    # --- the fire menu ------------------------------------------------------------------------
    print("\n=== FIRE MENU — pick any AppointmentNumber + its reason ===")
    print(f"  {'Appt':<12} {'Model':<10} {'Warranty':<16} {'Reason':<22} Expect")
    for number, model_id, tag, reason in rows:
        print(f"  {number:<12} {model_id:<10} {tag:<16} {reason:<22} {_EXPECT.get(reason, '')}")
    print("\nFire one (real send armed on Render):")
    print('  curl -X POST https://fieldflow-ai-w6bm.onrender.com/sim/appointment-at-risk \\')
    print('    -H "Content-Type: application/json" \\')
    print(f'    -d \'{{"workOrderId":"WO-DEMO","appointmentId":"{rows[0][0]}",'
          f'"reason":"{rows[0][3]}","eventId":"evt-demo"}}\'')


def ensure_technicians(sf, esc) -> list[str]:
    """Make sure the named ServiceResource pool exists (match by Name; create from a free user when
    missing). A user can own only one active ServiceResource, so we never double-assign a user."""
    ids: list[str] = []
    for name in TECHNICIANS:
        found = sf.query(f"SELECT Id FROM ServiceResource WHERE Name = '{esc(name)}' LIMIT 1")
        if found["totalSize"]:
            ids.append(found["records"][0]["Id"])
            continue
        free = sf.query("SELECT Id FROM User WHERE IsActive = true AND Id NOT IN "
                        "(SELECT RelatedRecordId FROM ServiceResource) ORDER BY CreatedDate LIMIT 1")
        if not free["totalSize"]:
            print(f"  ! no free user for technician '{name}' (reusing the pool we have)")
            break
        rid = sf.ServiceResource.create(
            {"Name": name, "IsActive": True, "ResourceType": "T",
             "RelatedRecordId": free["records"][0]["Id"]})["id"]
        ids.append(rid)
    if not ids:  # fall back to any existing resource so appointments can still be assigned
        any_res = sf.query("SELECT Id FROM ServiceResource WHERE IsActive = true LIMIT 1")
        ids = [r["Id"] for r in any_res["records"]]
    return ids


def clean(sf, esc) -> None:
    """Delete the FieldFlow demo chain (tagged records). Order respects dependencies. ServiceResources
    are left (they're tied to users and reusable)."""
    tag = f"{TAG}"
    print(f"Cleaning demo records tagged '{tag}'...")
    # ServiceAppointments + their AssignedResources (via the tagged WorkOrders)
    wos = sf.query(f"SELECT Id FROM WorkOrder WHERE Subject LIKE '{tag}%'")["records"]
    for wo in wos:
        sas = sf.query(f"SELECT Id FROM ServiceAppointment WHERE ParentRecordId = '{wo['Id']}'")["records"]
        for sa in sas:
            ars = sf.query(f"SELECT Id FROM AssignedResource WHERE ServiceAppointmentId = '{sa['Id']}'")["records"]
            for ar in ars:
                sf.AssignedResource.delete(ar["Id"])
            sf.ServiceAppointment.delete(sa["Id"])
        sf.WorkOrder.delete(wo["Id"])
    print(f"  deleted {len(wos)} WorkOrders + their appointments")
    accts = sf.query(f"SELECT Id FROM Account WHERE Name LIKE '{tag}:%'")["records"]
    for acct in accts:
        for asset in sf.query(f"SELECT Id FROM Asset WHERE AccountId = '{acct['Id']}'")["records"]:
            sf.Asset.delete(asset["Id"])
        for con in sf.query(f"SELECT Id FROM Contact WHERE AccountId = '{acct['Id']}'")["records"]:
            sf.Contact.delete(con["Id"])
        sf.Account.delete(acct["Id"])
    print(f"  deleted {len(accts)} Accounts (+ their Assets + Contacts)")
    print("Done. (ServiceResources kept — they're tied to users and reusable.)")


if __name__ == "__main__":
    main()
