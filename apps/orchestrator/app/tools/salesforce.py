"""Salesforce read/action tools behind an interface. MCP-vs-REST stays swappable.

Spine uses FakeSalesforce returning stub context. Real hosted MCP (or REST) fills these later
(R3 — the Field Service DE — must be ready first). Action tools will run the authority ladder
before mutating; the spine only reads.
"""

from __future__ import annotations

from typing import Protocol


class SalesforceTools(Protocol):
    def get_context(self, appointment_id: str) -> dict: ...


class FakeSalesforce:
    """Stub context for one at-risk appointment — all fake data."""

    def get_context(self, appointment_id: str) -> dict:
        return {
            "appointmentId": appointment_id,
            "customer": {"name": "Kaleem Ahmed", "phone": "+91-90000-00000"},
            "asset": {"model": "Daikin Inverter AC XYZ-492", "warranty": "active"},
            "technician": {"name": "Rahul Kumar", "skills": ["daikin-inverter"]},
            "slaWindowMinutes": 120,
        }
