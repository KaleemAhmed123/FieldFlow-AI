"""Dump the contract as JSON Schema so the frontend can generate TS types.

Run: `python -m fieldflow_contract.export_schema` → writes schema/*.json next to this package.
"""

from __future__ import annotations

import json
from pathlib import Path

from .events import AppointmentAtRisk
from .types import Card, CaseView, SlotOption

MODELS = [AppointmentAtRisk, SlotOption, Card, CaseView]


def main() -> None:
    out = Path(__file__).resolve().parent.parent / "schema"
    out.mkdir(exist_ok=True)
    for model in MODELS:
        (out / f"{model.__name__}.json").write_text(
            json.dumps(model.model_json_schema(), indent=2), encoding="utf-8"
        )
    print(f"wrote {len(MODELS)} schemas to {out}")


if __name__ == "__main__":
    main()
