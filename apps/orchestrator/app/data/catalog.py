"""Load + query the product catalog (app/data/catalog.json) — the single source of truth for
inventory stock, Salesforce assets, the RAG corpus, and proposer grounding.

Pure data access, no DB/network. Later this same catalog seeds a real Salesforce / e-com.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

_CATALOG_PATH = Path(__file__).resolve().parent / "catalog.json"

# Stock levels seeded into FakeInventory, by part kind/flag. Scarce parts sit at 1 so the NFR-5
# inventory race can fire; consumables are plentiful; everything else has a small buffer.
_SCARCE_QTY = 1
_CONSUMABLE_QTY = 8
_DEFAULT_QTY = 3


@lru_cache(maxsize=1)
def load_catalog() -> dict[str, Any]:
    return json.loads(_CATALOG_PATH.read_text(encoding="utf-8"))


def models() -> list[dict[str, Any]]:
    return load_catalog()["models"]


def get_model(model_id: str) -> dict[str, Any] | None:
    return next((m for m in models() if m["modelId"] == model_id), None)


def model_for_asset(model_name: str) -> dict[str, Any] | None:
    """Find a model by its display name or by its id appearing in the name (Salesforce stores the
    display string, e.g. 'Frostline Inverter Split AC XYZ-492')."""
    for m in models():
        if m["name"] == model_name or m["modelId"] in model_name:
            return m
    return None


def parts_for_model(model_id: str) -> list[dict[str, Any]]:
    m = get_model(model_id)
    return m["parts"] if m else []


def fault_codes_for_model(model_id: str) -> list[dict[str, Any]]:
    m = get_model(model_id)
    return m["faultCodes"] if m else []


def find_part(part_no: str) -> dict[str, Any] | None:
    for m in models():
        for p in m["parts"]:
            if p["partNo"] == part_no:
                return p
    return None


def price_book_paise() -> dict[str, int]:
    """Every catalog part's price, for commerce to consume as its authority if it chooses to."""
    return {p["partNo"]: p["pricePaise"] for m in models() for p in m["parts"]}


def stock_seed() -> dict[str, list[dict[str, Any]]]:
    """Initial FakeInventory stock for every catalog part, keyed by part number."""
    seed: dict[str, list[dict[str, Any]]] = {}
    for m in models():
        for p in m["parts"]:
            if p.get("scarce"):
                qty = _SCARCE_QTY
            elif p["kind"] == "consumable":
                qty = _CONSUMABLE_QTY
            else:
                qty = _DEFAULT_QTY
            seed[p["partNo"]] = [{"location": "Noida", "qty": qty}, {"location": "Delhi", "qty": 0}]
    return seed
