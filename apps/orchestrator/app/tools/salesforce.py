"""Salesforce read/action backing behind an interface. MCP-vs-REST stays swappable.

Split concern-wise (one method per object) so the graph composes context from granular reads and
the decision trace's `toolsUsed` is real. The Toolbox (app/tools/registry.py) wraps these as the
MCP surface; the action tool runs the authority ladder before `reschedule` is applied.

FakeSalesforce resolves one demo appointment to its linked customer/asset/technician — the same
appointment → related-records shape real hosted MCP returns. Unknown ids return None so an action
tool can refuse. Real Field Service (R3 — the DE org) swaps in behind the same methods later.
"""

from __future__ import annotations

from typing import Protocol


class SalesforceTools(Protocol):
    def get_appointment(self, appointment_id: str) -> dict | None: ...
    def get_customer(self, customer_id: str) -> dict | None: ...
    def get_asset(self, asset_id: str) -> dict | None: ...
    def get_technician(self, resource_id: str) -> dict | None: ...
    def reschedule(self, appointment_id: str, slot_id: str) -> dict: ...


class FakeSalesforce:
    """In-memory demo org. One appointment links to a customer, asset and technician."""

    def __init__(self) -> None:
        # Step 7b: flip this (via /sim/fault) to simulate Salesforce being down — every read then
        # raises, the consumer handler fails, and the message dead-letters to events.dlq.
        self.down: bool = False
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
            "SR-1": {"name": "Rahul Kumar", "skills": ["inverter-ac"], "territory": "Noida"},
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

    def reschedule(self, appointment_id: str, slot_id: str) -> dict:
        """Apply the chosen slot (fake). The Toolbox action ran the authority ladder first."""
        return {"appointmentId": appointment_id, "slotId": slot_id, "status": "RESCHEDULED"}
