import { Check, Loader2, X } from "lucide-react";

import { Panel, SectionTitle } from "@/components/ui/panel";
import { cn } from "@/lib/cn";
import { isPaused, LIFECYCLE, statusMeta } from "@/lib/trace";

const LABEL: Record<(typeof LIFECYCLE)[number], string> = {
  LOADING: "Loaded",
  OPTIONS_SENT: "Options sent (RCS)",
  EXECUTED: "Rescheduled",
  QUOTE_BUILT: "Quote built",
  ORDER_CREATED: "Order created",
  PAYMENT_PENDING: "Payment sent",
  VERIFIED: "Verified",
  CLOSED: "Closed",
};

// Where a given status sits on the milestone track.
const REACHED: Record<string, number> = {
  LOADING: 0,
  AWAITING_APPROVAL: 1,
  PAUSED: 1,
  OPTIONS_SENT: 1,
  EXECUTED: 2,
  QUOTE_BUILT: 3,
  AWAITING_QUOTE_APPROVAL: 3,
  ORDER_CREATED: 4,
  PAYMENT_PENDING: 5,
  PAID: 6,
  VERIFIED: 6,
  CLOSED: 7,
};

export function StatusTimeline({ status }: { status: string }) {
  const rejected = status === "REJECTED";
  const reached = REACHED[status] ?? 0;
  const paused = isPaused(status);
  const meta = statusMeta(status);

  return (
    <Panel className="p-4">
      <SectionTitle className="mb-3">lifecycle</SectionTitle>
      <ol className="space-y-0">
        {LIFECYCLE.map((step, i) => {
          const done = !rejected && i < reached;
          const current = !rejected && i === reached;
          const last = i === LIFECYCLE.length - 1;
          return (
            <li key={step} className="flex gap-3">
              <div className="flex flex-col items-center">
                <span
                  className={cn(
                    "flex h-5 w-5 shrink-0 items-center justify-center rounded-full border text-[10px] transition-colors",
                    done && "border-ok/40 bg-ok/15 text-ok",
                    current && !paused && "border-accent bg-accent/15 text-accent",
                    current && paused && "border-warn bg-warn/15 text-warn",
                    !done && !current && "border-border bg-surface text-faint",
                  )}
                >
                  {done ? (
                    <Check className="h-3 w-3" />
                  ) : current && paused ? (
                    <Loader2 className="h-3 w-3 animate-spin" />
                  ) : (
                    <span className="font-mono">{i + 1}</span>
                  )}
                </span>
                {!last && (
                  <span className={cn("my-0.5 h-5 w-px", i < reached ? "bg-ok/40" : "bg-border")} />
                )}
              </div>
              <div className={cn("pb-2 pt-0.5", last && "pb-0")}>
                <div
                  className={cn(
                    "text-xs",
                    done && "text-muted",
                    current && "font-semibold text-fg",
                    !done && !current && "text-faint",
                  )}
                >
                  {LABEL[step]}
                </div>
                {current && paused && (
                  <div className="font-mono text-[10px] text-warn">waiting — {meta.label.toLowerCase()}</div>
                )}
              </div>
            </li>
          );
        })}
      </ol>
      {rejected && (
        <div className="mt-2 flex items-center gap-2 rounded border border-risk/30 bg-risk/10 px-3 py-2 text-xs text-risk">
          <X className="h-3.5 w-3.5" /> Rejected by operator
        </div>
      )}
    </Panel>
  );
}
