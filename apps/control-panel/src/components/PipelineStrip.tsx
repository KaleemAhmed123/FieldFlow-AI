import { ChevronRight, Cpu, MessageSquare, Scale, UserCheck } from "lucide-react";
import type { LucideIcon } from "lucide-react";

import { cn } from "@/lib/cn";
import type { Stage } from "@/lib/trace";

// The one story, always on screen: AI proposes -> policy decides -> a human approves risk -> RCS is
// the customer control plane. When a case is selected we light the stages up to where it is.
const STAGES: Array<{ stage: Stage; label: string; sub: string; icon: LucideIcon }> = [
  { stage: "propose", label: "AI proposes", sub: "LLM + RAG", icon: Cpu },
  { stage: "decide", label: "Policy decides", sub: "deterministic", icon: Scale },
  { stage: "human", label: "Human approves", sub: "risk gate", icon: UserCheck },
  { stage: "customer", label: "RCS control", sub: "customer taps", icon: MessageSquare },
];

const ORDER: Stage[] = ["propose", "decide", "human", "customer", "done"];

export function PipelineStrip({ active }: { active?: Stage }) {
  const activeIdx = active ? ORDER.indexOf(active) : -1;
  return (
    <div className="flex items-center gap-1">
      {STAGES.map((s, i) => {
        const on = activeIdx >= 0 && (i <= activeIdx || active === "done");
        const Icon = s.icon;
        return (
          <div key={s.stage} className="flex items-center gap-1">
            <div
              className={cn(
                "flex items-center gap-2 rounded border px-2.5 py-1 transition-colors duration-200",
                on
                  ? "border-accent/40 bg-accent/10 text-accent"
                  : "border-border bg-surface text-faint",
              )}
            >
              <Icon className="h-3.5 w-3.5 shrink-0" />
              <div className="leading-tight">
                <div className="text-[11px] font-semibold">{s.label}</div>
                <div className="font-mono text-[9px] uppercase tracking-wider opacity-70">{s.sub}</div>
              </div>
            </div>
            {i < STAGES.length - 1 && (
              <ChevronRight className={cn("h-3.5 w-3.5 shrink-0", on ? "text-accent/60" : "text-faint/50")} />
            )}
          </div>
        );
      })}
    </div>
  );
}
