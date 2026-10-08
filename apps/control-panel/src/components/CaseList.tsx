import { CircleDot, Search } from "lucide-react";
import { useMemo, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import type { CaseRow } from "@/lib/api";
import { cn } from "@/lib/cn";
import { confidencePct, eventReason, humanize, isPaused, statusMeta, timeAgo } from "@/lib/trace";

export function CaseList({
  cases,
  selectedId,
  onSelect,
  loading,
}: {
  cases: CaseRow[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  loading: boolean;
}) {
  const [q, setQ] = useState("");
  const [onlyActive, setOnlyActive] = useState(false);

  const filtered = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return cases.filter((c) => {
      if (onlyActive && ["CLOSED", "PAID", "VERIFIED", "REJECTED"].includes(c.status)) return false;
      if (!needle) return true;
      const hay = `${c.correlationId} ${c.status} ${eventReason(c.decisionTrace) ?? ""} ${
        c.context?.customer?.name ?? ""
      }`.toLowerCase();
      return hay.includes(needle);
    });
  }, [cases, q, onlyActive]);

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="shrink-0 space-y-2 border-b border-border p-3">
        <div className="flex items-center justify-between">
          <h2 className="font-mono text-[11px] font-semibold uppercase tracking-[0.12em] text-faint">
            Cases <span className="text-muted">({filtered.length})</span>
          </h2>
          <button
            onClick={() => setOnlyActive((v) => !v)}
            className={cn(
              "rounded px-2 py-0.5 font-mono text-[10px] uppercase tracking-wide transition-colors",
              onlyActive ? "bg-accent/15 text-accent" : "text-faint hover:text-fg",
            )}
          >
            active only
          </button>
        </div>
        <div className="flex items-center gap-2 rounded border border-border bg-bg px-2">
          <Search className="h-3.5 w-3.5 text-faint" />
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="search id, status, customer…"
            className="h-8 w-full bg-transparent font-mono text-xs text-fg placeholder:text-faint focus:outline-none"
          />
        </div>
      </div>

      <ScrollArea className="min-h-0 flex-1">
        <div className="divide-y divide-border">
          {filtered.map((c) => {
            const meta = statusMeta(c.status);
            const pct = confidencePct(c.decisionTrace);
            const reason = humanize(eventReason(c.decisionTrace));
            const selected = c.correlationId === selectedId;
            return (
              <button
                key={c.correlationId}
                onClick={() => onSelect(c.correlationId)}
                className={cn(
                  "block w-full px-3 py-2.5 text-left transition-colors",
                  selected ? "bg-surface2" : "hover:bg-surface2/50",
                )}
              >
                <div className="flex items-center justify-between gap-2">
                  <span
                    className={cn(
                      "truncate font-mono text-xs font-medium",
                      selected ? "text-accent" : "text-fg",
                    )}
                  >
                    {c.correlationId}
                  </span>
                  <span className="shrink-0 font-mono text-[10px] text-faint">{timeAgo(c.updatedAt)}</span>
                </div>
                <div className="mt-1.5 flex items-center justify-between gap-2">
                  <Badge tone={meta.tone}>
                    {isPaused(c.status) && <CircleDot className="h-3 w-3" />}
                    {meta.label}
                  </Badge>
                  {pct !== null && (
                    <span className="font-mono text-[10px] text-muted" title="confidence">
                      {pct}%
                    </span>
                  )}
                </div>
                {reason && (
                  <div className="mt-1 truncate font-mono text-[10px] uppercase tracking-wide text-faint">
                    {reason}
                  </div>
                )}
              </button>
            );
          })}
          {!loading && filtered.length === 0 && (
            <p className="p-4 text-center font-mono text-xs text-faint">
              {cases.length === 0 ? "no cases yet — fire one from the ops deck" : "no matches"}
            </p>
          )}
        </div>
      </ScrollArea>
    </div>
  );
}
