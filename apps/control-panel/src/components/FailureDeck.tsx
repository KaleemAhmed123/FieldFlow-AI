import { CreditCard, Inbox, PlayCircle, RotateCcw, ServerCrash, Siren, Zap } from "lucide-react";
import { type ReactNode, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { SectionTitle } from "@/components/ui/panel";
import { useDlq } from "@/hooks/useOps";
import { useSim } from "@/hooks/useSim";
import type { CaseRow, Reason } from "@/lib/api";

const REASONS: Reason[] = [
  "technician_delay",
  "traffic_weather",
  "technician_no_show",
  "customer_access_issue",
  "part_missing",
  "wrong_part_shipped",
  "additional_fault_found",
  "asset_complex",
  "safety_risk",
  "warranty_dispute",
];

function Block({ icon, title, children }: { icon: ReactNode; title: string; children: ReactNode }) {
  return (
    <section className="space-y-2 rounded-lg border border-border bg-surface p-3">
      <SectionTitle>
        <span className="inline-flex items-center gap-1.5 text-muted">
          {icon}
          {title}
        </span>
      </SectionTitle>
      {children}
    </section>
  );
}

const inputCls =
  "h-8 w-full rounded border border-border bg-bg px-2 font-mono text-xs text-fg focus:border-accent/50 focus:outline-none";

export function FailureDeck({ selected }: { selected?: CaseRow }) {
  const sim = useSim();
  const dlq = useDlq();
  const [reason, setReason] = useState<Reason>("technician_delay");
  const [workOrderId, setWorkOrderId] = useState("");
  const [lastEventId, setLastEventId] = useState<string | null>(null);
  const [muid, setMuid] = useState("msg-demo-1");
  const [sfDown, setSfDown] = useState(false);

  const fire = (eventId: string) => {
    setLastEventId(eventId);
    sim.fireAtRisk.mutate({
      reason,
      eventId,
      ...(workOrderId.trim() ? { workOrderId: workOrderId.trim() } : {}),
    });
  };

  const payPending = selected?.status === "PAYMENT_PENDING";

  return (
    <div className="space-y-3">
      <Block icon={<Zap className="h-3.5 w-3.5" />} title="fire at-risk">
        <select
          value={reason}
          onChange={(e) => setReason(e.target.value as Reason)}
          className={inputCls}
          aria-label="reason"
        >
          {REASONS.map((r) => (
            <option key={r} value={r}>
              {r}
            </option>
          ))}
        </select>
        <input
          value={workOrderId}
          onChange={(e) => setWorkOrderId(e.target.value)}
          placeholder="workOrderId (optional)"
          className={inputCls}
        />
        <div className="flex gap-2">
          <Button
            variant="accent"
            size="sm"
            className="flex-1"
            disabled={sim.fireAtRisk.isPending}
            onClick={() => fire(`evt_${Date.now()}`)}
          >
            <PlayCircle className="h-3.5 w-3.5" /> Fire
          </Button>
          <Button
            variant="outline"
            size="sm"
            disabled={!lastEventId || sim.fireAtRisk.isPending}
            onClick={() => lastEventId && fire(lastEventId)}
            title="re-send the same eventId to prove idempotency"
          >
            <RotateCcw className="h-3.5 w-3.5" /> Re-fire
          </Button>
        </div>
        <p className="font-mono text-[9px] text-faint">
          complex/safety/warranty pause for approval; part_missing runs the inventory race
        </p>
      </Block>

      {payPending && (
        <Block icon={<CreditCard className="h-3.5 w-3.5" />} title="payment">
          <p className="font-mono text-[10px] text-faint">targets {selected!.correlationId}</p>
          <Button
            variant="accent"
            size="sm"
            className="w-full"
            disabled={sim.payment.isPending}
            onClick={() =>
              sim.payment.mutate({
                correlationId: selected!.correlationId,
                status: "captured",
                eventId: `pay_${Date.now()}`,
              })
            }
          >
            Simulate payment captured
          </Button>
        </Block>
      )}

      <Block icon={<ServerCrash className="h-3.5 w-3.5" />} title="salesforce fault">
        <div className="flex items-center justify-between">
          <Badge tone={sfDown ? "risk" : "ok"}>{sfDown ? "DOWN" : "up"}</Badge>
          <Button
            variant={sfDown ? "default" : "danger"}
            size="sm"
            disabled={sim.fault.isPending}
            onClick={() => {
              const next = !sfDown;
              setSfDown(next);
              sim.fault.mutate({ salesforceDown: next });
            }}
          >
            {sfDown ? "Bring up" : "Knock down"}
          </Button>
        </div>
        <p className="font-mono text-[9px] text-faint">
          while down, a fired event fails processing and parks in the DLQ
        </p>
      </Block>

      <Block icon={<Inbox className="h-3.5 w-3.5" />} title="dead-letter queue">
        {dlq.data?.available === false ? (
          <p className="font-mono text-[10px] text-faint">{dlq.data.detail ?? "needs RabbitMQ"}</p>
        ) : (
          <>
            <div className="flex items-center justify-between">
              <span className="font-mono text-xs text-muted">
                depth <span className="text-fg">{dlq.data?.depth ?? 0}</span>
              </span>
              <Button
                variant="outline"
                size="sm"
                disabled={sim.replayDlq.isPending || (dlq.data?.depth ?? 0) === 0}
                onClick={() => sim.replayDlq.mutate()}
              >
                <RotateCcw className="h-3.5 w-3.5" /> Replay
              </Button>
            </div>
            {(dlq.data?.messages ?? []).slice(0, 3).map((m, i) => (
              <div key={i} className="truncate rounded bg-bg px-2 py-1 font-mono text-[9px] text-faint">
                {JSON.stringify(m)}
              </div>
            ))}
          </>
        )}
      </Block>

      <Block icon={<Siren className="h-3.5 w-3.5" />} title="delivery status → SMS fallback">
        <input value={muid} onChange={(e) => setMuid(e.target.value)} placeholder="messageUuid" className={inputCls} />
        <Button
          variant="outline"
          size="sm"
          className="w-full"
          disabled={sim.deliveryStatus.isPending || !muid.trim()}
          onClick={() => sim.deliveryStatus.mutate({ messageUuid: muid.trim(), status: "failed" })}
        >
          Mark undelivered → send SMS
        </Button>
        <p className="font-mono text-[9px] text-faint">
          a failed RCS delivery on a waiting case re-sends the options over SMS
        </p>
      </Block>
    </div>
  );
}
