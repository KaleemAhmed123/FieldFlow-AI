import { AlertTriangle, BookOpen, Braces, Scissors, Sparkles, Wrench } from "lucide-react";

import { ConfidenceMeter } from "@/components/ConfidenceMeter";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogTrigger } from "@/components/ui/dialog";
import { Panel, SectionTitle } from "@/components/ui/panel";
import { ScrollArea } from "@/components/ui/scroll-area";
import { cn } from "@/lib/cn";
import { type DecisionTrace as Trace, rupees, type Tone } from "@/lib/trace";

const POLICY_TONE: Record<string, Tone> = { APPROVED: "ok", PARTIAL: "warn", DENIED: "risk" };

function isAction(name: string): boolean {
  return (
    name.startsWith("commerce.") ||
    name.endsWith(".reserve") ||
    name.endsWith(".confirm")
  );
}

export function DecisionTrace({ trace }: { trace?: Trace }) {
  if (!trace) {
    return (
      <Panel className="flex items-center justify-center p-8 text-center">
        <p className="font-mono text-xs text-faint">no decision trace yet</p>
      </Panel>
    );
  }

  const policy = trace.policyResult ?? "—";
  const sources = trace.knowledgeSources ?? [];
  const tools = trace.toolsUsed ?? [];
  const removed = trace.removed ?? [];
  const reasons = trace.reason ?? [];
  const commerce = trace.commerce;

  return (
    <Panel className="overflow-hidden">
      {/* header */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border bg-surface2/40 px-4 py-3">
        <div className="flex items-center gap-2">
          <Sparkles className="h-4 w-4 text-accent" />
          <h2 className="text-sm font-semibold text-fg">Decision trace</h2>
          <span className="font-mono text-[10px] uppercase tracking-wider text-faint">show your work</span>
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          {trace.llmProvider && <Badge tone="info" mono>{trace.llmProvider}</Badge>}
          {trace.degraded && <Badge tone="warn">degraded</Badge>}
          <Badge tone={POLICY_TONE[policy] ?? "muted"}>policy {policy}</Badge>
          <Dialog>
            <DialogTrigger asChild>
              <Button variant="ghost" size="sm">
                <Braces className="h-3.5 w-3.5" /> raw
              </Button>
            </DialogTrigger>
            <DialogContent title="decision trace — raw json">
              <ScrollArea className="max-h-[70vh]">
                <pre className="whitespace-pre-wrap break-words p-4 font-mono text-[11px] leading-relaxed text-muted">
                  {JSON.stringify(trace, null, 2)}
                </pre>
              </ScrollArea>
            </DialogContent>
          </Dialog>
        </div>
      </div>

      <div className="space-y-5 p-4">
        {trace.rateLimitNote && (
          <div className="flex items-start gap-2 rounded border border-warn/30 bg-warn/10 px-3 py-2 text-xs text-warn">
            <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
            <span>{trace.rateLimitNote}</span>
          </div>
        )}

        {trace.explanation && (
          <p className="text-sm leading-relaxed text-fg">
            <span className="mr-2 font-mono text-[10px] uppercase tracking-wider text-accent">proposal</span>
            {trace.explanation}
          </p>
        )}

        <ConfidenceMeter breakdown={trace.confidenceBreakdown} confidence={trace.confidence} />

        {reasons.length > 0 && (
          <div className="space-y-1.5">
            <SectionTitle>why this decision</SectionTitle>
            <ul className="space-y-1">
              {reasons.map((r, i) => (
                <li key={i} className="flex items-start gap-2 font-mono text-[11px] text-muted">
                  <span className="mt-[3px] h-1 w-1 shrink-0 rounded-full bg-accent/70" />
                  <span className="break-words">{r}</span>
                </li>
              ))}
            </ul>
          </div>
        )}

        <div className="grid gap-5 md:grid-cols-2">
          {/* knowledge sources */}
          <div className="space-y-2">
            <SectionTitle>
              <span className="inline-flex items-center gap-1.5">
                <BookOpen className="h-3 w-3" /> knowledge cited ({sources.length})
              </span>
            </SectionTitle>
            {sources.length === 0 ? (
              <p className="font-mono text-[10px] text-faint">no passages retrieved</p>
            ) : (
              <ul className="space-y-2">
                {sources.map((s, i) => (
                  <li key={i} className="rounded border border-border bg-bg/50 p-2.5">
                    <div className="flex items-center justify-between gap-2">
                      <span className="truncate font-mono text-[11px] text-fg">{s.source}</span>
                      {typeof s.score === "number" && <Badge tone="info" mono>{s.score.toFixed(2)}</Badge>}
                    </div>
                    {s.locator && (
                      <div className="font-mono text-[10px] uppercase tracking-wide text-faint">{s.locator}</div>
                    )}
                    {s.snippet && <p className="mt-1 line-clamp-3 text-[11px] leading-snug text-muted">{s.snippet}</p>}
                  </li>
                ))}
              </ul>
            )}
          </div>

          {/* tools used */}
          <div className="space-y-2">
            <SectionTitle>
              <span className="inline-flex items-center gap-1.5">
                <Wrench className="h-3 w-3" /> tools used ({tools.length})
              </span>
            </SectionTitle>
            {tools.length === 0 ? (
              <p className="font-mono text-[10px] text-faint">none recorded</p>
            ) : (
              <div className="flex flex-wrap gap-1.5">
                {tools.map((t) => (
                  <span
                    key={t}
                    className={cn(
                      "inline-flex items-center gap-1 rounded border px-1.5 py-0.5 font-mono text-[10px]",
                      isAction(t)
                        ? "border-warn/30 bg-warn/10 text-warn"
                        : "border-border bg-surface2 text-muted",
                    )}
                    title={isAction(t) ? "action — runs the ladder, may refuse" : "read — safe lookup"}
                  >
                    {t}
                  </span>
                ))}
              </div>
            )}
            <p className="font-mono text-[9px] text-faint">
              <span className="text-warn">■</span> action (may refuse) · <span className="text-muted">■</span> read
            </p>
          </div>
        </div>

        {removed.length > 0 && (
          <div className="space-y-1.5">
            <SectionTitle>
              <span className="inline-flex items-center gap-1.5">
                <Scissors className="h-3 w-3" /> removed by policy ({removed.length})
              </span>
            </SectionTitle>
            <ul className="space-y-1">
              {removed.map((r, i) => (
                <li key={i} className="flex items-start gap-2 text-[11px] text-risk">
                  <span className="font-mono">{r.slotId}</span>
                  <span className="text-muted">— {r.reason}</span>
                </li>
              ))}
            </ul>
          </div>
        )}

        {commerce?.quote && (
          <div className="space-y-1.5">
            <SectionTitle>commerce</SectionTitle>
            <div className="flex flex-wrap items-center gap-x-4 gap-y-1 rounded border border-border bg-bg/50 px-3 py-2 font-mono text-[11px]">
              <span className="text-muted">
                quote <span className="text-fg">{rupees(commerce.quote.amountPaise)}</span>
              </span>
              {commerce.quote.partNo && (
                <span className="text-muted">
                  part <span className="text-fg">{commerce.quote.partNo}</span>
                </span>
              )}
              {commerce.order?.orderId && (
                <span className="text-muted">
                  order <span className="text-fg">{commerce.order.orderId}</span>
                </span>
              )}
              {commerce.payment?.status && (
                <Badge tone={commerce.payment.status === "captured" ? "ok" : "warn"}>
                  {commerce.payment.status}
                </Badge>
              )}
              <span className="text-faint">authority: price_book</span>
            </div>
          </div>
        )}
      </div>
    </Panel>
  );
}
