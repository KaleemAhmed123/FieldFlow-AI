#!/usr/bin/env python3
"""Deterministic generator for the FieldFlow AI Excalidraw diagrams.

Rebuilds the rich presentation diagrams from code so IDs, bindings and layout
stay consistent and re-runnable. (The original generator lived in scratchpad and
was lost; this restores the capability the diagrams README references.)

Run from anywhere:   python docs/specs/field-service-recovery/diagrams/gen_diagrams.py
Writes the .excalidraw files next to this script. 04-scaffold is left untouched
(it is historical — the thin-spine origin).

Colour key (kept from the original):
  yellow  #ffd43b  customer-facing / core
  green   #b2f2bb  deterministic / knowledge
  violet  #d0bfff  AI & tools
  red     #ffc9c9  failure / event
  blue    #a5d8ff  external systems
  grey    #e9ecef  infra / data
"""
from __future__ import annotations

import json
import math
import os

# ---------------------------------------------------------------- palette
YEL = "#ffd43b"; YEL_BG = "#fff3bf"
GRN = "#b2f2bb"; GRN_BG = "#ebfbee"
VIO = "#d0bfff"; VIO_BG = "#f3f0ff"
RED = "#ffc9c9"; RED_BG = "#fff0f0"
BLU = "#a5d8ff"; BLU_BG = "#e7f5ff"
GRY = "#ced4da"; GRY_BG = "#f1f3f5"
INK = "#1e1e1e"
MUT = "#495057"

_counter = 0


def _nid() -> str:
    global _counter
    _counter += 1
    return f"ff{_counter:04d}"


def _seed() -> int:
    global _counter
    return 100000 + _counter * 7


class Canvas:
    def __init__(self) -> None:
        self.els: list[dict] = []

    # -- primitives ----------------------------------------------------
    def _base(self, typ: str, x: float, y: float, w: float, h: float) -> dict:
        return {
            "id": _nid(), "type": typ, "x": x, "y": y, "width": w, "height": h,
            "angle": 0, "strokeColor": INK, "backgroundColor": "transparent",
            "fillStyle": "solid", "strokeWidth": 2, "strokeStyle": "solid",
            "roughness": 1, "opacity": 100, "groupIds": [], "frameId": None,
            "roundness": None, "seed": _seed(), "version": 1, "versionNonce": _seed(),
            "isDeleted": False, "boundElements": [], "updated": 1, "link": None,
            "locked": False,
        }

    def zone(self, x, y, w, h, label, stroke=GRY, fill=GRY_BG, dash=False):
        r = self._base("rectangle", x, y, w, h)
        r["strokeColor"] = stroke; r["backgroundColor"] = fill
        r["roundness"] = {"type": 3}; r["strokeWidth"] = 1.5
        r["strokeStyle"] = "dashed" if dash else "solid"
        self.els.append(r)
        if label:
            t = self._base("text", x + 14, y + 10, max(120, len(label) * 11), 22)
            t.update({"strokeColor": MUT, "fontSize": 16, "fontFamily": 5,
                      "text": label, "textAlign": "left", "verticalAlign": "top",
                      "containerId": None, "originalText": label, "lineHeight": 1.25})
            self.els.append(t)
        return r

    def box(self, x, y, w, h, text, fill=YEL, stroke=INK, fs=16, dash=False):
        r = self._base("rectangle", x, y, w, h)
        r["backgroundColor"] = fill; r["strokeColor"] = stroke
        r["roundness"] = {"type": 3}
        r["strokeStyle"] = "dashed" if dash else "solid"
        tid = _nid()
        lines = text.count("\n") + 1
        t = {
            "id": tid, "type": "text", "x": x + 8, "y": y + h / 2 - (fs * 1.25 * lines) / 2,
            "width": w - 16, "height": fs * 1.25 * lines, "angle": 0,
            "strokeColor": INK, "backgroundColor": "transparent", "fillStyle": "solid",
            "strokeWidth": 2, "strokeStyle": "solid", "roughness": 1, "opacity": 100,
            "groupIds": [], "frameId": None, "roundness": None, "seed": _seed(),
            "version": 1, "versionNonce": _seed(), "isDeleted": False,
            "boundElements": [], "updated": 1, "link": None, "locked": False,
            "fontSize": fs, "fontFamily": 5, "text": text, "textAlign": "center",
            "verticalAlign": "middle", "containerId": r["id"], "originalText": text,
            "lineHeight": 1.25,
        }
        r["boundElements"].append({"type": "text", "id": tid})
        self.els.append(r); self.els.append(t)
        return r

    def label(self, x, y, text, fs=14, color=MUT, align="left", w=None):
        w = w or max(80, int(len(max(text.split("\n"), key=len)) * fs * 0.58))
        lines = text.count("\n") + 1
        t = self._base("text", x, y, w, fs * 1.25 * lines)
        t.update({"strokeColor": color, "fontSize": fs, "fontFamily": 5,
                  "text": text, "textAlign": align, "verticalAlign": "top",
                  "containerId": None, "originalText": text, "lineHeight": 1.25})
        self.els.append(t)
        return t

    def arrow(self, a, b, label=None, color=INK, dash=False, two=False):
        ax, ay = a["x"] + a["width"] / 2, a["y"] + a["height"] / 2
        bx, by = b["x"] + b["width"] / 2, b["y"] + b["height"] / 2

        def border(box, tx, ty):
            cx, cy = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
            dx, dy = tx - cx, ty - cy
            if dx == 0 and dy == 0:
                return cx, cy
            hw, hh = box["width"] / 2, box["height"] / 2
            sx = hw / abs(dx) if dx else math.inf
            sy = hh / abs(dy) if dy else math.inf
            s = min(sx, sy)
            return cx + dx * s, cy + dy * s

        sx, sy = border(a, bx, by)
        ex, ey = border(b, ax, ay)
        arr = self._base("arrow", sx, sy, abs(ex - sx), abs(ey - sy))
        arr["strokeColor"] = color
        arr["strokeStyle"] = "dashed" if dash else "solid"
        arr["points"] = [[0, 0], [ex - sx, ey - sy]]
        arr["lastCommittedPoint"] = None
        arr["startBinding"] = {"elementId": a["id"], "focus": 0.0, "gap": 4}
        arr["endBinding"] = {"elementId": b["id"], "focus": 0.0, "gap": 4}
        arr["startArrowhead"] = "arrow" if two else None
        arr["endArrowhead"] = "arrow"
        arr["roundness"] = {"type": 2}
        a["boundElements"].append({"type": "arrow", "id": arr["id"]})
        b["boundElements"].append({"type": "arrow", "id": arr["id"]})
        self.els.append(arr)
        if label:
            mx, my = (sx + ex) / 2, (sy + ey) / 2
            self.label(mx - len(label) * 3.3, my - 20, label, fs=12, color=color)
        return arr

    def dump(self) -> dict:
        return {"type": "excalidraw", "version": 2, "source": "fieldflow-gen",
                "elements": self.els,
                "appState": {"viewBackgroundColor": "#ffffff", "gridSize": 20},
                "files": {}}


def title(c: Canvas, x, y, text, sub=None):
    t = c._base("text", x, y, max(300, len(text) * 18), 36)
    t.update({"strokeColor": INK, "fontSize": 30, "fontFamily": 5, "text": text,
              "textAlign": "left", "verticalAlign": "top", "containerId": None,
              "originalText": text, "lineHeight": 1.25})
    c.els.append(t)
    if sub:
        c.label(x, y + 42, sub, fs=15, color=MUT)


# =====================================================================
# 01 — System architecture (logical, live)
# =====================================================================
def d01():
    c = Canvas()
    title(c, 60, 30, "FieldFlow AI — System Architecture (live)",
          "AI proposes · deterministic policy decides · human approves risk · RCS is the control plane.  "
          "Orchestrator on Render · e-com on Vercel · data on Supabase.")

    # customer
    c.zone(60, 110, 1180, 90, "L1 · EXPERIENCE", YEL, YEL_BG)
    cust = c.box(90, 135, 300, 50, "Customer\nAndroid · Google Messages (RCS)", YEL)

    # communication (Vonage)
    c.zone(60, 220, 1180, 120, "L2 · COMMUNICATION — Vonage Messages API (managed)", BLU, BLU_BG)
    v_send = c.box(90, 250, 220, 56, "RCS send\nJWT / RS256", BLU)
    v_in = c.box(330, 250, 220, 56, "Inbound webhook\n/webhooks/inbound", BLU)
    v_st = c.box(570, 250, 220, 56, "Status webhook\n/webhooks/status", BLU)
    v_fb = c.box(810, 250, 220, 56, "RCS → SMS\nfailover (NFR-1)", BLU)

    # ingress (FastAPI on Render)
    c.zone(60, 360, 1180, 120, "L3 · INGRESS — FastAPI (Render)", YEL, YEL_BG)
    g_sf = c.box(90, 390, 250, 56, "/webhooks/sf/at-risk\n← Apex HTTP callout (live)", YEL)
    g_sim = c.box(360, 390, 220, 56, "/sim/*\noffline twin (tests/demo)", YEL)
    g_corr = c.box(600, 390, 230, 56, "correlationId stamped\n(one tenancy key)", YEL)
    g_api = c.box(850, 390, 180, 56, "/cases /tools\n/health /metrics", YEL)

    # queue
    c.zone(60, 500, 1180, 100, "L7 · RELIABILITY — CloudAMQP (RabbitMQ)", GRY, GRY_BG)
    q_ex = c.box(90, 525, 300, 52, "exchange → queue\nidempotency on eventId (NFR-2)", GRY_BG, GRY)
    q_dlq = c.box(410, 525, 320, 52, "retry · exponential backoff · DLQ\n→ reconciliation (NFR-3)", RED_BG, RED)

    # orchestrator
    c.zone(60, 620, 780, 300, "L3 · ORCHESTRATION — LangGraph (Render)", YEL, YEL_BG)
    o_state = c.box(90, 650, 330, 56, "Case state machine\ncheckpoint · interrupt · resume", YEL)
    o_llm = c.box(90, 730, 330, 56, "LLM proposer (Level 2)\nGroq → Gemini → deterministic", VIO)
    o_pol = c.box(90, 810, 330, 56, "Policy Engine (Level 1)\ndeterministic authority", GRN)
    o_tool = c.box(460, 650, 350, 56, "Toolbox (read + action tools)\nladder-gated mutations", VIO)
    o_rag = c.box(460, 730, 350, 56, "retrieve_knowledge (RAG)\nLlamaIndex", GRN)
    o_hum = c.box(460, 810, 350, 56, "Human gate (Level 3)\napprove risky / low-confidence", RED)

    # knowledge + enterprise
    c.zone(860, 620, 380, 140, "L4 · KNOWLEDGE", GRN, GRN_BG)
    k_vec = c.box(885, 650, 330, 56, "pgvector (Supabase)\n209 chunks · Jina embed+rerank", GRN)
    k_note = c.box(885, 715, 330, 34, "manuals · warranty · SOP · part-fit", GRN_BG, GRN, fs=13)

    c.zone(860, 780, 380, 300, "L6 · ENTERPRISE / EXTERNAL", BLU, BLU_BG)
    e_sf = c.box(885, 810, 330, 52, "Salesforce Field Service\nreads+reschedule · Apex REST", BLU)
    e_ecom = c.box(885, 872, 330, 52, "e-com inventory (Vercel)\nproduct · price · stock + MCP", BLU)
    e_com = c.box(885, 934, 330, 52, "Service-Commerce (module)\nprice-book authority", VIO)
    e_rzp = c.box(885, 996, 330, 52, "Razorpay (Test-Mode)\nOpen-URL / webview", BLU)

    # data + observability
    c.zone(60, 940, 780, 140, "L7 · DATA & OBSERVABILITY", GRY, GRY_BG)
    d_pg = c.box(90, 970, 430, 56, "Supabase Postgres\ncase_state · idempotency · audit · ai_decisions", GRY_BG, GRY)
    d_log = c.box(540, 970, 270, 56, "Logfire (OTel)\ngod-eye trace per case", GRY_BG, GRY)

    # flow arrows
    c.arrow(cust, v_send, two=True)
    c.arrow(v_in, g_api, "customer tap")
    c.arrow(v_st, d_log, "delivery/read", dash=True)
    c.arrow(g_sf, q_ex); c.arrow(g_sim, q_ex)
    c.arrow(q_ex, o_state, "consume")
    c.arrow(q_ex, q_dlq, "on failure", color="#c92a2a", dash=True)
    c.arrow(o_state, o_llm); c.arrow(o_llm, o_pol); c.arrow(o_pol, o_hum, "risky")
    c.arrow(o_state, o_tool); c.arrow(o_state, o_rag)
    c.arrow(o_rag, k_vec)
    c.arrow(o_tool, e_sf); c.arrow(o_tool, e_ecom); c.arrow(o_tool, e_com)
    c.arrow(e_com, e_rzp)
    c.arrow(o_pol, v_send, color="#2b8a3e")  # offer options → RCS (label dropped: long cross-zone arrow)
    c.arrow(o_state, d_pg, dash=True)
    c.arrow(o_state, d_log, dash=True)
    return c


# =====================================================================
# 02 — Customer journey (13 stages over RCS)
# =====================================================================
def d02():
    c = Canvas()
    title(c, 60, 30, "FieldFlow AI — Customer Journey over RCS",
          "One failed AC appointment, fully recovered inside one chat thread — no app, no phone call. "
          "Tag = the RCS primitive each step uses.")
    stages = [
        ("1", "Appointment card\n+ actions", "rich card", YEL),
        ("2", "Technician delay\nfires at_risk", "SF trigger", RED),
        ("3", "AI investigates\ncontext + SLA", "RAG + LLM", VIO),
        ("4", "Policy removes\nillegal options", "Level 1", GRN),
        ("5", "Valid slots as\na carousel", "carousel", YEL),
        ("6", "Customer taps\na slot", "suggested reply", YEL),
        ("7", "Share location\n→ ETA", "inbound location", YEL),
        ("8", "Upload photo of\nunit label", "inbound image", YEL),
        ("9", "Vision + RAG:\nmodel · warranty · part", "RAG", VIO),
        ("10", "Inventory reserved\natomically", "action tool", GRN),
        ("11", "Quote card\nApprove & Pay", "rich card", YEL),
        ("12", "Pay via webview\n(Razorpay Test)", "Open-URL", BLU),
        ("13", "Confirm + calendar\n+ dial + PDF report", "PDF card", YEL),
    ]
    cols = 4
    bw, bh, gx, gy = 250, 92, 40, 70
    x0, y0 = 70, 150
    boxes = []
    for i, (n, body, prim, fill) in enumerate(stages):
        r, ccol = divmod(i, cols)
        # serpentine so arrows chain left→right then right→left
        col = ccol if r % 2 == 0 else (cols - 1 - ccol)
        x = x0 + col * (bw + gx)
        y = y0 + r * (bh + gy)
        b = c.box(x, y, bw, bh, f"{n}.  {body}", fill)
        c.label(x + 6, y - 20, f"» {prim}", fs=12, color=MUT)
        boxes.append(b)
    for i in range(len(boxes) - 1):
        c.arrow(boxes[i], boxes[i + 1])
    # footnote
    c.zone(70, y0 + 4 * (bh + gy) - 10, 1180, 70, None, GRN, GRN_BG)
    c.label(90, y0 + 4 * (bh + gy) + 2,
             "Live: RCS send + inbound/status webhooks verified on a real Android (2026-10-09).   "
             "POC stand-ins (labelled in the trace): photo OCR · Share-Location ETA · PDF report — the RCS primitives are real.",
             fs=13, color=MUT)
    return c


# =====================================================================
# 03 — Decision authority + confidence model (AI focus)
# =====================================================================
def d03():
    c = Canvas()
    title(c, 60, 30, "FieldFlow AI — Authority Ladder & Confidence",
          "The AI never decides. Deterministic rules decide what is allowed; humans approve risk.")

    # ladder
    c.zone(60, 120, 520, 360, "THE AUTHORITY LADDER", INK, "#ffffff")
    l1 = c.box(90, 160, 460, 80,
               "LEVEL 1 — DETERMINISTIC\nCan this legally/technically happen?\npermission · SLA · stock · price · state · idempotency", GRN)
    l2 = c.box(90, 270, 460, 80,
               "LEVEL 2 — AI\nWhat's probably happening? Which fix is best?\nHow to explain it? (runs only if L1 allowed)", VIO)
    l3 = c.box(90, 380, 460, 80,
               "LEVEL 3 — HUMAN\nApprove a high-risk / low-confidence call\n(graph interrupts and waits)", RED)
    c.arrow(l1, l2, "possible?"); c.arrow(l2, l3, "risky?")

    # every mutation
    c.zone(620, 120, 620, 360, "EVERY MUTATION TAKES THE SAME PATH", INK, "#ffffff")
    seq = [
        ("AI suggestion", VIO), ("Policy validation", GRN), ("Permission check", GRN),
        ("Idempotency check", GRY_BG), ("Transaction", YEL), ("Emit event", RED_BG),
        ("Audit + decision trace", GRY_BG),
    ]
    bx = []
    for i, (txt, fill) in enumerate(seq):
        y = 160 + i * 44
        b = c.box(650, y, 560, 34, txt, fill, fs=14)
        bx.append(b)
    for i in range(len(bx) - 1):
        c.arrow(bx[i], bx[i + 1])

    # confidence model
    c.zone(60, 510, 1180, 300, "CONFIDENCE — evidence-weighted, not a number the model invents", VIO, VIO_BG)
    factors = [
        ("archetype prior", "0.40", "how hard the reason is", GRN),
        ("policy headroom", "0.20", "room L1 left (APPROVED/PARTIAL/DENIED)", GRN),
        ("grounding", "0.15", "strength of retrieved RAG", GRN),
        ("data completeness", "0.10", "fraction of key fields present", GRN),
        ("LLM self-rating", "0.15", "clamped: min(self, prior)", VIO),
    ]
    fx = []
    for i, (name, w, why, fill) in enumerate(factors):
        x = 90 + i * 228
        b = c.box(x, 560, 210, 92, f"{name}\nweight {w}\n{why}", fill, fs=13)
        fx.append(b)
    blend = c.box(360, 690, 300, 56, "weighted blend\n= confidence", YEL)
    for b in fx:
        c.arrow(b, blend)
    gate = c.box(720, 690, 460, 56,
                 "GATE → human if ANY: reason in ALWAYS_HUMAN (safety/warranty)\n· confidence < 0.70 · policy DENIED", RED)
    c.arrow(blend, gate)
    c.label(90, 760, "The clamp is the point: the model can only LOWER confidence, never inflate a risky case past the gate.",
             fs=13, color=MUT)
    return c


# =====================================================================
# 05 — AI decision pipeline (LangGraph node-by-node)
# =====================================================================
def d05():
    c = Canvas()
    title(c, 60, 30, "FieldFlow AI — The AI Decision Pipeline (LangGraph)",
          "What each node does, and where the LLM is used vs deterministic code. Violet = AI · green = deterministic · red = pause.")
    nodes = [
        ("appointment.at_risk", "event in (SF trigger or /sim)", RED),
        ("load_context", "customer · asset · warranty · technician · stock", GRN),
        ("retrieve_knowledge", "RAG: manuals · warranty · SOP (pgvector)", VIO),
        ("generate_options", "LLM proposer: candidate fixes + message\nGroq → Gemini → deterministic", VIO),
        ("policy_validate", "Level 1: drop illegal options + blend confidence", GRN),
        ("human_approval", "Level 3: interrupt & wait (if risky/low-conf)", RED),
        ("offer_to_customer", "send RCS carousel → interrupt, wait for tap", YEL),
        ("resume_on_reply", "version check (NFR-6) → reserve · quote · pay", GRN),
        ("verify", "state consistent across SF · stock · commerce", GRN),
        ("close", "work order closed + service report (PDF)", YEL),
    ]
    x = 90
    bw, bh = 430, 74
    y0 = 150
    boxes = []
    for i, (name, body, fill) in enumerate(nodes):
        y = y0 + i * (bh + 26)
        b = c.box(x, y, bw, bh, f"{name}\n{body}", fill, fs=14)
        boxes.append(b)
    for i in range(len(boxes) - 1):
        c.arrow(boxes[i], boxes[i + 1])

    # side annotations
    c.zone(600, 150, 640, 300, "WHERE THE AI IS (bounded)", VIO, VIO_BG)
    c.box(630, 190, 580, 56, "LLM proposes candidate resolutions + the customer message. "
          "It never mutates state.", VIO, fs=14)
    c.box(630, 258, 580, 56, "RAG grounds the proposal in the right manual/warranty — every passage "
          "becomes a knowledgeSource in the trace.", GRN, fs=14)
    c.box(630, 326, 580, 56, "Confidence is evidence-weighted; the LLM's own score is clamped so it "
          "can only lower it. (see diagram 03)", VIO, fs=14)
    c.box(630, 394, 580, 40, "Deterministic rung always returns valid JSON → an LLM outage can't take "
          "the loop down.", GRN, fs=13)

    c.zone(600, 470, 640, 250, "WHAT THE GRAPH PERSISTS", GRY, GRY_BG)
    c.box(630, 510, 580, 50, "Checkpoint to Supabase Postgres → a paused case survives a restart "
          "and resumes, not restarts.", GRY_BG, GRY, fs=14)
    c.box(630, 572, 580, 50, "ai_decisions row = {decision, reason[], knowledgeSources[], toolsUsed[], "
          "confidence, policyResult}.", GRY_BG, GRY, fs=13)
    c.box(630, 634, 580, 50, "Every node, tool call, SQL query + the LLM call ride one Logfire trace, "
          "keyed by correlationId.", GRY_BG, GRY, fs=13)
    # link resume loop back to offer (the two waits)
    c.arrow(boxes[6], boxes[5], "or wait for human", color="#c92a2a", dash=True)
    return c


# =====================================================================
# 06 — MCP: the two modes kept apart
# =====================================================================
def d06():
    c = Canvas()
    title(c, 60, 30, "FieldFlow AI — Tools & MCP (two modes, kept apart)",
          "The deterministic recovery pipeline does NOT use LLM tool-selection. The agentic admin copilot does — that is what earns real MCP.")

    # Mode A
    c.zone(60, 130, 560, 560, "MODE A — DETERMINISTIC PIPELINE (recovery flow)", GRN, GRN_BG)
    a_graph = c.box(100, 170, 480, 56, "LangGraph node calls a tool BY NAME\n(no model picks the tool)", GRN)
    a_tool = c.box(100, 250, 480, 56, "In-process Toolbox\nread tools · action tools (ladder-gated)", VIO)
    a_sf = c.box(100, 340, 230, 70, "Salesforce\nApex REST\n(live reads+reschedule)", BLU)
    a_ec = c.box(350, 340, 230, 70, "e-com inventory\nHTTP API (Vercel)\nfind_part · reserve", BLU)
    a_note = c.box(100, 440, 480, 56, "Policy decides; mutations run the authority ladder.\nNo MCP needed on the mutation path.", GRN)
    a_guard = c.box(100, 520, 480, 48, "GUARDRAIL: LLM never fires an unsupervised mutation.", RED)
    c.arrow(a_graph, a_tool); c.arrow(a_tool, a_sf); c.arrow(a_tool, a_ec)
    c.arrow(a_tool, a_note, dash=True)

    # Mode B
    c.zone(680, 130, 560, 560, "MODE B — AGENTIC ADMIN COPILOT (panel chat)", VIO, VIO_BG)
    b_chat = c.box(720, 170, 480, 56, "Admin asks an open-ended question\n(control-panel chat)", YEL)
    b_llm = c.box(720, 250, 480, 56, "LLM MCP client\nDISCOVERS + PICKS tools by description", VIO)
    b_sfm = c.box(720, 340, 230, 80, "Salesforce\nHosted MCP\n8 read-only Apex tools\n(built; live arming deferred)", BLU, dash=True)
    b_ecm = c.box(970, 340, 230, 80, "e-com MCP server\n/api/mcp (Vercel)\nLIVE → 200", BLU)
    b_read = c.box(720, 450, 480, 48, "Reads flow freely across SF + e-com.", GRN)
    b_guard = c.box(720, 520, 480, 48, "GUARDRAIL: any write stays human-confirmed.", RED)
    c.arrow(b_chat, b_llm); c.arrow(b_llm, b_sfm); c.arrow(b_llm, b_ecm)
    c.arrow(b_llm, b_read, dash=True)

    c.zone(60, 710, 1180, 90, "WHY REAL MCP ONLY NOW", INK, "#ffffff")
    c.label(90, 735,
             "A purely deterministic pipeline never needed MCP (tools are called by name). The open-ended copilot can't hardcode "
             "every question→tool mapping — it must discover and pick tools by description. That is exactly MCP's job, so it earns its place here.",
             fs=14, color=MUT)
    return c


# =====================================================================
# 07 — Reliability & the six failure demos
# =====================================================================
def d07():
    c = Canvas()
    title(c, 60, 30, "FieldFlow AI — Reliability & Failure Demos",
          "Nothing lost · nothing twice · everything explainable. Break it on purpose from the panel and watch it recover.")

    # spine
    c.zone(60, 120, 1180, 130, "THE RELIABILITY SPINE", GRY, GRY_BG)
    s_in = c.box(90, 155, 220, 70, "inbound event / webhook\ncorrelationId + eventId", YEL)
    s_q = c.box(340, 155, 220, 70, "CloudAMQP (RabbitMQ)\nretry → backoff → DLQ", GRY_BG, GRY)
    s_g = c.box(590, 155, 220, 70, "LangGraph consumer\nidempotent (dedupe)", GRN)
    s_pg = c.box(840, 155, 370, 70, "Supabase Postgres\ncase_state · idempotency · audit · ai_decisions", GRY_BG, GRY)
    c.arrow(s_in, s_q); c.arrow(s_q, s_g); c.arrow(s_g, s_pg)

    # six demos grid
    demos = [
        ("NFR-1", "RCS unavailable / rejected", "Vonage RCS → SMS failover; message still lands, flow continues.", BLU),
        ("NFR-2", "Duplicate webhook / double tap", "Idempotency on the UUID — 2nd copy ignored; no double reschedule/charge.", GRN),
        ("NFR-3", "Salesforce temporarily down", "Event not lost: retry → backoff → DLQ → reconcile; completes on return.", RED),
        ("NFR-4", "AI low-confidence / risky", "Routed to human approval before any execution (Level 3).", VIO),
        ("NFR-5", "Stock changed before execute", "Atomic reserve fails cleanly → graph recalculates → re-offers.", GRN),
        ("NFR-6", "Reply against stale version", "Conversation state versioned; stale tap rejected, current options re-sent.", YEL),
    ]
    bw, bh, gx, gy = 560, 110, 60, 40
    x0, y0 = 70, 300
    for i, (nfr, scen, fix, fill) in enumerate(demos):
        r, col = divmod(i, 2)
        x = x0 + col * (bw + gx)
        y = y0 + r * (bh + gy)
        c.box(x, y, bw, bh, f"{nfr} — {scen}\n\n{fix}", fill, fs=14)

    c.zone(70, y0 + 3 * (bh + gy) - 6, 1120, 86, "OBSERVABILITY", GRY, GRY_BG)
    c.label(100, y0 + 3 * (bh + gy) + 22,
             "Logfire (OTel) traces every request/case end to end — webhook → queue → each node → each tool call → each SQL query → the LLM call — "
             "keyed by correlationId. The decision trace rides the span AND is stored in Postgres. The telemetry is real, not staged.",
             fs=14, color=MUT)
    return c


# =====================================================================
# 08 — Deployment topology (what runs where)
# =====================================================================
def d08():
    c = Canvas()
    title(c, 60, 30, "FieldFlow AI — Deployment Topology",
          "What runs where, and the env var that wires each hop. Managed free tiers; ₹0 to run.")

    # Render
    c.zone(60, 120, 520, 360, "RENDER — orchestrator (FastAPI + LangGraph)", GRN, GRN_BG)
    r_app = c.box(90, 160, 460, 60, "fieldflow-ai-w6bm.onrender.com\nFastAPI · consumer · graph · policy · toolbox", GRN)
    r_hook = c.box(90, 236, 460, 44, "/webhooks/sf/at-risk · /webhooks/inbound · /sim/*", YEL)
    r_sec = c.box(90, 294, 460, 44, "Secret File: vonage private.key → /etc/secrets", GRY_BG, GRY)
    r_env = c.box(90, 352, 460, 100,
                  "env wires everything:\nDATABASE_URL · AMQP_URL · GROQ/GEMINI/JINA keys\nSF_* · ECOM_API_URL · VONAGE_* · RAZORPAY_* · LOGFIRE_TOKEN", GRY_BG, GRY, fs=13)

    # Vercel  (env var that wires each hop printed INSIDE the box → no colliding arrow labels)
    c.zone(620, 120, 620, 150, "VERCEL — e-com inventory", BLU, BLU_BG)
    v_app = c.box(650, 160, 560, 44, "field-flow-ai.vercel.app  (Next.js, root = apps/ecom)", BLU)
    v_api = c.box(650, 212, 270, 44, "/api/products · /stock · /reserve\n← ECOM_API_URL", BLU, fs=13)
    v_mcp = c.box(940, 212, 270, 44, "/api/mcp (MCP server, 200)", BLU, fs=13)

    # Supabase
    c.zone(620, 300, 300, 230, "SUPABASE", GRY, GRY_BG)
    su_pg = c.box(650, 340, 240, 70, "Postgres (case + checkpoints)\n← DATABASE_URL", GRY_BG, GRY, fs=13)
    su_vec = c.box(650, 430, 240, 70, "pgvector · 209 RAG chunks\n← retrieval (Jina)", GRN, fs=13)

    # managed APIs
    c.zone(940, 300, 300, 230, "MANAGED APIs", VIO, VIO_BG)
    m_q = c.box(970, 340, 240, 44, "CloudAMQP (RabbitMQ)\n← AMQP_URL", GRY_BG, GRY, fs=13)
    m_llm = c.box(970, 398, 240, 44, "Groq · Gemini · Jina\n← *_API_KEY", VIO, fs=13)
    m_obs = c.box(970, 456, 240, 44, "Logfire · Razorpay Test\n← LOGFIRE_TOKEN · RAZORPAY_*", VIO, fs=12)

    # external orgs
    c.zone(60, 560, 1180, 150, "EXTERNAL ORGS (gated live)", RED, RED_BG)
    x_sf = c.box(90, 600, 350, 60, "Salesforce Field Service org\nApex trigger → callout (X-FieldFlow-Secret)", RED, fs=14)
    x_von = c.box(460, 600, 350, 60, "Vonage RCS agent (astrea_it)\ntest device · send JWT/RS256", RED, fs=14)
    x_dev = c.box(830, 600, 380, 60, "Customer Android (Google Messages)\nreal card 2026-10-09 · tap → webhook", YEL, fs=14)

    # wiring arrows — all label-less (every name is printed inside the boxes → no floating-label collisions)
    c.arrow(r_app, v_api)
    c.arrow(r_env, su_pg)
    c.arrow(r_env, su_vec, dash=True)
    c.arrow(r_env, m_q)
    c.arrow(r_env, m_llm, dash=True)
    c.arrow(r_env, m_obs, dash=True)
    c.arrow(v_api, su_pg, dash=True)          # e-com → Supabase (service role)
    c.arrow(x_sf, r_hook)                      # SF callout in
    c.arrow(r_sec, x_von)                      # RCS send out (key from the secret file)
    c.arrow(x_von, x_dev)
    c.arrow(x_dev, r_hook, dash=True)          # customer tap resumes the case
    return c


DIAGRAMS = {
    "01-system-architecture": d01,
    "02-customer-journey": d02,
    "03-decision-authority": d03,
    "05-ai-decision-pipeline": d05,
    "06-mcp-two-modes": d06,
    "07-reliability-failure-modes": d07,
    "08-deployment-topology": d08,
}


def _font(sz: int):
    from PIL import ImageFont
    for name in ("segoeui.ttf", "arial.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(name, sz)
        except OSError:
            continue
    return ImageFont.load_default()


def render_png(excalidraw_path: str) -> str:
    """Render an .excalidraw file to a PNG next to it. The PNG is the committed
    artifact; the .excalidraw stays local (gitignored). Approximate render
    (straight arrows, no hand-drawn roughness) — open the .excalidraw in
    Excalidraw for the polished version."""
    from PIL import Image, ImageDraw
    els = json.load(open(excalidraw_path, encoding="utf-8"))["elements"]
    xs = [e["x"] for e in els]; ys = [e["y"] for e in els]
    xe = [e["x"] + e.get("width", 0) for e in els]
    ye = [e["y"] + e.get("height", 0) for e in els]
    minx, miny, maxx, maxy = min(xs), min(ys), max(xe), max(ye)
    pad, S = 40, 1.4
    img = Image.new("RGB", (int((maxx - minx + 2 * pad) * S), int((maxy - miny + 2 * pad) * S)), "white")
    dr = ImageDraw.Draw(img)
    tx = lambda x: int((x - minx + pad) * S)
    ty = lambda y: int((y - miny + pad) * S)
    for e in els:
        if e["type"] == "rectangle":
            bg = e.get("backgroundColor", "transparent")
            dr.rounded_rectangle([tx(e["x"]), ty(e["y"]), tx(e["x"] + e["width"]), ty(e["y"] + e["height"])],
                                 radius=8, fill=None if bg == "transparent" else bg,
                                 outline=e.get("strokeColor", INK), width=2)
    for e in els:
        if e["type"] == "arrow":
            p = e["points"]
            x0, y0 = tx(e["x"] + p[0][0]), ty(e["y"] + p[0][1])
            x1, y1 = tx(e["x"] + p[-1][0]), ty(e["y"] + p[-1][1])
            col = e.get("strokeColor", INK)
            if e.get("strokeStyle") == "dashed":
                n = max(1, int(math.hypot(x1 - x0, y1 - y0) / 11))
                for i in range(0, n, 2):
                    dr.line([x0 + (x1 - x0) * i / n, y0 + (y1 - y0) * i / n,
                             x0 + (x1 - x0) * (i + 1) / n, y0 + (y1 - y0) * (i + 1) / n], fill=col, width=2)
            else:
                dr.line([x0, y0, x1, y1], fill=col, width=2)
            a = math.atan2(y1 - y0, x1 - x0); L = 10
            dr.polygon([(x1, y1), (x1 - L * math.cos(a - 0.4), y1 - L * math.sin(a - 0.4)),
                        (x1 - L * math.cos(a + 0.4), y1 - L * math.sin(a + 0.4))], fill=col)
    for e in els:
        if e["type"] == "text":
            fs = int(e.get("fontSize", 16) * S * 0.85)
            f = _font(max(10, fs)); lines = e["text"].split("\n"); cid = e.get("containerId")
            if cid:
                cont = next((r for r in els if r["id"] == cid), None)
                cx, cy = tx(cont["x"] + cont["width"] / 2), ty(cont["y"] + cont["height"] / 2)
                yy = cy - len(lines) * (fs + 3) / 2
                for ln in lines:
                    w = dr.textlength(ln, font=f)
                    dr.text((cx - w / 2, yy), ln, fill=e.get("strokeColor", INK), font=f); yy += fs + 3
            else:
                xx, yy = tx(e["x"]), ty(e["y"])
                for ln in lines:
                    dr.text((xx, yy), ln, fill=e.get("strokeColor", INK), font=f); yy += fs + 3
    out = excalidraw_path.rsplit(".excalidraw", 1)[0] + ".png"
    img.save(out)
    return out


def main() -> None:
    here = os.path.dirname(os.path.abspath(__file__))
    for name, fn in DIAGRAMS.items():
        global _counter
        _counter = 0  # reset so IDs are stable per file
        c = fn()
        path = os.path.join(here, f"{name}.excalidraw")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(c.dump(), f, indent=2)
        print(f"wrote {name}.excalidraw  ({len(c.els)} elements)")
    # Render EVERY .excalidraw in the folder (incl. 04-scaffold, not generated here)
    # to a committed PNG. The .excalidraw files are gitignored; the PNGs are the deliverable.
    for fp in sorted(f for f in os.listdir(here) if f.endswith(".excalidraw")):
        out = render_png(os.path.join(here, fp))
        print(f"  rendered {os.path.basename(out)}")


if __name__ == "__main__":
    main()
