import { cn } from "@/lib/cn";
import type { ConfidenceBreakdown, ConfidenceFactors } from "@/lib/trace";
import { Tip } from "@/components/ui/tooltip";

const FACTOR_LABEL: Record<keyof ConfidenceFactors, string> = {
  prior: "reason prior",
  headroom: "policy headroom",
  grounding: "RAG grounding",
  data: "data completeness",
  llm: "LLM self (clamped)",
};

const FACTOR_WHY: Record<keyof ConfidenceFactors, string> = {
  prior: "How hard this reason is. Easy jobs score 1.0; a complex one is capped low so it can't auto-send.",
  headroom: "Room left after policy: APPROVED 1.0, PARTIAL 0.6, DENIED 0.0.",
  grounding: "Strength of the top retrieved knowledge passage.",
  data: "Fraction of the key case fields that were present.",
  llm: "The model's own rating — clamped so it can only lower confidence, never inflate it.",
};

const ORDER: Array<keyof ConfidenceFactors> = ["prior", "headroom", "grounding", "data", "llm"];

export function ConfidenceMeter({
  breakdown,
  confidence,
  threshold = 0.7,
}: {
  breakdown?: ConfidenceBreakdown;
  confidence?: number;
  threshold?: number;
}) {
  const final = breakdown?.final ?? confidence;
  if (typeof final !== "number") return null;
  const pass = final >= threshold;
  const pct = Math.round(final * 100);

  // ring geometry
  const r = 30;
  const circ = 2 * Math.PI * r;
  const offset = circ * (1 - Math.max(0, Math.min(1, final)));

  return (
    <div className="flex flex-col gap-4 sm:flex-row sm:items-center">
      <div className="flex items-center gap-3">
        <div className="relative h-[76px] w-[76px] shrink-0">
          <svg viewBox="0 0 76 76" className="h-full w-full -rotate-90">
            <circle cx="38" cy="38" r={r} fill="none" strokeWidth="6" className="stroke-border" />
            <circle
              cx="38"
              cy="38"
              r={r}
              fill="none"
              strokeWidth="6"
              strokeLinecap="round"
              strokeDasharray={circ}
              strokeDashoffset={offset}
              className={cn("transition-[stroke-dashoffset] duration-500", pass ? "stroke-accent" : "stroke-warn")}
            />
          </svg>
          <div className="absolute inset-0 flex flex-col items-center justify-center">
            <span className={cn("font-mono text-lg font-semibold leading-none", pass ? "text-accent" : "text-warn")}>
              {pct}
            </span>
            <span className="font-mono text-[9px] text-faint">/ 100</span>
          </div>
        </div>
        <div className="leading-tight">
          <div className="font-mono text-[11px] uppercase tracking-wide text-faint">confidence</div>
          <div className={cn("text-sm font-semibold", pass ? "text-accent" : "text-warn")}>
            {pass ? "clears gate" : "below gate"}
          </div>
          <div className="font-mono text-[10px] text-muted">gate {Math.round(threshold * 100)}%</div>
        </div>
      </div>

      {breakdown && (
        <div className="flex-1 space-y-1.5">
          {ORDER.map((k) => {
            const v = breakdown.factors[k] ?? 0;
            const w = breakdown.weights[k] ?? 0;
            return (
              <Tip key={k} label={FACTOR_WHY[k]} side="left">
                <div className="flex items-center gap-2">
                  <span className="w-28 shrink-0 truncate font-mono text-[10px] uppercase tracking-wide text-muted">
                    {FACTOR_LABEL[k]}
                  </span>
                  <div className="relative h-2 flex-1 overflow-hidden rounded-full bg-surface2">
                    <div
                      className="h-full rounded-full bg-accent/70 transition-[width] duration-500"
                      style={{ width: `${Math.round(v * 100)}%` }}
                    />
                  </div>
                  <span className="w-8 shrink-0 text-right font-mono text-[10px] text-fg">{v.toFixed(2)}</span>
                  <span className="w-10 shrink-0 text-right font-mono text-[9px] text-faint">×{w}</span>
                </div>
              </Tip>
            );
          })}
          <div className="pt-0.5 text-right font-mono text-[9px] text-faint">
            final = Σ (factor × weight), clamped to [0,1]
          </div>
        </div>
      )}
    </div>
  );
}
