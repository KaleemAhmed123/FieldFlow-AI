"""RestInventory maps the e-com HTTP contract onto the InventoryTools interface, and
build_inventory stays mock-first (FakeInventory unless ECOM_API_URL is set).

No live server: httpx.MockTransport answers the calls, so these run fully offline.
"""

from __future__ import annotations

import json

import httpx
from app.config import Settings
from app.tools.inventory import FakeInventory, RestInventory, build_inventory


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_find_part_returns_locations() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/stock/PCB-492"
        return httpx.Response(200, json={
            "partNo": "PCB-492",
            "locations": [{"location": "Noida", "qty": 1}, {"location": "Delhi", "qty": 0}],
        })

    inv = RestInventory("http://ecom.test", client=_client(handler))
    assert inv.find_part("PCB-492") == [
        {"location": "Noida", "qty": 1}, {"location": "Delhi", "qty": 0},
    ]


def test_reserve_ok_and_refusal() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/reserve"
        body = json.loads(request.content)
        return httpx.Response(200, json={"ok": body["partNo"] == "HAVE"})

    inv = RestInventory("http://ecom.test", client=_client(handler))
    assert inv.reserve("HAVE") is True          # stock held
    assert inv.reserve("GONE") is False         # lost the race → refusal, not an oversell (NFR-5)


def test_build_inventory_is_mock_first() -> None:
    assert isinstance(build_inventory(Settings(ecom_api_url="")), FakeInventory)
    assert isinstance(build_inventory(Settings(ecom_api_url="http://ecom.test")), RestInventory)
