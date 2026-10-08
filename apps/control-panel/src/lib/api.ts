// The one client that talks to the orchestrator. Every endpoint lives here, typed.
// Set VITE_USE_FIXTURES=true to serve captured sample data instead (offline UI dev + demo with no
// backend/queue) — see fixtures.ts. The flag is read once here so the rest of the app is unaware.

import type { Card, SlotOption } from "./contract.gen";
import { fixtureBackend } from "./fixtures";
import type { CaseContext, DecisionTrace } from "./trace";

export type { Card, SlotOption };

/** A case row as GET /cases returns it (same shape as GET /cases/{id}). */
export interface CaseRow {
  correlationId: string;
  status: string;
  version?: number;
  context?: CaseContext;
  decisionTrace?: DecisionTrace;
  sentCard?: Card | null;
  updatedAt: string;
}

export interface ToolInfo {
  name: string;
  kind: "read" | "action";
  args: string[];
  description: string;
}
export interface ToolsSurface {
  reads: ToolInfo[];
  actions: ToolInfo[];
  note: string;
}
export interface DlqView {
  available: boolean;
  detail?: string;
  depth?: number;
  messages?: Array<Record<string, unknown>>;
}

export const API = import.meta.env.VITE_API_URL ?? "http://localhost:8000";
export const USE_FIXTURES = import.meta.env.VITE_USE_FIXTURES === "true";

async function getJSON<T>(path: string): Promise<T> {
  const r = await fetch(`${API}${path}`);
  if (!r.ok) throw new Error(`GET ${path} -> ${r.status}`);
  return r.json() as Promise<T>;
}

async function postJSON<T>(path: string, body: unknown): Promise<T> {
  const r = await fetch(`${API}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body ?? {}),
  });
  if (!r.ok) throw new Error(`POST ${path} -> ${r.status}`);
  return r.json() as Promise<T>;
}

// ---- Reads -----------------------------------------------------------------
export const getCases = (): Promise<CaseRow[]> =>
  USE_FIXTURES ? fixtureBackend.listCases() : getJSON<CaseRow[]>("/cases");

export const getTools = (): Promise<ToolsSurface> =>
  USE_FIXTURES ? fixtureBackend.getTools() : getJSON<ToolsSurface>("/tools");

export const getDlq = (): Promise<DlqView> =>
  USE_FIXTURES ? fixtureBackend.getDlq() : getJSON<DlqView>("/dlq");

export async function getMetricsText(): Promise<string> {
  if (USE_FIXTURES) return fixtureBackend.getMetricsText();
  const r = await fetch(`${API}/metrics`);
  if (!r.ok) throw new Error(`GET /metrics -> ${r.status}`);
  return r.text();
}

export const getHealth = (): Promise<{ status: string }> =>
  USE_FIXTURES ? Promise.resolve({ status: "ok" }) : getJSON<{ status: string }>("/health");

// ---- Sim mutations (the offline twin of the real events) -------------------
export type Reason =
  | "technician_delay"
  | "traffic_weather"
  | "technician_no_show"
  | "customer_access_issue"
  | "part_missing"
  | "wrong_part_shipped"
  | "additional_fault_found"
  | "asset_complex"
  | "safety_risk"
  | "warranty_dispute";

export interface AtRiskBody {
  workOrderId?: string;
  appointmentId?: string;
  reason?: Reason;
  delayMinutes?: number;
  eventId?: string;
}
export interface FireResult {
  published: boolean;
  eventId: string;
  correlationId: string;
}

export const fireAtRisk = (body: AtRiskBody): Promise<FireResult> =>
  USE_FIXTURES ? fixtureBackend.fireAtRisk(body) : postJSON<FireResult>("/sim/appointment-at-risk", body);

export const customerReply = (body: { correlationId: string; slotId: string; version: number }) =>
  USE_FIXTURES ? fixtureBackend.customerReply(body) : postJSON("/sim/customer-reply", body);

export const approve = (body: { correlationId: string; approved: boolean }) =>
  USE_FIXTURES ? fixtureBackend.approve(body) : postJSON("/sim/approve", body);

export const payment = (body: {
  correlationId: string;
  paymentId?: string;
  status?: "captured" | "failed";
  eventId?: string;
}) => (USE_FIXTURES ? fixtureBackend.payment(body) : postJSON("/sim/payment", body));

export const deliveryStatus = (body: { messageUuid: string; status?: string; to?: string }) =>
  USE_FIXTURES ? fixtureBackend.deliveryStatus(body) : postJSON("/sim/delivery-status", body);

export const fault = (body: { salesforceDown: boolean }) =>
  USE_FIXTURES ? fixtureBackend.fault(body) : postJSON("/sim/fault", body);

export const replayDlq = () =>
  USE_FIXTURES ? fixtureBackend.replayDlq() : postJSON("/sim/dlq/replay", {});
