"""Inventory tool interface. Fake with mutable stock so the inventory race (NFR-5) can fire.

`find_part` is the safe read; `reserve` is the atomic action tool — it decrements under a check,
so a reserve that loses the race returns False instead of overselling. Inventory is a SEPARATE
source from Salesforce (Decision A, 2026-10-10): a real e-com inventory service (Node/Postgres)
owns product image + price + stock and swaps in behind these same two methods later.
"""

from __future__ import annotations

from typing import Any, Protocol

from app.logging import get_logger

log = get_logger("inventory")


class InventoryTools(Protocol):
    def find_part(self, part_no: str) -> list[dict]: ...
    def reserve(self, part_no: str, qty: int = 1) -> bool: ...


class FakeInventory:
    """In-memory stock keyed by part number, seeded from the product catalog (the single source of
    truth). Scarce parts sit at qty 1 so the inventory race (NFR-5) can fire. `set_stock` is the
    demo/test knob. A real e-com inventory service swaps in behind the same two methods (Dec. A)."""

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


class RestInventory:
    """Real inventory over the e-com service's HTTP API (Decision A: inventory is a SEPARATE
    e-com source — product image + price + stock live in a Node/Next.js + Supabase service, not
    Salesforce). Same two methods as FakeInventory, so build_toolbox, the graph and every test are
    untouched — only the wiring in main.py changes.

    Contract (the e-com side owns it):
      find_part → GET  {base}/api/stock/{partNo}  → {"partNo", "locations": [{location, qty}]}
      reserve   → POST {base}/api/reserve {partNo, qty} → {"ok": bool}  (atomic on the e-com side)

    `httpx` is imported lazily so an offline import of this module needs no network dep; a client
    can be injected for tests (httpx.MockTransport) without a live server.
    """

    def __init__(self, base_url: str, *, timeout: float = 10.0, client: Any = None) -> None:
        self._base = base_url.rstrip("/")
        self._timeout = timeout
        self._client = client

    def _get_client(self) -> Any:
        if self._client is None:
            import httpx  # lazy: only when the e-com adapter is actually wired

            self._client = httpx.Client(timeout=self._timeout)
        return self._client

    def find_part(self, part_no: str) -> list[dict]:
        resp = self._get_client().get(f"{self._base}/api/stock/{part_no}")
        if resp.status_code >= 400:
            log.error("ecom.find_part_rejected", part_no=part_no, status=resp.status_code,
                      body=resp.text)
        resp.raise_for_status()
        return resp.json().get("locations", [])

    def reserve(self, part_no: str, qty: int = 1) -> bool:
        # The e-com service runs the atomic check-and-decrement (a row-locked SQL function), so a
        # reserve that loses the race returns ok=False here instead of overselling (drives NFR-5).
        resp = self._get_client().post(
            f"{self._base}/api/reserve", json={"partNo": part_no, "qty": qty}
        )
        if resp.status_code >= 400:
            log.error("ecom.reserve_rejected", part_no=part_no, status=resp.status_code,
                      body=resp.text)
        resp.raise_for_status()
        return bool(resp.json().get("ok", False))


def build_inventory(settings: Any) -> InventoryTools:
    """FakeInventory unless ECOM_API_URL is set, then the real e-com adapter — the same
    mock-first, one-line-swap convention as build_vonage / build_gateway. Tests and a keyless run
    stay fully offline on the fake."""
    if getattr(settings, "ecom_api_url", ""):
        log.info("inventory.rest", base=settings.ecom_api_url)
        return RestInventory(settings.ecom_api_url)
    return FakeInventory()
