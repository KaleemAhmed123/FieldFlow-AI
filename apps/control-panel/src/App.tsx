import { useEffect, useState } from "react";
import { type CaseView, fireAtRisk, listCases } from "./api";

export default function App() {
  const [cases, setCases] = useState<CaseView[]>([]);
  const [lastEventId, setLastEventId] = useState<string | null>(null);

  useEffect(() => {
    const tick = () => listCases().then(setCases).catch(() => {});
    tick();
    const t = setInterval(tick, 2000); // spine: poll. WebSocket live-updates come later.
    return () => clearInterval(t);
  }, []);

  async function fireNew() {
    const id = `evt_${Date.now()}`;
    setLastEventId(id);
    await fireAtRisk(id);
  }

  return (
    <div className="mx-auto max-w-5xl p-6">
      <header className="mb-6">
        <h1 className="text-2xl font-bold">FieldFlow AI — Field Service Control Center</h1>
        <p className="text-sm text-slate-500">
          Thin spine: fire an at-risk appointment, watch the case recover through the pipeline.
        </p>
      </header>

      <div className="mb-6 flex items-center gap-3">
        <button
          onClick={fireNew}
          className="rounded-lg bg-indigo-600 px-4 py-2 font-medium text-white hover:bg-indigo-700"
        >
          Simulate technician delay (fire at-risk)
        </button>
        {lastEventId && (
          <button
            onClick={() => fireAtRisk(lastEventId)}
            className="rounded-lg border border-slate-300 px-4 py-2 text-sm hover:bg-slate-100"
            title="Re-send the same eventId to prove idempotency"
          >
            Re-fire same event (idempotency)
          </button>
        )}
      </div>

      {cases.length === 0 && (
        <p className="text-slate-400">No cases yet. Fire an event above.</p>
      )}

      <div className="space-y-4">
        {cases.map((c) => (
          <div key={c.correlationId} className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
            <div className="mb-2 flex items-center justify-between">
              <span className="font-mono text-sm text-slate-500">{c.correlationId}</span>
              <span className="rounded-full bg-emerald-100 px-3 py-1 text-xs font-semibold text-emerald-700">
                {c.status}
              </span>
            </div>

            {c.sentCard && (
              <div className="mb-3">
                <p className="mb-1 text-sm font-medium text-slate-700">📲 Sent to customer (RCS):</p>
                <div className="rounded-lg bg-slate-50 p-3">
                  <p className="mb-2 text-sm font-semibold">{c.sentCard.title}</p>
                  <div className="flex flex-wrap gap-2">
                    {c.sentCard.options.map((o) => (
                      <div key={o.slotId} className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-xs">
                        <div className="font-semibold">{o.label}</div>
                        <div className="text-slate-500">{o.technician} · {o.note}</div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )}

            <details className="text-xs text-slate-600">
              <summary className="cursor-pointer font-medium">AI decision trace</summary>
              <pre className="mt-2 overflow-x-auto rounded bg-slate-900 p-3 text-slate-100">
                {JSON.stringify(c.decisionTrace, null, 2)}
              </pre>
            </details>
          </div>
        ))}
      </div>
    </div>
  );
}
