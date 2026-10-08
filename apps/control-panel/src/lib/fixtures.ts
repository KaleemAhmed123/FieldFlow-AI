// A tiny in-memory twin of the orchestrator, used when VITE_USE_FIXTURES=true. It lets every view
// (incl. the paused/approval + commerce + failure states) render with no backend and no queue, and
// makes the failure-deck buttons visibly do something during offline dev/demo. It is NOT the real
// decision engine — transitions are deliberately shallow. For the real flow, point at the backend.

import type { AtRiskBody, CaseRow, DlqView, FireResult, ToolsSurface } from "./api";
import type { DecisionTrace } from "./trace";

const WEIGHTS = { prior: 0.25, headroom: 0.3, grounding: 0.2, data: 0.15, llm: 0.1 };

function trace(partial: Partial<DecisionTrace>): DecisionTrace {
  return {
    decision: "OFFER_RESCHEDULE",
    llmProvider: "groq",
    degraded: false,
    rateLimitNote: null,
    toolsUsed: [
      "salesforce.get_appointment",
      "salesforce.get_customer",
      "salesforce.get_asset",
      "salesforce.get_technician",
    ],
    knowledgeSources: [],
    removed: [],
    ...partial,
  };
}

let seq = 1;
function now(offsetMin = 0): string {
  return new Date(Date.now() - offsetMin * 60_000).toISOString();
}

function seed(): CaseRow[] {
  return [
    {
      correlationId: "WO-10281",
      status: "OPTIONS_SENT",
      version: 1,
      updatedAt: now(1),
      context: {
        appointmentId: "SA-19281",
        customer: { name: "Rhea Nair", phone: "+91 98••• ••210" },
        asset: { model: "ThermaCore 9000", warranty: "active" },
        technician: { name: "Arjun Mehta", skills: ["HVAC", "electrical"] },
        slaWindowMinutes: 120,
        caseState: "open",
      },
      sentCard: {
        kind: "carousel",
        title: "Your appointment needs a small adjustment",
        options: [
          { slotId: "t-today-1", label: "TODAY 14:00–16:00", technician: "Arjun Mehta", note: "Same technician" },
          { slotId: "t-today-2", label: "TODAY 16:30–18:30", technician: "Arjun Mehta", note: "Same technician" },
          { slotId: "t-tmrw-1", label: "TOMORROW 09:00–11:00", technician: "Sana Qureshi", note: "Earliest slot" },
        ],
      },
      decisionTrace: trace({
        reason: ["event=technician_delay", "policy=APPROVED"],
        confidence: 0.9,
        policyResult: "APPROVED",
        explanation:
          "Technician is running ~50 min late against a 120 min SLA window. Offer three same-day/next-morning slots with the same technician to preserve continuity.",
        knowledgeSources: [
          {
            source: "field-service-sop.md",
            locator: "§4 Rescheduling",
            link: "#",
            score: 0.74,
            snippet: "When a visit will miss its SLA window, offer the customer the next available slots with the same resource where possible...",
          },
        ],
        confidenceBreakdown: {
          final: 0.9,
          factors: { prior: 1.0, headroom: 1.0, grounding: 0.74, data: 1.0, llm: 0.9 },
          weights: WEIGHTS,
        },
      }),
    },
    {
      correlationId: "WO-COMPLEX",
      status: "AWAITING_APPROVAL",
      version: 1,
      updatedAt: now(3),
      context: {
        appointmentId: "SA-55120",
        customer: { name: "Dev Patel", phone: "+91 90••• ••884" },
        asset: { model: "ThermaCore 9000", warranty: "active" },
        technician: { name: "Sana Qureshi", skills: ["HVAC"] },
        slaWindowMinutes: 120,
        caseState: "open",
      },
      sentCard: null,
      decisionTrace: trace({
        reason: [
          "event=asset_complex",
          "policy=PARTIAL",
          "removed t-tmrw-2: technician lacks control-board certification",
        ],
        confidence: 0.67,
        policyResult: "PARTIAL",
        llmProvider: "gemini",
        explanation:
          "Complex control-board fault. Confidence 0.67 is below the 0.70 auto-send gate, so this pauses for an operator before anything is sent.",
        knowledgeSources: [
          {
            source: "thermacore-9000-manual.pdf",
            locator: "p.42 Fault F3",
            link: "#",
            score: 0.81,
            snippet: "Fault code F3 indicates a control-board failure; a certified technician must verify board revision before replacement...",
          },
        ],
        removed: [{ slotId: "t-tmrw-2", reason: "technician lacks control-board certification" }],
        confidenceBreakdown: {
          final: 0.67,
          factors: { prior: 0.4, headroom: 0.6, grounding: 0.81, data: 1.0, llm: 0.4 },
          weights: WEIGHTS,
        },
      }),
    },
    {
      correlationId: "WO-PART",
      status: "OPTIONS_SENT",
      version: 1,
      updatedAt: now(6),
      context: {
        appointmentId: "SA-30455",
        customer: { name: "Meera Iyer", phone: "+91 99••• ••017" },
        asset: { model: "AquaPure X2", warranty: "active" },
        technician: { name: "Arjun Mehta", skills: ["plumbing"] },
        slaWindowMinutes: 180,
        caseState: "open",
        inventory: { "PMP-114": 1 },
      },
      sentCard: {
        kind: "carousel",
        title: "Your appointment needs a small adjustment",
        options: [
          { slotId: "t-part-1", label: "TOMORROW 10:00–12:00", technician: "Arjun Mehta", note: "Pump in stock (1 left)" },
        ],
      },
      decisionTrace: trace({
        reason: ["event=part_missing", "policy=APPROVED"],
        confidence: 0.8,
        policyResult: "APPROVED",
        toolsUsed: [
          "salesforce.get_appointment",
          "salesforce.get_customer",
          "salesforce.get_asset",
          "salesforce.get_technician",
          "inventory.find_part",
        ],
        explanation:
          "A replacement pump (PMP-114) is required and one unit is in stock. Offer the earliest slot; the part is reserved atomically on the customer's tap.",
        knowledgeSources: [
          {
            source: "part-compat.csv",
            locator: "row 12",
            link: "#",
            score: 0.69,
            snippet: "AquaPure X2 is compatible with pump PMP-114 (supersedes PMP-110)...",
          },
        ],
        confidenceBreakdown: {
          final: 0.8,
          factors: { prior: 0.85, headroom: 1.0, grounding: 0.69, data: 1.0, llm: 0.8 },
          weights: WEIGHTS,
        },
      }),
    },
    {
      correlationId: "WO-PAY",
      status: "PAYMENT_PENDING",
      version: 2,
      updatedAt: now(9),
      context: {
        appointmentId: "SA-OOW",
        customer: { name: "Kabir Shah", phone: "+91 98••• ••655" },
        asset: { model: "ThermaCore 9000", warranty: "expired" },
        technician: { name: "Sana Qureshi", skills: ["HVAC", "electrical"] },
        slaWindowMinutes: 120,
        caseState: "open",
      },
      sentCard: {
        kind: "payment",
        title: "Approve & Pay ₹4,720.00",
        options: [],
        payUrl: "https://rzp.io/i/demo-link",
      },
      decisionTrace: trace({
        reason: [
          "event=additional_fault_found",
          "policy=APPROVED",
          "quote ₹4,720.00 (authority: price_book)",
        ],
        confidence: 0.82,
        policyResult: "APPROVED",
        toolsUsed: [
          "salesforce.get_appointment",
          "salesforce.get_customer",
          "salesforce.get_asset",
          "salesforce.get_technician",
          "commerce.create_quote",
          "commerce.create_order",
          "commerce.create_payment_link",
        ],
        explanation:
          "A newly-found fault is outside the original warranty scope, so the part is chargeable. The price book set ₹4,720.00; the customer approves and pays in one tap over RCS.",
        knowledgeSources: [
          {
            source: "warranty-terms.pdf",
            locator: "Clause 1",
            link: "#",
            score: 0.77,
            snippet: "Faults discovered outside the originally reported issue are not covered and are billable at the published rate...",
          },
        ],
        confidenceBreakdown: {
          final: 0.82,
          factors: { prior: 0.85, headroom: 1.0, grounding: 0.77, data: 1.0, llm: 0.82 },
          weights: WEIGHTS,
        },
        commerce: {
          quote: { amountPaise: 472000, currency: "INR", partNo: "CB-9000" },
          order: { orderId: "order_demo_01", amountPaise: 472000, currency: "INR" },
          paymentLink: { shortUrl: "https://rzp.io/i/demo-link" },
        },
      }),
    },
    {
      correlationId: "WO-CLOSED",
      status: "CLOSED",
      version: 1,
      updatedAt: now(22),
      context: {
        appointmentId: "SA-18840",
        customer: { name: "Anaya Rao", phone: "+91 97••• ••431" },
        asset: { model: "AquaPure X2", warranty: "active" },
        technician: { name: "Arjun Mehta", skills: ["plumbing"] },
        slaWindowMinutes: 180,
        caseState: "closed",
      },
      sentCard: null,
      decisionTrace: trace({
        reason: ["event=technician_delay", "policy=APPROVED"],
        confidence: 0.93,
        policyResult: "APPROVED",
        explanation: "Customer picked TODAY 15:00–17:00; rescheduled and confirmed.",
        confidenceBreakdown: {
          final: 0.93,
          factors: { prior: 1.0, headroom: 1.0, grounding: 0.72, data: 1.0, llm: 0.95 },
          weights: WEIGHTS,
        },
      }),
    },
  ];
}

const counters: Record<string, number> = {
  fieldflow_events_processed_total: 5,
  fieldflow_events_duplicate_total: 1,
  fieldflow_events_failed_total: 0,
  fieldflow_cards_sent_total: 4,
  fieldflow_sms_fallbacks_total: 0,
  fieldflow_dlq_replays_total: 0,
};

let cases = seed();
let sfDown = false;
let dlqDepth = 0;

function touch(id: string, patch: Partial<CaseRow>) {
  cases = cases.map((c) => (c.correlationId === id ? { ...c, ...patch, updatedAt: now(0) } : c));
}

/** Singleton the api layer delegates to when fixtures are on. Each method mimics one endpoint. */
export const fixtureBackend = {
  listCases: async (): Promise<CaseRow[]> =>
    [...cases].sort((a, b) => b.updatedAt.localeCompare(a.updatedAt)),

  getTools: async (): Promise<ToolsSurface> => ({
    note: "Read = safe lookup. Action = validated; the function decides, may refuse.",
    reads: [
      { name: "salesforce.get_appointment", kind: "read", args: ["appointmentId"], description: "The scheduled visit + its linked ids and SLA window." },
      { name: "salesforce.get_customer", kind: "read", args: ["customerId"], description: "Customer name + contact." },
      { name: "salesforce.get_asset", kind: "read", args: ["assetId"], description: "Asset model + warranty state." },
      { name: "salesforce.get_technician", kind: "read", args: ["resourceId"], description: "Technician name + skills." },
      { name: "inventory.find_part", kind: "read", args: ["partNo"], description: "Stock for a part across locations." },
    ],
    actions: [
      { name: "inventory.reserve", kind: "action", args: ["partNo", "qty"], description: "Atomically reserve stock; refuses if the part was taken since it was offered." },
      { name: "reschedule.confirm", kind: "action", args: ["appointmentId", "slotId"], description: "Confirm a new slot; refuses on an unknown/terminal case." },
      { name: "commerce.create_quote", kind: "action", args: ["workOrderId", "partNo"], description: "Price-book quote for a chargeable part (the book sets the amount)." },
      { name: "commerce.create_order", kind: "action", args: ["quote"], description: "Open an order from an approved quote." },
      { name: "commerce.create_payment_link", kind: "action", args: ["orderId", "amountPaise", "currency"], description: "Create the Approve & Pay link." },
    ],
  }),

  getDlq: async (): Promise<DlqView> => ({
    available: true,
    depth: dlqDepth,
    messages: Array.from({ length: dlqDepth }, (_, i) => ({
      event: "appointment.at_risk",
      correlationId: `WO-DLQ-${i + 1}`,
      note: "parked while Salesforce was down",
    })),
  }),

  getMetricsText: async (): Promise<string> =>
    Object.entries(counters)
      .map(([k, v]) => `# TYPE ${k} counter\n${k} ${v}`)
      .join("\n") + "\n",

  fireAtRisk: async (body: AtRiskBody): Promise<FireResult> => {
    const eventId = body.eventId ?? `evt_${Date.now()}`;
    const id = body.workOrderId ?? `WO-${1000 + seq++}`;
    const existing = cases.find((c) => c.correlationId === id);
    if (existing) {
      counters.fieldflow_events_duplicate_total += 1;
      return { published: true, eventId, correlationId: id };
    }
    if (sfDown) {
      dlqDepth += 1;
      counters.fieldflow_events_failed_total += 1;
      return { published: true, eventId, correlationId: id };
    }
    const reason = body.reason ?? "technician_delay";
    const complex = ["asset_complex", "safety_risk", "warranty_dispute"].includes(reason);
    counters.fieldflow_events_processed_total += 1;
    if (!complex) counters.fieldflow_cards_sent_total += 1;
    cases = [
      {
        correlationId: id,
        status: complex ? "AWAITING_APPROVAL" : "OPTIONS_SENT",
        version: 1,
        updatedAt: now(0),
        context: {
          appointmentId: body.appointmentId ?? "SA-NEW",
          customer: { name: "New Customer", phone: "+91 90••• ••000" },
          asset: { model: "ThermaCore 9000", warranty: "active" },
          technician: { name: "Arjun Mehta", skills: ["HVAC"] },
          slaWindowMinutes: 120,
          caseState: "open",
        },
        sentCard: complex
          ? null
          : {
              kind: "carousel",
              title: "Your appointment needs a small adjustment",
              options: [
                { slotId: "t-today-1", label: "TODAY 14:00–16:00", technician: "Arjun Mehta", note: "Same technician" },
                { slotId: "t-tmrw-1", label: "TOMORROW 09:00–11:00", technician: "Sana Qureshi", note: "Earliest slot" },
              ],
            },
        decisionTrace: trace({
          reason: [`event=${reason}`, `policy=${complex ? "PARTIAL" : "APPROVED"}`],
          confidence: complex ? 0.66 : 0.88,
          policyResult: complex ? "PARTIAL" : "APPROVED",
          explanation: complex
            ? "Low-confidence complex job — paused for an operator before anything is sent."
            : "Rescheduling within SLA; three same-day options offered.",
          confidenceBreakdown: {
            final: complex ? 0.66 : 0.88,
            factors: {
              prior: complex ? 0.4 : 1.0,
              headroom: complex ? 0.6 : 1.0,
              grounding: 0.7,
              data: 1.0,
              llm: complex ? 0.4 : 0.88,
            },
            weights: WEIGHTS,
          },
        }),
      },
      ...cases,
    ];
    return { published: true, eventId, correlationId: id };
  },

  customerReply: async (body: { correlationId: string; slotId: string; version: number }) => {
    touch(body.correlationId, { status: "CLOSED" });
    return { resumed: true };
  },

  approve: async (body: { correlationId: string; approved: boolean }) => {
    const c = cases.find((x) => x.correlationId === body.correlationId);
    if (!c) return { resumed: false };
    if (!body.approved) {
      touch(body.correlationId, { status: "REJECTED" });
    } else if (c.status === "AWAITING_QUOTE_APPROVAL") {
      touch(body.correlationId, { status: "PAYMENT_PENDING" });
    } else {
      counters.fieldflow_cards_sent_total += 1;
      touch(body.correlationId, {
        status: "OPTIONS_SENT",
        sentCard: {
          kind: "carousel",
          title: "Your appointment needs a small adjustment",
          options: [
            { slotId: "t-today-1", label: "TODAY 14:00–16:00", technician: "Sana Qureshi", note: "Certified technician" },
          ],
        },
      });
    }
    return { resumed: true };
  },

  payment: async (body: { correlationId: string; status?: string }) => {
    if ((body.status ?? "captured") === "captured") touch(body.correlationId, { status: "PAID" });
    return { resumed: true };
  },

  deliveryStatus: async (body: { messageUuid: string; status?: string }) => {
    if ((body.status ?? "failed") === "failed") counters.fieldflow_sms_fallbacks_total += 1;
    return { recorded: true, messageUuid: body.messageUuid, status: body.status ?? "failed" };
  },

  fault: async (body: { salesforceDown: boolean }) => {
    sfDown = body.salesforceDown;
    return { salesforceDown: sfDown };
  },

  replayDlq: async () => {
    const replayed = dlqDepth;
    counters.fieldflow_dlq_replays_total += replayed;
    dlqDepth = 0;
    return { replayed };
  },
};
