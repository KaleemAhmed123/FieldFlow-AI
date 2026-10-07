// Talks to the orchestrator. Spine uses polling; WebSocket live-updates come later.

const API = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

export type SlotOption = { slotId: string; label: string; technician: string; note: string };
export type Card = { kind: string; title: string; options: SlotOption[] } | null;
export type CaseView = {
  correlationId: string;
  status: string;
  context: Record<string, unknown>;
  decisionTrace: Record<string, unknown>;
  sentCard: Card;
  updatedAt: string;
};

export async function listCases(): Promise<CaseView[]> {
  const r = await fetch(`${API}/cases`);
  if (!r.ok) return [];
  return r.json();
}

export async function fireAtRisk(eventId?: string): Promise<void> {
  await fetch(`${API}/sim/appointment-at-risk`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(eventId ? { eventId } : {}),
  });
}
