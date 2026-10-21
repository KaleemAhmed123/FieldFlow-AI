#!/usr/bin/env python
"""Seed a RICH, CONNECTED, operational Field Service demo into your REAL Salesforce org.

Catalog-driven: for EVERY model in app/data/catalog.json it builds an in-warranty and an
out-of-warranty chain, fully wired so ANY scenario (delay / parts / complex x in/out warranty x
stock) is firable with real data end to end:

  Account+Contact (addressed)  ->  Asset (serial/dates/price/warranty)  ->  WorkOrder (priority,
  address)  ->  ServiceAppointment (territory + schedule + address)  ->  AssignedResource (a
  technician who HAS the asset's skill and is a MEMBER of the appointment's territory).

It also creates the operational backbone the org was missing:
  - Service Territories (Noida / Delhi / Gurgaon) on real Operating Hours, with addresses.
  - Skills (one per catalog requiresSkill) + ServiceResourceSkill (each tech skilled on a cluster so
    every skill is covered by >= 2 techs).
  - ServiceTerritoryMember (each tech is a member of one territory).

Auth: the SAME OAuth client-credentials creds the orchestrator uses (SF_LOGIN_URL / SF_CLIENT_ID /
SF_CLIENT_SECRET, read from apps/orchestrator/.env or the environment).

Run (from the repo root):
    uv run --with simple-salesforce python apps/salesforce-apex/seed_demo_data.py
    uv run --with simple-salesforce python apps/salesforce-apex/seed_demo_data.py --clean

Idempotent: every record matches on a filterable field, so a re-run UPDATES rather than duplicating.
`--clean` removes the FieldFlow demo chain + its territories/members/resource-skills.

Prereqs (match FieldFlowRest.cls A1-A4): Asset.Warranty_Active__c checkbox exists; the integration
user can create Field Service objects (it has Modify All Data). Rich (cosmetic) field writes are
best-effort — a picklist your org restricts is logged once and skipped, the connections still land.
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
ENV_PATH = REPO / "orchestrator" / ".env"
CATALOG = REPO / "orchestrator" / "app" / "data" / "catalog.json"
TAG = "FFDemo"  # stamped on every demo record so --clean can find them

# Territories (name without the TAG prefix is added below) + their address, on real Operating Hours.
TERRITORIES = [
    ("Noida", "Sector 62", "Noida", "Uttar Pradesh", "201301"),
    ("Delhi", "Connaught Place", "New Delhi", "Delhi", "110001"),
    ("Gurgaon", "Cyber City", "Gurugram", "Haryana", "122002"),
]

# Customers reused across the chains. First is Kaleem (the live-fire one). Rich contact + address.
CUSTOMERS = [
    ("Kaleem", "Ahmed", "+91-90000-00001", "A-14 Sector 62", "Noida", "Uttar Pradesh", "201301"),
    ("Priya", "Nair", "+91-90000-00002", "22 MG Road", "New Delhi", "Delhi", "110001"),
    ("Imran", "Khan", "+91-90000-00003", "DLF Phase 3", "Gurugram", "Haryana", "122002"),
    ("Sneha", "Reddy", "+91-90000-00004", "7 Lajpat Nagar", "New Delhi", "Delhi", "110024"),
    ("Vikram", "Singh", "+91-90000-00005", "B-9 Sector 18", "Noida", "Uttar Pradesh", "201301"),
    ("Meera", "Iyer", "+91-90000-00006", "41 Golf Course Rd", "Gurugram", "Haryana", "122002"),
    ("Arjun", "Mehta", "+91-90000-00007", "5 Vasant Kunj", "New Delhi", "Delhi", "110070"),
    ("Fatima", "Sheikh", "+91-90000-00008", "C-3 Sector 15", "Noida", "Uttar Pradesh", "201301"),
    ("Rohan", "Das", "+91-90000-00009", "18 Sushant Lok", "Gurugram", "Haryana", "122009"),
    ("Divya", "Pillai", "+91-90000-00010", "9 Saket", "New Delhi", "Delhi", "110017"),
]
TECHNICIANS = ["Rahul Kumar", "Anjali Verma", "Suresh Patel", "Kavya Rao", "Deepak Joshi",
               "Neha Gupta"]

# Suggested reason per case for the fire menu (fired via /sim at demo time, not stored).
REASONS_IN = ["part_missing", "technician_delay", "part_missing", "traffic_weather",
              "part_missing", "customer_access_issue", "part_missing"]
REASONS_OUT = ["additional_fault_found", "asset_complex", "part_missing", "safety_risk",
               "wrong_part_shipped", "warranty_dispute", "technician_no_show"]
_EXPECT = {
    "part_missing": "part reschedule (free in-warranty, PAID if not) + inventory race",
    "additional_fault_found": "newly-found fault -> chargeable -> Approve & Pay",
    "technician_delay": "simple reschedule, no part",
    "traffic_weather": "simple reschedule, no part",
    "customer_access_issue": "simple reschedule, no part",
    "technician_no_show": "simple reschedule",
    "wrong_part_shipped": "re-order the right part",
    "asset_complex": "low confidence -> HUMAN",
    "safety_risk": "forced HUMAN approval (risk-tiered)",
    "warranty_dispute": "forced HUMAN approval",
}


# --- creds + token (stdlib; env wins over .env) ---------------------------------------------------
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


_WARNED: set[str] = set()


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
        found = sf.query(f"SELECT Id FROM {obj} WHERE {where} LIMIT 1")
        if found["totalSize"]:
            rid = found["records"][0]["Id"]
            upd = {k: v for k, v in fields.items() if k not in create_only}
            if upd:
                getattr(sf, obj).update(rid, upd)
            return rid
        return getattr(sf, obj).create(fields)["id"]

    def enrich(obj: str, rid: str, fields: dict) -> None:
        """Best-effort cosmetic update — a field your org restricts (e.g. a picklist) is logged
        once per object and skipped, so the connections still land."""
        try:
            getattr(sf, obj).update(rid, fields)
        except Exception as exc:  # noqa: BLE001 — rich fields are nice-to-have, never fail the seed
            if obj not in _WARNED:
                _WARNED.add(obj)
                detail = str(exc).split("Response content:")[-1].strip()[:160]
                print(f"  ! {obj} rich fields skipped ({detail})")

    models = json.loads(CATALOG.read_text(encoding="utf-8"))["models"]

    # --- backbone: operating hours, territories, skills, technicians (members + skills) -----------
    oh_id = _operating_hours(sf)
    terr_ids = _territories(sf, esc, oh_id)                     # name -> territory id
    skill_ids = _skills(sf, esc, models)                        # skill label -> skill id
    tech_ids = _technicians(sf, esc)                            # name -> resource id
    tech_terr, tech_skills = _assign_members_and_skills(sf, esc, tech_ids, terr_ids, skill_ids,
                                                        models)
    print(f"  backbone: {len(terr_ids)} territories, {len(skill_ids)} skills, "
          f"{len(tech_ids)} technicians wired\n")

    # --- customers (Account + Contact), addressed ------------------------------------------------
    customer_ids: list[tuple[str, str, str]] = []
    for first, last, phone, street, city, state, pin in CUSTOMERS:
        acct_name = f"{TAG}: {first} {last}"
        acct = upsert("Account", f"Name = '{esc(acct_name)}'", {"Name": acct_name})
        enrich("Account", acct, {"Phone": phone, "BillingStreet": street, "BillingCity": city,
                                 "BillingState": state, "BillingPostalCode": pin,
                                 "BillingCountry": "India",
                                 "Description": f"{TAG} residential service customer"})
        con = upsert(
            "Contact", f"LastName = '{esc(last)}' AND AccountId = '{acct}'",
            {"LastName": last, "FirstName": first, "AccountId": acct, "MobilePhone": phone})
        enrich("Contact", con, {
            "Email": f"{first.lower()}.{last.lower()}@example.com", "Phone": phone,
            "MailingStreet": street, "MailingCity": city, "MailingState": state,
            "MailingPostalCode": pin, "MailingCountry": "India", "Title": "Home owner"})
        customer_ids.append((acct, con, f"{first} {last}"))
    print(f"  customers: {len(customer_ids)}")

    # --- the chains ------------------------------------------------------------------------------
    rows: list[tuple[str, str, str, str, str]] = []  # (number, model, warranty, reason, tech)
    case = 0
    skill_round: dict[str, int] = {}
    for mi, m in enumerate(models):
        model_name, model_id = m["name"], m["modelId"]
        skill = m.get("requiresSkill") or "general"
        specs = ", ".join(f"{k}={v}" for k, v in (m.get("specs") or {}).items())
        for warranty_active, tag in ((True, "in-warranty"), (False, "out-of-warranty")):
            acct_id, con_id, cust = customer_ids[case % len(customer_ids)]
            # pick a technician who HAS this asset's skill; the appt takes that tech's territory
            candidates = ([t for t in TECHNICIANS if skill in tech_skills.get(t, set())]
                          or TECHNICIANS)
            ti = skill_round.get(skill, 0)
            skill_round[skill] = ti + 1
            tech_name = candidates[ti % len(candidates)]
            tech_id = tech_ids[tech_name]
            terr_name = tech_terr[tech_name]
            terr_id = terr_ids[terr_name]

            asset_where = (f"Name = '{esc(model_name)}' AND AccountId = '{acct_id}' "
                           f"AND Warranty_Active__c = {'true' if warranty_active else 'false'}")
            asset_id = upsert("Asset", asset_where,
                              {"Name": model_name, "AccountId": acct_id, "ContactId": con_id,
                               "Warranty_Active__c": warranty_active})
            install = date.today() - timedelta(days=400 if warranty_active else 1500)
            enrich("Asset", asset_id, {
                "SerialNumber": f"{model_id}-{case:04d}", "Status": "Installed", "Quantity": 1,
                "InstallDate": install.isoformat(), "PurchaseDate": install.isoformat(),
                "Price": 34999,
                "Description": f"{m.get('brand', '')} {m.get('category', '')} — {specs}"})

            subject = f"{TAG} {model_id} {tag} ({cust})"
            wo_id = upsert("WorkOrder", f"Subject = '{esc(subject)}'",
                           {"Subject": subject, "ContactId": con_id, "AssetId": asset_id,
                            "AccountId": acct_id})
            enrich("WorkOrder", wo_id, {
                "Description": f"Service recovery for {model_name} ({tag}).",
                "Priority": "High" if not warranty_active else "Medium",
                "ServiceTerritoryId": terr_id})

            sa_id = upsert("ServiceAppointment", f"ParentRecordId = '{wo_id}'",
                           {"ParentRecordId": wo_id}, create_only=("ParentRecordId",))
            start = datetime.now(UTC) + timedelta(days=1, hours=3 * case)
            _fmt = "%Y-%m-%dT%H:%M:%S.000+0000"
            # Territory + schedule first (FS needs them before a resource can be assigned).
            sf.ServiceAppointment.update(sa_id, {
                "ServiceTerritoryId": terr_id,
                "SchedStartTime": start.strftime(_fmt),
                "SchedEndTime": (start + timedelta(hours=2)).strftime(_fmt),
            })
            # Arrival window the Field Service scheduler (GetSlots) searches inside. Wide + rolling
            # (now → +90 days) so real bookable slots stay findable for months without re-seeding
            # (availability-slots.md); SchedStart/End above stay the current at-risk booking.
            window_start = datetime.now(UTC)
            enrich("ServiceAppointment", sa_id, {
                "Subject": f"{model_id} service — {cust}",
                "Description": f"{model_name} at risk; recover via FieldFlow.",
                "Duration": 2, "DurationType": "Hours",
                "EarliestStartTime": window_start.strftime(_fmt),
                "DueDate": (window_start + timedelta(days=90)).strftime(_fmt)})
            _assign_resource(sf, sa_id, tech_id, warn=(case == 0))

            number = sf.ServiceAppointment.get(sa_id)["AppointmentNumber"]
            reason = (REASONS_IN if warranty_active else REASONS_OUT)[mi % len(REASONS_IN)]
            rows.append((number, model_id, tag, reason, tech_name))
            case += 1
            print(f"  [{case:>2}/{len(models) * 2}] {number:<10} {model_id:<10} {tag:<16} "
                  f"{terr_name:<8} {tech_name:<14} -> {reason}")

    _fire_menu(rows)


# --- backbone builders ----------------------------------------------------------------------------
def _operating_hours(sf) -> str:
    """Reuse an existing Operating Hours (every FS org has one); create a basic one if not."""
    rows = sf.query("SELECT Id, Name FROM OperatingHours ORDER BY CreatedDate LIMIT 1")["records"]
    if rows:
        return rows[0]["Id"]
    return sf.OperatingHours.create({"Name": f"{TAG} Hours", "TimeZone": "Asia/Kolkata"})["id"]


def _territories(sf, esc, oh_id: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for name, street, city, state, pin in TERRITORIES:
        full = f"{TAG} {name}"
        found = sf.query(f"SELECT Id FROM ServiceTerritory WHERE Name = '{esc(full)}' LIMIT 1")
        if found["totalSize"]:
            out[name] = found["records"][0]["Id"]
            continue
        out[name] = sf.ServiceTerritory.create({
            "Name": full, "OperatingHoursId": oh_id, "IsActive": True,
            "Street": street, "City": city, "State": state, "PostalCode": pin, "Country": "India",
        })["id"]
    return out


def _skills(sf, esc, models) -> dict[str, str]:
    """A Skill per distinct catalog requiresSkill (model- and part-level)."""
    labels = {m.get("requiresSkill") for m in models if m.get("requiresSkill")}
    labels |= {p.get("requiresSkill") for m in models for p in m.get("parts", [])
               if p.get("requiresSkill")}
    out: dict[str, str] = {}
    for label in sorted(labels):
        found = sf.query(f"SELECT Id FROM Skill WHERE MasterLabel = '{esc(label)}' LIMIT 1")
        if found["totalSize"]:
            out[label] = found["records"][0]["Id"]
            continue
        dev = label.replace("-", "_").replace(" ", "_")
        out[label] = sf.Skill.create({"MasterLabel": label, "DeveloperName": dev})["id"]
    return out


def _technicians(sf, esc) -> dict[str, str]:
    """Named ServiceResource pool (match by Name; create from a free user when missing)."""
    out: dict[str, str] = {}
    for name in TECHNICIANS:
        found = sf.query(f"SELECT Id FROM ServiceResource WHERE Name = '{esc(name)}' LIMIT 1")
        if found["totalSize"]:
            out[name] = found["records"][0]["Id"]
            continue
        free = sf.query(
            "SELECT Id FROM User WHERE IsActive = true AND Id NOT IN "
            "(SELECT RelatedRecordId FROM ServiceResource) ORDER BY CreatedDate LIMIT 1")
        if not free["totalSize"]:
            print(f"  ! no free user for technician '{name}' — reusing the pool we have")
            continue
        out[name] = sf.ServiceResource.create(
            {"Name": name, "IsActive": True, "ResourceType": "T",
             "RelatedRecordId": free["records"][0]["Id"]})["id"]
    if not out:  # fall back to any resource so appointments can still be assigned
        q = sf.query("SELECT Id, Name FROM ServiceResource WHERE IsActive = true LIMIT 6")
        for r in q["records"]:
            out[r["Name"]] = r["Id"]
    return out


def _assign_members_and_skills(sf, esc, tech_ids, terr_ids, skill_ids, models):
    """Put each tech in one territory (member) and give them a skill cluster so every skill is
    covered by >= 2 techs. Returns (tech->territory name, tech->set(skill labels))."""
    techs = list(tech_ids.keys())
    terr_names = list(terr_ids.keys())
    skills = sorted(skill_ids.keys())
    tech_terr = {t: terr_names[i % len(terr_names)] for i, t in enumerate(techs)}
    tech_skills: dict[str, set[str]] = {t: set() for t in techs}
    for i, skill in enumerate(skills):  # each skill -> 2 techs (round-robin), so coverage >= 2
        for t in (techs[i % len(techs)], techs[(i + 1) % len(techs)]):
            tech_skills[t].add(skill)

    today = date.today().isoformat()
    for t in techs:
        # territory membership (idempotent)
        terr_id = terr_ids[tech_terr[t]]
        exists = sf.query(f"SELECT Id FROM ServiceTerritoryMember WHERE ServiceResourceId = "
                          f"'{tech_ids[t]}' AND ServiceTerritoryId = '{terr_id}' LIMIT 1")
        if not exists["totalSize"]:
            try:
                sf.ServiceTerritoryMember.create({
                    "ServiceResourceId": tech_ids[t], "ServiceTerritoryId": terr_id,
                    "EffectiveStartDate": f"{today}T00:00:00.000+0000", "TerritoryType": "P"})
            except Exception as exc:  # noqa: BLE001
                if "member" not in _WARNED:
                    _WARNED.add("member")
                    print(f"  ! territory member skipped ({str(exc)[-140:]})")
        # resource skills (idempotent)
        for skill in tech_skills[t]:
            sid = skill_ids[skill]
            has = sf.query(f"SELECT Id FROM ServiceResourceSkill WHERE ServiceResourceId = "
                           f"'{tech_ids[t]}' AND SkillId = '{sid}' LIMIT 1")
            if not has["totalSize"]:
                try:
                    sf.ServiceResourceSkill.create({
                        "ServiceResourceId": tech_ids[t], "SkillId": sid, "SkillLevel": 7,
                        "EffectiveStartDate": f"{today}T00:00:00.000+0000"})
                except Exception as exc:  # noqa: BLE001
                    if "skill" not in _WARNED:
                        _WARNED.add("skill")
                        print(f"  ! resource skill skipped ({str(exc)[-140:]})")
    return tech_terr, tech_skills


def _assign_resource(sf, sa_id: str, tech_id: str, *, warn: bool) -> None:
    exists = sf.query(f"SELECT Id FROM AssignedResource WHERE ServiceAppointmentId = '{sa_id}' "
                      f"AND ServiceResourceId = '{tech_id}' LIMIT 1")
    if exists["totalSize"]:
        return
    try:
        sf.AssignedResource.create({"ServiceAppointmentId": sa_id, "ServiceResourceId": tech_id})
    except Exception as exc:  # noqa: BLE001 — FS scheduling config may still block it on some orgs
        if warn:
            detail = str(exc).split("Response content:")[-1].strip()[:160]
            print(f"  ! technician not assigned (FS config): {detail}")


def _fire_menu(rows) -> None:
    print("\n=== FIRE MENU — pick any AppointmentNumber + its reason ===")
    print(f"  {'Appt':<10} {'Model':<10} {'Warranty':<16} {'Tech':<14} {'Reason':<22} Expect")
    for number, model_id, tag, reason, tech in rows:
        print(f"  {number:<10} {model_id:<10} {tag:<16} {tech:<14} {reason:<22} "
              f"{_EXPECT.get(reason, '')}")
    print("\nFire one (real send armed on Render):")
    print('  curl -X POST https://fieldflow-ai-w6bm.onrender.com/sim/appointment-at-risk \\')
    print('    -H "Content-Type: application/json" \\')
    print(f'    -d \'{{"workOrderId":"WO-DEMO","appointmentId":"{rows[0][0]}",'
          f'"reason":"{rows[0][3]}","eventId":"evt-demo"}}\'')


def clean(sf, esc) -> None:
    """Delete the FieldFlow demo chain + its territories / members. ServiceResources + Skills stay —
    they're reusable."""
    print(f"Cleaning demo records tagged '{TAG}'...")

    def ids(soql: str) -> list[dict]:
        return sf.query(soql)["records"]

    wos = ids(f"SELECT Id FROM WorkOrder WHERE Subject LIKE '{TAG}%'")
    for wo in wos:
        for sa in ids(f"SELECT Id FROM ServiceAppointment WHERE ParentRecordId = '{wo['Id']}'"):
            for ar in ids(f"SELECT Id FROM AssignedResource "
                          f"WHERE ServiceAppointmentId = '{sa['Id']}'"):
                sf.AssignedResource.delete(ar["Id"])
            sf.ServiceAppointment.delete(sa["Id"])
        sf.WorkOrder.delete(wo["Id"])
    print(f"  deleted {len(wos)} WorkOrders + their appointments")
    accts = ids(f"SELECT Id FROM Account WHERE Name LIKE '{TAG}:%'")
    for acct in accts:
        for asset in ids(f"SELECT Id FROM Asset WHERE AccountId = '{acct['Id']}'"):
            sf.Asset.delete(asset["Id"])
        for con in ids(f"SELECT Id FROM Contact WHERE AccountId = '{acct['Id']}'"):
            sf.Contact.delete(con["Id"])
        sf.Account.delete(acct["Id"])
    print(f"  deleted {len(accts)} Accounts (+ Assets + Contacts)")
    terrs = ids(f"SELECT Id FROM ServiceTerritory WHERE Name LIKE '{TAG} %'")
    for terr in terrs:
        for mem in ids(f"SELECT Id FROM ServiceTerritoryMember "
                       f"WHERE ServiceTerritoryId = '{terr['Id']}'"):
            sf.ServiceTerritoryMember.delete(mem["Id"])
        sf.ServiceTerritory.delete(terr["Id"])
    print(f"  deleted {len(terrs)} territories (+ members)")
    print("Done. (ServiceResources + Skills kept — reusable.)")


if __name__ == "__main__":
    main()
