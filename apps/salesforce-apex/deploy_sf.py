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


def fail(ctx: str, res: dict) -> None:
    sys.exit(f"  FAILED {ctx}: {json.dumps(res)[:1000]}")


# --- pure parsing (offline-testable) --------------------------------------------------------------
def parse_apex_text(suffix: str, body: str) -> tuple[str, str, str | None]:
    """(tooling_type, name, sobject|None) from a .cls/.trigger body. Triggers carry the SObject."""
    if suffix == ".trigger":
        m = re.search(r"\btrigger\s+(\w+)\s+on\s+(\w+)", body)
        if not m:
            raise ValueError("can't find 'trigger <Name> on <SObject>' header")
        return "ApexTrigger", m.group(1), m.group(2)
    m = re.search(r"\bclass\s+(\w+)", body)
    if not m:
        raise ValueError("can't find 'class <Name>'")
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


def deploy_fields(token: str, instance: str) -> None:
    for full_name, meta in FIELDS:
        status, res = api("POST", token, instance, "/sobjects/CustomField",
                          {"FullName": full_name, "Metadata": meta})
        if status in (200, 201):
            print(f"  created field {full_name}")
        elif "duplicate" in json.dumps(res).lower() or "already" in json.dumps(res).lower():
            print(f"  field {full_name} already exists — ok")
        else:
            fail(f"field {full_name}", res)


def self_check() -> None:
    assert parse_apex_text(".trigger",
        "trigger ServiceAppointmentAtRisk on ServiceAppointment (after insert, after update) {}"
    ) == ("ApexTrigger", "ServiceAppointmentAtRisk", "ServiceAppointment")
    assert parse_apex_text(".cls", "global class FieldFlowAtRisk { }") == \
        ("ApexClass", "FieldFlowAtRisk", None)
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
    for arg in argv:
        deploy_apex(token, instance, Path(arg))


if __name__ == "__main__":
    main(sys.argv[1:])
