import { Clock, Cpu, Package, User, Wrench } from "lucide-react";
import type { ReactNode } from "react";

import { ApprovalActions } from "@/components/ApprovalActions";
import { DecisionTrace } from "@/components/DecisionTrace";
import { RcsCardPreview } from "@/components/RcsCardPreview";
import { StatusTimeline } from "@/components/StatusTimeline";
import { Badge } from "@/components/ui/badge";
import type { CaseRow } from "@/lib/api";
import { useSim } from "@/hooks/useSim";
import { confidencePct, eventReason, humanize, statusMeta, timeAgo } from "@/lib/trace";

function Meta({ icon, label, value }: { icon: ReactNode; label: string; value?: ReactNode }) {
  if (value === undefined || value === null || value === "") return null;
  return (
    <div className="flex items-center gap-1.5">
      <span className="text-faint">{icon}</span>
      <span className="font-mono text-[10px] uppercase tracking-wide text-faint">{label}</span>
      <span className="text-xs text-fg">{value}</span>
    </div>
  );
}

export function CaseDetail({ c }: { c?: CaseRow }) {
  const sim = useSim();

  if (!c) {
    return (
      <div className="flex h-full items-center justify-center p-8">
        <div className="max-w-sm text-center">
          <Cpu className="mx-auto mb-3 h-8 w-8 text-faint" />
          <p className="text-sm text-muted">Select a case to inspect its decision trace.</p>
          <p className="mt-1 font-mono text-[11px] text-faint">
            AI proposes · policy decides · a human approves risk · RCS is the control plane
          </p>
        </div>
      </div>
    );
  }

  const meta = statusMeta(c.status);
  const pct = confidencePct(c.decisionTrace);
  const reason = humanize(eventReason(c.decisionTrace));
  const ctx = c.context ?? {};
  const version = c.version ?? 1;
  const quotePaise = c.decisionTrace?.commerce?.quote?.amountPaise;

  return (
    <div className="flex h-full min-h-0 flex-col">
      {/* case header */}
      <div className="shrink-0 border-b border-border px-5 py-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2.5">
            <h1 className="font-mono text-base font-semibold text-fg">{c.correlationId}</h1>
            <Badge tone={meta.tone}>{meta.label}</Badge>
            {reason && (
              <span className="font-mono text-[11px] uppercase tracking-wide text-faint">{reason}</span>
            )}
          </div>
          <div className="flex items-center gap-3">
            {pct !== null && (
              <span className="font-mono text-xs text-muted">
                conf <span className="text-fg">{pct}%</span>
              </span>
            )}
            <span className="flex items-center gap-1 font-mono text-[11px] text-faint">
              <Clock className="h-3 w-3" /> {timeAgo(c.updatedAt)}
            </span>
          </div>
        </div>
        <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1">
          <Meta icon={<User className="h-3 w-3" />} label="cust" value={ctx.customer?.name} />
          <Meta
            icon={<Package className="h-3 w-3" />}
            label="asset"
            value={
              ctx.asset?.model && (
                <>
                  {ctx.asset.model}{" "}
                  <span className={ctx.asset.warranty === "active" ? "text-ok" : "text-warn"}>
                    ({ctx.asset.warranty})
                  </span>
                </>
              )
            }
          />
          <Meta icon={<Wrench className="h-3 w-3" />} label="tech" value={ctx.technician?.name} />
          <Meta
            icon={<Clock className="h-3 w-3" />}
            label="sla"
            value={ctx.slaWindowMinutes ? `${ctx.slaWindowMinutes}m` : undefined}
          />
        </div>
      </div>

      {/* body */}
      <div className="min-h-0 flex-1 space-y-4 overflow-y-auto p-5">
        <ApprovalActions
          status={c.status}
          quoteAmountPaise={quotePaise}
          pending={sim.approve.isPending}
          onDecide={(approved) => sim.approve.mutate({ correlationId: c.correlationId, approved })}
        />

        <div className="grid gap-4 xl:grid-cols-[1fr_300px]">
          <DecisionTrace trace={c.decisionTrace} />
          <div className="space-y-4">
            <RcsCardPreview
              card={c.sentCard}
              busy={sim.customerReply.isPending}
              onPickSlot={(slotId) =>
                sim.customerReply.mutate({ correlationId: c.correlationId, slotId, version })
              }
            />
            <StatusTimeline status={c.status} />
          </div>
        </div>
      </div>
    </div>
  );
}
