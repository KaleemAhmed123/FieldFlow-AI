"""Inventory tool interface. Fake with mutable stock so the inventory race (NFR-5) can fire.

`find_part` is the safe read; `reserve` is the atomic action tool — it decrements under a check,
so a reserve that loses the race returns False instead of overselling. Real Salesforce Field
Service inventory swaps in behind the same two methods later.
"""

from __future__ import annotations

from typing import Protocol


class InventoryTools(Protocol):
    def find_part(self, part_no: str) -> list[dict]: ...
    def reserve(self, part_no: str, qty: int = 1) -> bool: ...


class FakeInventory:
    """In-memory stock keyed by part number, seeded from the product catalog (the single source of
    truth). Scarce parts sit at qty 1 so the inventory race (NFR-5) can fire. `set_stock` is the
    demo/test knob. Real Salesforce Field Service inventory swaps in behind the same two methods."""

    def __init__(self, stock: dict[str, list[dict]] | None = None) -> None:
        from app.data.catalog import stock_seed

        self._stock: dict[str, list[dict]] = stock if stock is not None else stock_seed()

    def find_part(self, part_no: str) -> list[dict]:
        return [dict(loc) for loc in self._stock.get(part_no, [])]

    def reserve(self, part_no: str, qty: int = 1) -> bool:
        """Atomic check-and-decrement at the first location with enough stock."""
        for loc in self._stock.get(part_no, []):
            if loc["qty"] >= qty:
                loc["qty"] -= qty
                return True
        return False

    def set_stock(self, part_no: str, qty: int) -> None:
        """Force total stock for a part (demo 'parts grabbed by another case' button)."""
        self._stock[part_no] = [{"location": "Noida", "qty": qty}]
