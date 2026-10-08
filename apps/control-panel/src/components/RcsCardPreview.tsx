import { CreditCard, MessageSquare, Signal, Wifi } from "lucide-react";

import { Button } from "@/components/ui/button";
import type { Card } from "@/lib/api";

// A phone mock of what the customer sees over RCS — the "customer control plane". The carousel's
// slot buttons and the "Approve & Pay" button are live: they drive the same /sim resume the real
// webhook would. `busy` disables them while a tap is in flight.
export function RcsCardPreview({
  card,
  onPickSlot,
  busy,
}: {
  card?: Card | null;
  onPickSlot?: (slotId: string) => void;
  busy?: boolean;
}) {
  return (
    <div className="mx-auto w-full max-w-[280px]">
      <div className="overflow-hidden rounded-xl border border-border bg-bg shadow-soft">
        {/* phone status bar */}
        <div className="flex items-center justify-between bg-surface2 px-3 py-1.5 font-mono text-[9px] text-faint">
          <span>9:41</span>
          <span className="flex items-center gap-1">
            <Signal className="h-2.5 w-2.5" />
            <Wifi className="h-2.5 w-2.5" />
            RCS
          </span>
        </div>
        {/* agent header */}
        <div className="flex items-center gap-2 border-b border-border px-3 py-2">
          <div className="flex h-6 w-6 items-center justify-center rounded-full bg-accent/15 text-accent">
            <MessageSquare className="h-3 w-3" />
          </div>
          <div className="leading-tight">
            <div className="text-[11px] font-semibold text-fg">FieldFlow</div>
            <div className="font-mono text-[9px] text-faint">verified business</div>
          </div>
        </div>

        {/* message area */}
        <div className="min-h-[180px] space-y-2 bg-grid p-3">
          {!card ? (
            <div className="flex h-[160px] items-center justify-center">
              <p className="font-mono text-[10px] text-faint">no card sent yet</p>
            </div>
          ) : (
            <div className="animate-fade-in space-y-2 rounded-lg rounded-tl-sm border border-border bg-surface p-2.5">
              <p className="text-[11px] font-medium leading-snug text-fg">{card.title}</p>

              {card.kind === "payment" ? (
                <a href={card.payUrl ?? "#"} target="_blank" rel="noreferrer" className="block">
                  <Button variant="accent" size="sm" className="w-full" disabled={!card.payUrl}>
                    <CreditCard className="h-3.5 w-3.5" /> Approve &amp; Pay
                  </Button>
                </a>
              ) : (
                <div className="space-y-1.5">
                  {(card.options ?? []).map((o) => (
                    <button
                      key={o.slotId}
                      disabled={busy || !onPickSlot}
                      onClick={() => onPickSlot?.(o.slotId)}
                      className="w-full rounded border border-border bg-bg px-2.5 py-1.5 text-left transition-colors hover:border-accent/50 hover:bg-accent/5 disabled:opacity-50"
                    >
                      <div className="text-[11px] font-semibold text-fg">{o.label}</div>
                      <div className="font-mono text-[9px] text-faint">
                        {o.technician}
                        {o.note ? ` · ${o.note}` : ""}
                      </div>
                    </button>
                  ))}
                  {(card.options ?? []).length === 0 && (
                    <p className="font-mono text-[9px] text-faint">no options on this card</p>
                  )}
                </div>
              )}
            </div>
          )}
        </div>
      </div>
      <p className="mt-2 text-center font-mono text-[9px] uppercase tracking-wider text-faint">
        tap = /sim/customer-reply (offline twin of the RCS webhook)
      </p>
    </div>
  );
}
