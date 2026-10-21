#!/usr/bin/env python
"""Deploy FieldFlow's Salesforce code + fields with the Tooling API — no `sf` CLI, no new deps.

Why this exists: we iterate on Apex a lot, and clicking paste-into-Dev-Console every time is slow
and un-repeatable. This script pushes Apex classes/triggers and the at-risk custom fields to the
org using the SAME OAuth client-credentials creds the orchestrator already uses (SF_LOGIN_URL /
SF_CLIENT_ID / SF_CLIENT_SECRET, read from apps/orchestrator/.env or the environment).

What "Tooling API" means: Salesforce's REST API for *developer* objects (Apex, triggers, fields). It
compiles + saves in one call, so it's perfect for scripting code. (Declarative metadata that Tooling
can't touch — e.g. a Named Credential — is a 2-min point-and-click; see the step-3 instructions.)

How it deploys each kind:
  - A NEW class/trigger  -> POST /tooling/sobjects/ApexClass|ApexTrigger  (compiles on save).
  - An EXISTING one      -> the MetadataContainer flow: make a container, add a *Member* with the
                            new Body, submit a ContainerAsyncRequest, poll until it compiles. (You
                            can't just overwrite the Body on an existing class — this is the way.)
  - A custom field       -> POST /tooling/sobjects/CustomField  with {FullName, Metadata}.

Usage (from the repo root):
    # deploy the 3 at-risk fields FIRST (the trigger won't compile until they exist):
    uv run python apps/salesforce-apex/deploy_sf.py --fields
    # create the FieldFlow_Payment__c object + its fields (FieldFlowRest won't compile without them):
    uv run python apps/salesforce-apex/deploy_sf.py --payment
    # then the Apex, in dependency order (class before the trigger/test that reference it):
    uv run python apps/salesforce-apex/deploy_sf.py \
        apps/salesforce-apex/FieldFlowAtRisk.cls \
        apps/salesforce-apex/ServiceAppointmentAtRisk.trigger \
        apps/salesforce-apex/FieldFlowAtRiskTest.cls
    # prove the offline parsing logic with no org:
    uv run python apps/salesforce-apex/deploy_sf.py --self-check
"""

from __future__ import annotations

import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
ENV_PATH = REPO / "orchestrator" / ".env"
API = "v61.0"
META_API = "61.0"  # Metadata API SOAP version (object creation; Tooling can't insert a CustomObject)

# The 10 contract reasons (packages/contract Reason Literal) — the picklist the SF trigger carries.
REASONS = [
    "technician_delay", "traffic_weather", "technician_no_show", "customer_access_issue",
    "part_missing", "wrong_part_shipped", "additional_fault_found",
    "asset_complex", "safety_risk", "warranty_dispute",
]

# The at-risk fields on ServiceAppointment the trigger reads. Checkbox = the explicit "fire it";
# reason picks the archetype; delay feeds the delay scenarios.
FIELDS: list[tuple[str, dict]] = [
    ("ServiceAppointment.At_Risk__c",
     {"label": "At Risk", "type": "Checkbox", "defaultValue": "false"}),
    ("ServiceAppointment.Delay_Minutes__c",
     {"label": "Delay Minutes", "type": "Number", "precision": 18, "scale": 0}),
    ("ServiceAppointment.At_Risk_Reason__c",
     {"label": "At Risk Reason", "type": "Picklist",
      "valueSet": {"valueSetDefinition": {"sorted": False,
                   "value": [{"fullName": r, "default": False, "label": r} for r in REASONS]}}}),
]

# The custom object FieldFlowRest.recordPayment upserts into — one row per captured payment, linked
# to the ServiceAppointment it paid for. The name is an AutoNumber (we key on Payment_Id__c, not the
# Name). sharingModel ReadWrite so the integration user can write without sharing-rule setup.
PAYMENT_OBJECT = ("FieldFlow_Payment__c", {
    "label": "FieldFlow Payment",
    "pluralLabel": "FieldFlow Payments",
    "nameField": {"type": "AutoNumber", "label": "Payment Name", "displayFormat": "PAY-{00000}"},
    "deploymentStatus": "Deployed",
    "sharingModel": "ReadWrite",
})

# Fields on FieldFlow_Payment__c. Payment_Id__c is the external-id/unique upsert key (the Razorpay
# payment id → one row, idempotent on a retried capture). The lookup ties the payment to its visit.
PAYMENT_FIELDS: list[tuple[str, dict]] = [
    ("FieldFlow_Payment__c.Payment_Id__c",
     {"label": "Payment Id", "type": "Text", "length": 64,
      "externalId": True, "unique": True}),
    ("FieldFlow_Payment__c.Payment_Ref__c",
     {"label": "Payment Ref", "type": "Text", "length": 64}),
    ("FieldFlow_Payment__c.Order_Id__c",
     {"label": "Order Id", "type": "Text", "length": 64}),
    ("FieldFlow_Payment__c.Amount_Paise__c",
     {"label": "Amount (paise)", "type": "Number", "precision": 18, "scale": 0}),
    ("FieldFlow_Payment__c.Currency_Code__c",
     {"label": "Currency", "type": "Text", "length": 8}),
    ("FieldFlow_Payment__c.Status__c",
     {"label": "Status", "type": "Text", "length": 32}),
    ("FieldFlow_Payment__c.Service_Appointment__c",
     {"label": "Service Appointment", "type": "Lookup", "referenceTo": "ServiceAppointment",
      "relationshipLabel": "FieldFlow Payments", "relationshipName": "FieldFlow_Payments",
      "deleteConstraint": "SetNull"}),
]


# --- creds + token (same pattern as seed_demo_data.py — stdlib, env wins over .env) ---------------
def load_creds() -> tuple[str, str, str]:
    import os

    vals = {k: os.environ.get(k, "") for k in ("SF_LOGIN_URL", "SF_CLIENT_ID", "SF_CLIENT_SECRET")}
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, raw = line.partition("=")
            if key.strip() in vals and not vals[key.strip()]:
                vals[key.strip()] = raw.split("#", 1)[0].strip().strip('"').strip("'")
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
            return (lambda b: (b["access_token"], b["instance_url"].rstrip("/")))(json.load(resp))
    except urllib.error.HTTPError as e:
        sys.exit(f"Token request failed ({e.code}): {e.read().decode(errors='replace')}")


# --- Tooling API helpers --------------------------------------------------------------------------
def api(method: str, token: str, instance: str, path: str,
        body: dict | None = None) -> tuple[int, dict]:
    url = f"{instance}/services/data/{API}/tooling{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310 (our own org URL)
            raw = resp.read().decode()
            return resp.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as e:
        raw = e.read().decode(errors="replace")
        try:
            return e.code, json.loads(raw)
        except json.JSONDecodeError:
            return e.code, {"raw": raw}


def query(token: str, instance: str, soql: str) -> list[dict]:
    status, body = api("GET", token, instance, f"/query/?q={urllib.parse.quote(soql)}")
    return body.get("records", []) if status == 200 else []


def data_api(method: str, token: str, instance: str, path: str,
             body: dict | None = None) -> tuple[int, dict]:
    """Same as api() but against the regular Data API (no /tooling) — PermissionSet / FieldPermissions
    / ObjectPermissions live here, not in Tooling."""
    url = f"{instance}/services/data/{API}{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310 (our own org URL)
            raw = resp.read().decode()
            return resp.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as e:
        raw = e.read().decode(errors="replace")
        try:
            return e.code, json.loads(raw)
        except json.JSONDecodeError:
            return e.code, {"raw": raw}


def data_query(token: str, instance: str, soql: str) -> list[dict]:
    status, body = data_api("GET", token, instance, f"/query/?q={urllib.parse.quote(soql)}")
    return body.get("records", []) if status == 200 else []


def fail(ctx: str, res: dict) -> None:
    sys.exit(f"  FAILED {ctx}: {json.dumps(res)[:1000]}")


# --- pure parsing (offline-testable) --------------------------------------------------------------
def parse_apex_text(suffix: str, body: str) -> tuple[str, str, str | None]:
    """(tooling_type, name, sobject|None) from a .cls/.trigger body. Triggers carry the SObject.

    The class name is matched only on a REAL declaration — the name followed by `{` (after an
    optional `extends`/`implements` clause). Without that anchor the old `class\\s+(\\w+)` matched
    prose in a doc comment ('this class is the foundation' → name 'is'), so the deploy never found
    the existing class and always took the create path."""
    if suffix == ".trigger":
        m = re.search(r"\btrigger\s+(\w+)\s+on\s+(\w+)", body)
        if not m:
            raise ValueError("can't find 'trigger <Name> on <SObject>' header")
        return "ApexTrigger", m.group(1), m.group(2)
    m = re.search(
        r"\bclass\s+(\w+)\b(?:\s+(?:extends|implements)\s+[\w\s,.<>]+?)?\s*\{", body)
    if not m:
        raise ValueError("can't find 'class <Name> {' declaration")
    return "ApexClass", m.group(1), None


# --- deploy actions -------------------------------------------------------------------------------
def deploy_apex(token: str, instance: str, path: Path) -> None:
    body = path.read_text(encoding="utf-8")
    kind, name, sobject = parse_apex_text(path.suffix, body)
    existing = query(token, instance, f"SELECT Id FROM {kind} WHERE Name = '{name}'")
    if not existing:
        payload: dict = {"Name": name, "Body": body}
        if kind == "ApexTrigger":
            payload["TableEnumOrId"] = sobject
        status, res = api("POST", token, instance, f"/sobjects/{kind}", payload)
        if status not in (200, 201):
            fail(f"create {kind} {name}", res)
        print(f"  created {kind} {name}")
        return
    _update_via_container(token, instance, kind, existing[0]["Id"], name, body)


def _update_via_container(token: str, instance: str, kind: str, entity_id: str,
                          name: str, body: str) -> None:
    status, cont = api("POST", token, instance, "/sobjects/MetadataContainer",
                       {"Name": f"FF{int(time.time())}"})
    if status not in (200, 201):
        fail(f"container for {name}", cont)
    cid = cont["id"]
    member = "ApexTriggerMember" if kind == "ApexTrigger" else "ApexClassMember"
    status, res = api("POST", token, instance, f"/sobjects/{member}",
                      {"MetadataContainerId": cid, "ContentEntityId": entity_id, "Body": body})
    if status not in (200, 201):
        fail(f"member for {name}", res)
    status, req = api("POST", token, instance, "/sobjects/ContainerAsyncRequest",
                      {"IsCheckOnly": False, "MetadataContainerId": cid})
    if status not in (200, 201):
        fail(f"compile request for {name}", req)
    arid = req["id"]
    for _ in range(60):
        time.sleep(1)
        _, ar = api("GET", token, instance, f"/sobjects/ContainerAsyncRequest/{arid}")
        state = ar.get("State")
        if state not in ("Queued", "InProgress"):
            if state == "Completed":
                print(f"  updated {kind} {name}")
            else:
                fail(f"compile {name} ({state})", ar.get("DeployDetails", ar))
            return
    sys.exit(f"  timed out waiting for {name} to compile")


def deploy_fields(token: str, instance: str,
                  fields: list[tuple[str, dict]] = FIELDS) -> None:
    for full_name, meta in fields:
        status, res = api("POST", token, instance, "/sobjects/CustomField",
                          {"FullName": full_name, "Metadata": meta})
        if status in (200, 201):
            print(f"  created field {full_name}")
        elif "duplicate" in json.dumps(res).lower() or "already" in json.dumps(res).lower():
            print(f"  field {full_name} already exists — ok")
        else:
            fail(f"field {full_name}", res)


def metadata_create_object(token: str, instance: str) -> None:
    """Create the custom object via the Metadata API (SOAP createMetadata) — the Tooling API can't
    INSERT a CustomObject (FullName isn't a column there), but the Metadata API does it in one
    synchronous call. The client-credentials access_token doubles as the SOAP sessionId. Idempotent:
    a 'duplicate/already exists' result is logged and skipped."""
    name, m = PAYMENT_OBJECT
    nf = m["nameField"]
    inner = (
        f'<met:metadata xsi:type="met:CustomObject">'
        f'<met:fullName>{name}</met:fullName>'
        f'<met:label>{m["label"]}</met:label>'
        f'<met:pluralLabel>{m["pluralLabel"]}</met:pluralLabel>'
        f'<met:nameField><met:type>{nf["type"]}</met:type><met:label>{nf["label"]}</met:label>'
        f'<met:displayFormat>{nf["displayFormat"]}</met:displayFormat></met:nameField>'
        f'<met:deploymentStatus>{m["deploymentStatus"]}</met:deploymentStatus>'
        f'<met:sharingModel>{m["sharingModel"]}</met:sharingModel>'
        f'</met:metadata>'
    )
    envelope = (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<env:Envelope xmlns:env="http://schemas.xmlsoap.org/soap/envelope/" '
        'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
        'xmlns:met="http://soap.sforce.com/2006/04/metadata">'
        f'<env:Header><met:SessionHeader><met:sessionId>{token}</met:sessionId>'
        '</met:SessionHeader></env:Header>'
        f'<env:Body><met:createMetadata>{inner}</met:createMetadata></env:Body>'
        '</env:Envelope>'
    )
    req = urllib.request.Request(
        f"{instance}/services/Soap/m/{META_API}", data=envelope.encode(),
        headers={"Content-Type": "text/xml; charset=UTF-8", "SOAPAction": "createMetadata"},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310 (our own org URL)
            body = resp.read().decode()
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
    low = body.lower()
    if "<success>true</success>" in body:
        print(f"  created object {name}")
    elif "duplicate" in low or "already" in low:
        print(f"  object {name} already exists — ok")
    else:
        fail(f"object {name}", {"raw": body[:1000]})


def deploy_payment(token: str, instance: str) -> None:
    """Create the FieldFlow_Payment__c object (if absent), then its fields. The object must exist
    before its fields; both are idempotent (an 'already exists' is logged and skipped)."""
    metadata_create_object(token, instance)
    deploy_fields(token, instance, PAYMENT_FIELDS)


PERM_SET_NAME = "FieldFlow_Payment_Access"  # dedicated set — see grant_payment_perms


def grant_payment_perms(token: str, instance: str) -> None:
    """Grant the integration user object + field access on FieldFlow_Payment__c. A brand-new custom
    object/field is invisible to the running user until it's granted ('field ... is inaccessible' /
    'No such column'), so the Apex write 500s without this.

    We use a DEDICATED permission set (not the user's profile): the integration user's profile has
    'Modify All Data', and Salesforce refuses ObjectPermissions on a MAD profile ('Cannot insert a
    record if parent permission set has Modify All Data'). A fresh permission set has no such
    conflict and is the clean, additive, reproducible way to carry this access. Idempotent — the set,
    its permission rows, and the assignment are all find-or-create / skip-on-duplicate."""
    me = _current_user_id(token, instance)
    obj = PAYMENT_OBJECT[0]
    rows = data_query(token, instance,
                      f"SELECT Id FROM PermissionSet WHERE Name = '{PERM_SET_NAME}'")
    if rows:
        ps = rows[0]["Id"]
        print(f"  permission set {PERM_SET_NAME} exists — ok")
    else:
        status, res = data_api("POST", token, instance, "/sobjects/PermissionSet",
                               {"Name": PERM_SET_NAME, "Label": "FieldFlow Payment Access"})
        if status not in (200, 201):
            fail(f"create permission set {PERM_SET_NAME}", res)
        ps = res["id"]
        print(f"  created permission set {PERM_SET_NAME}")
    _grant(token, instance, "ObjectPermissions", {
        "ParentId": ps, "SobjectType": obj,
        "PermissionsRead": True, "PermissionsCreate": True, "PermissionsEdit": True})
    for full_name, _ in PAYMENT_FIELDS:
        _grant(token, instance, "FieldPermissions", {
            "ParentId": ps, "SobjectType": obj, "Field": full_name,
            "PermissionsRead": True, "PermissionsEdit": True})
    status, res = data_api("POST", token, instance, "/sobjects/PermissionSetAssignment",
                           {"AssigneeId": me, "PermissionSetId": ps})
    if status in (200, 201):
        print(f"  assigned {PERM_SET_NAME} to the integration user")
    elif "duplicate" in json.dumps(res).lower():
        print(f"  {PERM_SET_NAME} already assigned — ok")
    else:
        fail(f"assign {PERM_SET_NAME}", res)


def _current_user_id(token: str, instance: str) -> str:
    req = urllib.request.Request(f"{instance}/services/oauth2/userinfo",
                                 headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310 (our own org URL)
        return json.load(resp)["user_id"]


def _grant(token: str, instance: str, kind: str, body: dict) -> None:
    status, res = data_api("POST", token, instance, f"/sobjects/{kind}", body)
    label = body.get("Field") or body.get("SobjectType")
    if status in (200, 201):
        print(f"  granted {kind} {label}")
    elif "duplicate" in json.dumps(res).lower():
        print(f"  {kind} {label} already granted — ok")
    else:
        fail(f"{kind} {label}", res)


def self_check() -> None:
    assert parse_apex_text(".trigger",
        "trigger ServiceAppointmentAtRisk on ServiceAppointment (after insert, after update) {}"
    ) == ("ApexTrigger", "ServiceAppointmentAtRisk", "ServiceAppointment")
    assert parse_apex_text(".cls", "global class FieldFlowAtRisk { }") == \
        ("ApexClass", "FieldFlowAtRisk", None)
    # The comment trap: prose "this class is ..." must NOT be parsed as the class name.
    assert parse_apex_text(".cls",
        "/** this class is the foundation */ global with sharing class FieldFlowRest { }"
    ) == ("ApexClass", "FieldFlowRest", None)
    try:
        parse_apex_text(".trigger", "oops no header")
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError on a malformed trigger")
    assert [f[0] for f in FIELDS] == [
        "ServiceAppointment.At_Risk__c", "ServiceAppointment.Delay_Minutes__c",
        "ServiceAppointment.At_Risk_Reason__c",
    ]
    # Payment object: the upsert key must be a unique external id, and the lookup must point at
    # ServiceAppointment — those two are what make the write idempotent and related.
    assert PAYMENT_OBJECT[0] == "FieldFlow_Payment__c"
    pf = dict(PAYMENT_FIELDS)
    assert pf["FieldFlow_Payment__c.Payment_Id__c"]["externalId"] is True
    assert pf["FieldFlow_Payment__c.Payment_Id__c"]["unique"] is True
    assert pf["FieldFlow_Payment__c.Service_Appointment__c"]["referenceTo"] == "ServiceAppointment"
    print("self-check ok")


def main(argv: list[str]) -> None:
    if not argv or argv[0] in ("-h", "--help"):
        sys.exit(__doc__)
    if argv[0] == "--self-check":
        self_check()
        return
    token, instance = get_token(*load_creds())
    print(f"Connected to {instance}\n")
    if argv[0] == "--fields":
        deploy_fields(token, instance)
        return
    if argv[0] == "--payment":
        deploy_payment(token, instance)
        return
    if argv[0] == "--payment-perms":
        grant_payment_perms(token, instance)
        return
    for arg in argv:
        deploy_apex(token, instance, Path(arg))


if __name__ == "__main__":
    main(sys.argv[1:])
