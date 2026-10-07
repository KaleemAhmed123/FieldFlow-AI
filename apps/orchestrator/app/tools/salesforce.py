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
        self._appointments: dict[str, dict] = {
            "SA-19281": {
                "appointmentId": "SA-19281",
                "customerId": "CON-1",
                "assetId": "AST-1",
                "resourceId": "SR-1",
                "slaWindowMinutes": 120,
                "caseState": "OPEN",
            },
        }
        self._customers: dict[str, dict] = {
            "CON-1": {"name": "Kaleem Ahmed", "phone": "+91-90000-00000"},
        }
        self._assets: dict[str, dict] = {
            "AST-1": {"model": "Daikin Inverter AC XYZ-492", "warranty": "active"},
        }
        self._technicians: dict[str, dict] = {
            "SR-1": {"name": "Rahul Kumar", "skills": ["daikin-inverter"], "territory": "Noida"},
        }

    def get_appointment(self, appointment_id: str) -> dict | None:
        appt = self._appointments.get(appointment_id)
        return dict(appt) if appt else None

    def get_customer(self, customer_id: str) -> dict | None:
        cust = self._customers.get(customer_id)
        return dict(cust) if cust else None

    def get_asset(self, asset_id: str) -> dict | None:
        asset = self._assets.get(asset_id)
        return dict(asset) if asset else None

    def get_technician(self, resource_id: str) -> dict | None:
        tech = self._technicians.get(resource_id)
        return dict(tech) if tech else None

    def reschedule(self, appointment_id: str, slot_id: str) -> dict:
        """Apply the chosen slot (fake). The Toolbox action ran the authority ladder first."""
        return {"appointmentId": appointment_id, "slotId": slot_id, "status": "RESCHEDULED"}
