// The decision trace + case context, typed by hand.
//
// WHY BY HAND: the backend types `decisionTrace` and `context` as dict[str, Any] (free-form), so
// the JSON Schema only covers the Card/SlotOption/CaseView envelope — see contract.gen.ts. These
// shapes are read off app/graph/build.py + app/llm/confidence.py and kept in sync by eye. If the
// graph adds a trace key, add it here.

export interface KnowledgeSource {
  source?: string | null;
  locator?: string | null;
  link?: string | null;
  score?: number;
  snippet?: string;
}

/** The five evidence-weighted factors blended into the final confidence (confidence.py). */
export interface ConfidenceFactors {
  prior: number; // how hard the reason is (easy -> 1.0)
  headroom: number; // policy room left: APPROVED 1.0 / PARTIAL 0.6 / DENIED 0.0
  grounding: number; // strength of the top RAG hit
  data: number; // fraction of key case fields present
  llm: number; // the model's own rating, clamped so it can only lower
}

export interface ConfidenceBreakdown {
  final: number;
  factors: ConfidenceFactors;
  weights: ConfidenceFactors;
}

export interface RemovedOption {
  slotId: string;
  reason: string;
}

export interface CommerceTrace {
  quote?: { amountPaise?: number; currency?: string; partNo?: string; [k: string]: unknown };
  order?: { orderId?: string; amountPaise?: number; currency?: string; [k: string]: unknown };
  paymentLink?: { shortUrl?: string; [k: string]: unknown };
  payment?: { status?: string; paymentId?: string; [k: string]: unknown };
  [k: string]: unknown;
}

/** "Show your work" — the hero of the panel. */
export interface DecisionTrace {
  decision?: string;
  reason?: string[];
  knowledgeSources?: KnowledgeSource[];
  toolsUsed?: string[];
  confidence?: number;
  confidenceBreakdown?: ConfidenceBreakdown;
  explanation?: string | null;
  llmProvider?: string | null;
  degraded?: boolean;
  rateLimitNote?: string | null;
  policyResult?: string;
  removed?: RemovedOption[];
  commerce?: CommerceTrace;
}

export interface CaseContext {
  appointmentId?: string;
  customer?: { name?: string; phone?: string; [k: string]: unknown };
  asset?: { model?: string; warranty?: string; [k: string]: unknown };
  technician?: { name?: string; skills?: string[]; [k: string]: unknown };
  slaWindowMinutes?: number;
  caseState?: string;
  inventory?: Record<string, number>;
  [k: string]: unknown;
}

// ---------------------------------------------------------------------------
// Status model — drives the timeline + the status badge tone.
// ---------------------------------------------------------------------------
export type Tone = "accent" | "ok" | "warn" | "risk" | "info" | "muted";

/** The one story, as four stages: AI proposes -> policy decides -> human approves -> RCS/customer. */
export type Stage = "propose" | "decide" | "human" | "customer" | "done";

export interface StatusMeta {
  label: string;
  tone: Tone;
  stage: Stage;
}

export const STATUS_META: Record<string, StatusMeta> = {
  LOADING: { label: "Loading", tone: "muted", stage: "propose" },
  OPTIONS_SENT: { label: "Options sent", tone: "info", stage: "customer" },
  AWAITING_APPROVAL: { label: "Awaiting approval", tone: "warn", stage: "human" },
  PAUSED: { label: "Paused", tone: "warn", stage: "human" },
  EXECUTED: { label: "Executed", tone: "accent", stage: "decide" },
  QUOTE_BUILT: { label: "Quote built", tone: "info", stage: "decide" },
  AWAITING_QUOTE_APPROVAL: { label: "Quote approval", tone: "warn", stage: "human" },
  ORDER_CREATED: { label: "Order created", tone: "info", stage: "decide" },
  PAYMENT_PENDING: { label: "Payment pending", tone: "warn", stage: "customer" },
  PAID: { label: "Paid", tone: "ok", stage: "done" },
  VERIFIED: { label: "Verified", tone: "ok", stage: "done" },
  CLOSED: { label: "Closed", tone: "ok", stage: "done" },
  REJECTED: { label: "Rejected", tone: "risk", stage: "done" },
};

/** The happy-path milestones, in order (commerce steps included). Paused states sit on top. */
export const LIFECYCLE = [
  "LOADING",
  "OPTIONS_SENT",
  "EXECUTED",
  "QUOTE_BUILT",
  "ORDER_CREATED",
  "PAYMENT_PENDING",
  "VERIFIED",
  "CLOSED",
] as const;

const PAUSED = new Set(["AWAITING_APPROVAL", "AWAITING_QUOTE_APPROVAL", "PAUSED"]);

export function statusMeta(status: string): StatusMeta {
  return STATUS_META[status] ?? { label: status, tone: "muted", stage: "decide" };
}

export function isPaused(status: string): boolean {
  return PAUSED.has(status);
}

/** Is this case waiting on a human (NFR-4 / high-value quote)? Used to surface the approve action. */
export function needsApproval(status: string): "human" | "quote" | null {
  if (status === "AWAITING_APPROVAL" || status === "PAUSED") return "human";
  if (status === "AWAITING_QUOTE_APPROVAL") return "quote";
  return null;
}

export function confidencePct(trace?: DecisionTrace): number | null {
  const c = trace?.confidence ?? trace?.confidenceBreakdown?.final;
  return typeof c === "number" ? Math.round(c * 100) : null;
}

/** Pull the at-risk reason out of the trace (reason[0] looks like "event=technician_delay"). */
export function eventReason(trace?: DecisionTrace): string | null {
  const first = trace?.reason?.find((r) => r.startsWith("event="));
  return first ? first.slice("event=".length) : null;
}

/** Humanize a snake_case reason: "technician_delay" -> "technician delay". */
export function humanize(s?: string | null): string {
  return (s ?? "").replace(/_/g, " ");
}

/** Compact relative time: "12s", "4m", "2h", "3d". */
export function timeAgo(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const s = Math.max(0, Math.round(diff / 1000));
  if (s < 60) return `${s}s`;
  const m = Math.round(s / 60);
  if (m < 60) return `${m}m`;
  const h = Math.round(m / 60);
  if (h < 24) return `${h}h`;
  return `${Math.round(h / 24)}d`;
}

/** integer paise -> "₹1,234.00" */
export function rupees(paise?: number): string {
  if (typeof paise !== "number") return "";
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 2,
  }).format(paise / 100);
}
