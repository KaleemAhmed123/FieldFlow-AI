"""Generate the RAG knowledge corpus from the product catalog (app/data/catalog.json).

Catalog-driven + deterministic: every model becomes a dense, multi-page service-manual PDF (real
PDFs via reportlab; pypdf reads them back), plus global docs (master warranty policy, technician
SOP, a troubleshooting quick-guide, and a part-compatibility matrix). Re-running overwrites the
same files; the ingestor keys off extracted TEXT, so re-ingest stays incremental.

All content is invented but structured like the real thing (sections, fault tables, replacement
procedures, warranty clauses, part-compat rows, links) so retrieval + citations are meaningful.

Run:  uv run python scripts/generate_corpus.py
"""

from __future__ import annotations

from pathlib import Path

from app.data.catalog import load_catalog, models
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer

CORPUS = Path(__file__).resolve().parent.parent / "app" / "rag" / "corpus"
BASE = "https://support.example-fieldflow.test"

# Category-specific flavour so manuals don't read identically across models.
INSTALL_FLAVOUR = {
    "air-conditioner": "Mount the indoor unit level, flare and torque the refrigerant lines, pull a vacuum to 500 microns, then release the R32 charge and confirm subcooling.",
    "water-purifier": "Flush the pre-filters for ten minutes, sanitise the RO/UV chamber, set the inlet TDS, and verify reject-to-product ratio before handover.",
    "refrigerator": "Let the unit stand upright for four hours before power-on, level the cabinet, and confirm the door gasket seals a paper strip on all four sides.",
    "washing-machine": "Remove the transit bolts, level the chassis against vibration, connect the inlet and standpipe drain, and run an empty calibration cycle.",
    "microwave": "Confirm the cavity is clear, verify the door interlocks cut power when opened, and run a one-minute water-load heat test.",
    "water-heater": "Fit the pressure-relief valve, fill the tank fully before switching on (dry-firing destroys the element), and set the thermostat to 60 C.",
    "dishwasher": "Connect the inlet and drain within the rated height, prime the softener with salt, and run a hot rinse before first use.",
    "air-purifier": "Remove the filter wrapping, seat the HEPA and carbon stacks, and calibrate the PM sensor in clean air for two minutes.",
    "kitchen-chimney": "Anchor to a load-bearing wall, align the duct with minimal bends, and confirm the auto-clean heater and baffle latch operate.",
    "induction-cooktop": "Confirm a dedicated 16A circuit, verify pan-detection with a ferrous pan, and check the cooling fan spins on load.",
}
SAFETY_FLAVOUR = {
    "air-conditioner": "Discharge the high-voltage capacitor before touching the inverter board. Recover refrigerant; never vent R32.",
    "water-purifier": "Isolate mains and relieve line pressure before opening the pump or valve housing.",
    "refrigerator": "R600a is flammable: no open flame, ensure ventilation, and recover before brazing.",
    "washing-machine": "Isolate mains and discharge; the heater circuit can hold a lethal charge. Never bypass the door interlock.",
    "microwave": "Discharge the HV capacitor to chassis before any work. The magnetron carries lethal voltage even unplugged.",
    "water-heater": "Isolate mains and relieve tank pressure. Never energise a partially filled tank.",
    "dishwasher": "Isolate mains and shut the inlet tap before removing the pump or heater.",
    "air-purifier": "Isolate mains; the motor capacitor can hold charge.",
    "kitchen-chimney": "Isolate mains before touching the motor run-capacitor.",
    "induction-cooktop": "Discharge the IGBT bus before service; the ceramic top can retain heat.",
}


def _pdf(path: Path, title: str, pages: list[tuple[str, list[str]]]) -> None:
    """Write a multi-page PDF; each (heading, paragraphs) tuple is one page."""
    styles = getSampleStyleSheet()
    doc = SimpleDocTemplate(str(path), pagesize=A4, title=title)
    flow = []
    for i, (heading, paras) in enumerate(pages):
        flow.append(Paragraph(f"<b>{heading}</b>", styles["Heading2"]))
        flow.append(Spacer(1, 10))
        for para in paras:
            flow.append(Paragraph(para, styles["BodyText"]))
            flow.append(Spacer(1, 6))
        flow.append(Spacer(1, 10))
        flow.append(Paragraph(f"<i>{title} — page {i + 1}</i>", styles["Normal"]))
        if i < len(pages) - 1:
            flow.append(PageBreak())
    doc.build(flow)


def _manual_pages(model: dict) -> list[tuple[str, list[str]]]:
    mid, cat = model["modelId"], model["category"]
    skill = model["requiresSkill"]
    link = f"{BASE}/{mid.lower()}/manual"
    specs = ", ".join(f"{k}: {v}" for k, v in model["specs"].items())

    # Page 1 — overview + specs
    p_overview = (
        "1. Overview & specifications",
        [
            f"The {model['name']} ({model['brand']}, {cat}) is covered by this service manual for "
            f"authorised technicians holding the '{skill}' skill. It documents diagnosis, fault "
            f"codes, and board/mechanical-level repair.",
            f"Specifications — {specs}.",
            f"Warranty: {model['warrantyMonths']} months. {model['warrantyCoverage']}",
            f"Reference: {link}",
        ],
    )
    # Page 2 — installation
    p_install = (
        "2. Installation & commissioning",
        [
            INSTALL_FLAVOUR.get(cat, "Install per the site survey and run the commissioning self-test."),
            "Record the serial number and commissioning date against the work order. A failed "
            "self-test must be cleared before the visit is closed.",
        ],
    )
    # Page 3 — fault codes (the dense diagnostic table; the retrieval target)
    fault_lines = []
    for fc in model["faultCodes"]:
        part = fc.get("likelyPart")
        action = (
            f"Replace {part}." if fc.get("needsPart") and part else "No part required; inspect and reset."
        )
        safety = " SAFETY: high-risk, follow discharge/isolation SOP." if fc.get("safetyRisk") else ""
        fault_lines.append(
            f"{fc['code']} — {fc['meaning']}. {action} Skill: {fc['skill']}.{safety}"
        )
    p_faults = ("3. Fault codes", fault_lines or ["No coded faults documented."])

    # Pages 4+ — part replacement procedures (two parts per page for density)
    part_pages: list[tuple[str, list[str]]] = []
    parts = model["parts"]
    for idx in range(0, len(parts), 2):
        group = parts[idx : idx + 2]
        paras = []
        for p in group:
            cover = "covered under active warranty (free)" if p["warrantyCovered"] else "chargeable (out of warranty scope)"
            paras.append(
                f"{p['partNo']} — {p['name']} ({p['kind']}). Isolate mains and follow the safety "
                f"SOP. Remove the faulty unit, fit {p['partNo']}, and run the self-test. Requires "
                f"'{p['requiresSkill']}'. This part is {cover}. List price ₹{p['pricePaise'] // 100:,}."
            )
        part_pages.append((f"{4 + idx // 2}. Part replacement — {group[0]['partNo']}" + (f" / {group[1]['partNo']}" if len(group) > 1 else ""), paras))

    # Final page — maintenance, safety, warranty annex
    covered = [p["partNo"] for p in parts if p["warrantyCovered"]]
    p_final = (
        f"{4 + len(part_pages)}. Maintenance, safety & warranty",
        [
            "Maintenance: inspect at each visit; clean or replace consumables on the service "
            "interval; log any recurring fault code.",
            SAFETY_FLAVOUR.get(cat, "Isolate mains and follow the discharge/isolation SOP before service."),
            f"Warranty annex: under an active warranty, {', '.join(covered) or 'no parts'} are "
            f"replaced free with labour. Consumables and cosmetic parts are never covered. If "
            f"warranty is expired or the fault is outside the original scope, the part is "
            f"chargeable: a quote is raised and payment is collected before the visit is confirmed.",
            f"Policy reference: {BASE}/warranty/v5",
        ],
    )
    return [p_overview, p_install, p_faults, *part_pages, p_final]


def _warranty_policy_pages() -> list[tuple[str, list[str]]]:
    cat_lines = [
        f"{m['name']} ({m['warrantyMonths']} mo): {m['warrantyCoverage']}" for m in models()
    ]
    return [
        (
            "Clause 1 — Coverage under active warranty",
            [
                "Assets under an active warranty are covered for parts and labour on the covered "
                "components listed per model. Coverage makes the repair a free replacement; no quote "
                "or payment is raised.",
                f"Policy reference: {BASE}/warranty/v5",
            ],
        ),
        (
            "Clause 2 — Out-of-warranty and out-of-scope path",
            [
                "If the warranty is expired or void, or the fault is outside the originally reported "
                "issue, the replacement is chargeable: a quote is raised for the part plus labour, "
                "and payment is collected before the visit is confirmed.",
                "Clause 3 — Consumables (filters, gaskets, belts, lamps, anode rods) are never "
                "covered. Clause 4 — A quote at or above the high-value threshold pauses for operator "
                "approval before it is sent to the customer.",
            ],
        ),
        ("Clause 5 — Per-model coverage summary", cat_lines),
    ]


def _troubleshooting_md() -> str:
    lines = [
        "# Troubleshooting Quick Guide",
        "",
        f"Source: {BASE}/troubleshooting",
        "",
    ]
    for m in models():
        lines.append(f"## {m['modelId']} — {m['name']}")
        for fc in m["faultCodes"][:3]:
            part = fc.get("likelyPart") or "none"
            lines.append(
                f"- {fc['code']}: {fc['meaning']}. Likely part: {part}. Skill: {fc['skill']}."
            )
        lines.append("")
    return "\n".join(lines)


def _sop_md() -> str:
    return (
        "# Field Technician SOP\n\n"
        f"Source: {BASE}/sop\n\n"
        "## Before travel\n"
        "Confirm the required skill for the fault code and that the serving location holds the part. "
        "If stock is uncertain, reserve before dispatch to avoid a wasted visit.\n\n"
        "## Safety\n"
        "Isolate mains and discharge any high-voltage capacitor before board work. If a safety risk "
        "is reported on site, stop and escalate for human approval before proceeding.\n\n"
        "## Completion\n"
        "Run the self-test, record the fault code cleared, and close the work order to generate the "
        "service report.\n"
    )


def _part_compat_csv() -> str:
    rows = ["part_no,fits_model,description,kind,requires_skill,warranty_covered"]
    for m in models():
        for p in m["parts"]:
            rows.append(
                f"{p['partNo']},{m['modelId']},{p['name']},{p['kind']},{p['requiresSkill']},{str(p['warrantyCovered']).lower()}"
            )
    return "\n".join(rows) + "\n"


def main() -> None:
    load_catalog()  # fail fast if the catalog is malformed
    CORPUS.mkdir(parents=True, exist_ok=True)
    # clear stale corpus so renamed/removed models don't linger
    for f in CORPUS.iterdir():
        if f.suffix.lower() in (".pdf", ".md", ".csv"):
            f.unlink()

    for m in models():
        _pdf(
            CORPUS / f"service-manual-{m['modelId'].lower()}.pdf",
            f"{m['name']} — Service Manual",
            _manual_pages(m),
        )

    _pdf(CORPUS / "warranty-policy.pdf", "FieldFlow Warranty Policy v5", _warranty_policy_pages())
    (CORPUS / "troubleshooting-faultcodes.md").write_text(_troubleshooting_md(), encoding="utf-8")
    (CORPUS / "technician-sop.md").write_text(_sop_md(), encoding="utf-8")
    (CORPUS / "part-compatibility.csv").write_text(_part_compat_csv(), encoding="utf-8")

    n = len(list(CORPUS.iterdir()))
    print(f"Corpus written to {CORPUS} ({n} files from {len(models())} models)")


if __name__ == "__main__":
    main()
