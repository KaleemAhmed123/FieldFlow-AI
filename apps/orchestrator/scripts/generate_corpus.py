"""Generate the synthetic knowledge corpus (all fake) for the Daikin XYZ-492 demo asset.

Deterministic + idempotent: re-running overwrites the same files byte-identically. Multi-format on
purpose (PDF/md/CSV) so the ingestor is exercised against real-world variety. No real manuals - the
content is invented but structured like the real thing (sections, page numbers, fault tables,
warranty clauses, part-compat rows, links) so retrieval + citations are meaningful.

Run:  uv run python scripts/generate_corpus.py
"""

from __future__ import annotations

from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer

CORPUS = Path(__file__).resolve().parent.parent / "app" / "rag" / "corpus"


def _pdf(path: Path, title: str, pages: list[list[str]]) -> None:
    """Write a multi-page PDF; each inner list is one page's paragraphs (first = heading)."""
    styles = getSampleStyleSheet()
    doc = SimpleDocTemplate(str(path), pagesize=A4, title=title)
    flow = []
    for i, page in enumerate(pages):
        flow.append(Paragraph(f"<b>{page[0]}</b>", styles["Heading2"]))
        flow.append(Spacer(1, 10))
        for para in page[1:]:
            flow.append(Paragraph(para, styles["BodyText"]))
            flow.append(Spacer(1, 6))
        flow.append(Spacer(1, 12))
        flow.append(Paragraph(f"<i>{title} - page {i + 1}</i>", styles["Normal"]))
        if i < len(pages) - 1:
            flow.append(PageBreak())
    doc.build(flow)


def main() -> None:
    CORPUS.mkdir(parents=True, exist_ok=True)

    # 1) Service manual - multi-page, with a fault-code table and the control-board section.
    _pdf(
        CORPUS / "service-manual.pdf",
        "Daikin Inverter AC XYZ-492 - Service Manual",
        [
            [
                "1. Overview",
                "The Daikin Inverter AC XYZ-492 is a split inverter air conditioner. This manual "
                "covers diagnosis, fault codes, and board-level repair for authorised technicians.",
                "Reference: https://support.example-daikin.test/xyz-492/manual",
            ],
            [
                "2. Fault codes",
                "F3 - Control board (PCB) failure. The inverter PCB cannot drive the compressor. "
                "Replace the control board assembly; compatible part is PCB-492 with capacitor "
                "CAP-492. Requires skill 'daikin-inverter'.",
                "F6 - Outdoor temperature sensor open circuit. Replace sensor; no board work.",
                "U4 - Indoor/outdoor communication error. Check harness before replacing any board.",
            ],
            [
                "3. Control board (PCB-492) replacement",
                "Isolate mains. Discharge CAP-492 before handling. Swap the PCB-492 assembly, refit "
                "CAP-492, and run the self-test. Estimated time 90 minutes. A loaner unit may be "
                "offered if PCB-492 stock is unavailable at the serving location.",
                "Safety: high-voltage capacitor - follow the discharge SOP before contact.",
            ],
        ],
    )

    # 2) Warranty policy - clauses + a coverage table-ish section + link.
    _pdf(
        CORPUS / "warranty-policy.pdf",
        "FieldFlow Warranty Policy v4",
        [
            [
                "Clause 1 - Coverage",
                "Assets under an active warranty are covered for parts and labour on inverter "
                "control-board (PCB) and compressor failures. Coverage makes the repair a free "
                "replacement; no quote or payment is raised.",
                "Policy reference: https://policy.example-fieldflow.test/warranty/v4",
            ],
            [
                "Clause 2 - Out-of-warranty path",
                "If warranty is expired or void, the control-board replacement is chargeable: a "
                "quote is raised for PCB-492 plus labour, and payment is collected before the visit "
                "is confirmed. Consumable filters are never covered.",
            ],
        ],
    )

    # 3) Troubleshooting / fault-code quick guide (markdown, heading-structured).
    (CORPUS / "troubleshooting-faultcodes.md").write_text(
        "# XYZ-492 Troubleshooting Quick Guide\n\n"
        "Source: https://support.example-daikin.test/xyz-492/troubleshooting\n\n"
        "## F3 control board failure\n"
        "Symptom: unit powers on, compressor never starts, fan runs. Most likely the inverter PCB. "
        "Confirm with the self-test, then replace PCB-492 (with CAP-492). Needs 'daikin-inverter' "
        "skill. Offer a loaner if PCB-492 is out of stock at the serving depot.\n\n"
        "## F6 temperature sensor\n"
        "Symptom: erratic temperature regulation. Replace the outdoor sensor; a standard visit, no "
        "board work and no scarce parts.\n\n"
        "## U4 communication error\n"
        "Symptom: indoor and outdoor units disagree. Inspect the interconnect harness first; do not "
        "replace a board until the harness is ruled out.\n",
        encoding="utf-8",
    )

    # 4) Technician SOP (markdown).
    (CORPUS / "technician-sop.md").write_text(
        "# Field Technician SOP - Inverter Board Repair\n\n"
        "Source: https://sop.example-fieldflow.test/inverter-board\n\n"
        "## Before travel\n"
        "Confirm the required skill ('daikin-inverter') and that the serving location holds the "
        "part (PCB-492). If stock is uncertain, reserve before dispatch to avoid a wasted visit.\n\n"
        "## High-voltage safety\n"
        "Always discharge CAP-492 before touching the board. If a safety risk is reported on site, "
        "stop and escalate for human approval before proceeding.\n\n"
        "## Completion\n"
        "Run the self-test, record the fault code cleared, and close the work order to generate the "
        "service report.\n",
        encoding="utf-8",
    )

    # 5) Part-compatibility table (CSV).
    (CORPUS / "part-compatibility.csv").write_text(
        "part_no,fits_model,description,requires_skill\n"
        "PCB-492,XYZ-492,Inverter control board assembly,daikin-inverter\n"
        "CAP-492,XYZ-492,High-voltage capacitor for PCB-492,daikin-inverter\n"
        "SENSOR-11,XYZ-492,Outdoor temperature sensor,general-hvac\n"
        "FILTER-100,XYZ-492,Consumable air filter (not warranty-covered),general-hvac\n",
        encoding="utf-8",
    )

    print(f"Corpus written to {CORPUS} ({len(list(CORPUS.iterdir()))} files)")


if __name__ == "__main__":
    main()
