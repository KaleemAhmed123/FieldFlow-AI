"""Inventory tool interface. Stub in the spine; real Salesforce Field Service inventory later."""

from __future__ import annotations

from typing import Protocol


class InventoryTools(Protocol):
    def find_part(self, part_no: str) -> list[dict]: ...


class FakeInventory:
    def find_part(self, part_no: str) -> list[dict]:
        return [{"location": "Noida", "qty": 7}, {"location": "Delhi", "qty": 0}]
