import { Eye, Zap } from "lucide-react";

import { ScrollArea } from "@/components/ui/scroll-area";
import { useTools } from "@/hooks/useOps";
import type { ToolInfo } from "@/lib/api";

function ToolRow({ t, action }: { t: ToolInfo; action: boolean }) {
  return (
    <li className="rounded border border-border bg-surface px-2.5 py-2">
      <div className="flex items-center gap-2">
        <span className="truncate font-mono text-[11px] text-fg">{t.name}</span>
        {t.args.length > 0 && (
          <span className="shrink-0 font-mono text-[9px] text-faint">({t.args.join(", ")})</span>
        )}
      </div>
      <p className="mt-0.5 text-[11px] leading-snug text-muted">{t.description}</p>
      {action && (
        <p className="mt-0.5 font-mono text-[9px] uppercase tracking-wide text-warn">
          runs the ladder · may refuse
        </p>
      )}
    </li>
  );
}

export function ToolsSurface() {
  const { data, isError } = useTools();

  if (isError) return <p className="p-3 font-mono text-[11px] text-faint">/tools unavailable</p>;
  if (!data) return <p className="p-3 font-mono text-[11px] text-faint">loading tools…</p>;

  return (
    <ScrollArea className="h-full">
      <div className="space-y-4 p-1">
        <section className="space-y-2">
          <div className="flex items-center gap-1.5 text-muted">
            <Eye className="h-3.5 w-3.5" />
            <h3 className="font-mono text-[11px] font-semibold uppercase tracking-wide">
              reads <span className="text-faint">({data.reads.length})</span>
            </h3>
          </div>
          <ul className="space-y-1.5">
            {data.reads.map((t) => (
              <ToolRow key={t.name} t={t} action={false} />
            ))}
          </ul>
        </section>
        <section className="space-y-2">
          <div className="flex items-center gap-1.5 text-warn">
            <Zap className="h-3.5 w-3.5" />
            <h3 className="font-mono text-[11px] font-semibold uppercase tracking-wide">
              actions <span className="text-faint">({data.actions.length})</span>
            </h3>
          </div>
          <ul className="space-y-1.5">
            {data.actions.map((t) => (
              <ToolRow key={t.name} t={t} action />
            ))}
          </ul>
        </section>
        <p className="px-1 text-[10px] leading-snug text-faint">{data.note}</p>
      </div>
    </ScrollArea>
  );
}
