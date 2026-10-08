import { useMetrics } from "@/hooks/useOps";
import { cn } from "@/lib/cn";
import type { MetricTile } from "@/lib/metrics";

const BORDER: Record<MetricTile["tone"], string> = {
  accent: "border-l-accent",
  ok: "border-l-ok",
  warn: "border-l-warn",
  risk: "border-l-risk",
  info: "border-l-info",
  muted: "border-l-faint",
};
const TEXT: Record<MetricTile["tone"], string> = {
  accent: "text-accent",
  ok: "text-ok",
  warn: "text-warn",
  risk: "text-risk",
  info: "text-info",
  muted: "text-fg",
};

export function MetricsStrip() {
  const { data, isError } = useMetrics();

  if (isError) {
    return <p className="p-3 font-mono text-[11px] text-faint">/metrics unavailable — is the backend up?</p>;
  }

  return (
    <div className="grid grid-cols-2 gap-2">
      {(data ?? []).map((t) => (
        <div
          key={t.key}
          className={cn("rounded border border-l-2 border-border bg-surface px-3 py-2", BORDER[t.tone])}
        >
          <div className={cn("font-mono text-xl font-semibold tabular-nums leading-none", TEXT[t.tone])}>
            {t.value}
          </div>
          <div className="mt-1 font-mono text-[10px] uppercase tracking-wide text-faint">{t.label}</div>
        </div>
      ))}
      <p className="col-span-2 pt-1 text-center font-mono text-[9px] text-faint">
        parsed live from GET /metrics (Prometheus)
      </p>
    </div>
  );
}
