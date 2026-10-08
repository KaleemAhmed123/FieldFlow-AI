import { Activity, FlaskConical, Radio } from "lucide-react";

import { PipelineStrip } from "@/components/PipelineStrip";
import { ThemeToggle } from "@/components/ThemeToggle";
import { Badge, Dot } from "@/components/ui/badge";
import { Tip } from "@/components/ui/tooltip";
import { useHealth } from "@/hooks/useOps";
import { USE_FIXTURES } from "@/lib/api";
import type { Stage } from "@/lib/trace";

export function TopBar({ activeStage }: { activeStage?: Stage }) {
  const health = useHealth();
  const online = !health.isError && health.data?.status === "ok";

  return (
    <header className="flex h-14 shrink-0 items-center justify-between gap-4 border-b border-border bg-surface/80 px-4 backdrop-blur">
      <div className="flex items-center gap-3">
        <div className="flex h-7 w-7 items-center justify-center rounded bg-accent/15 text-accent">
          <Radio className="h-4 w-4" />
        </div>
        <div className="leading-tight">
          <div className="font-mono text-sm font-semibold tracking-tight text-fg">
            FieldFlow<span className="text-accent"> // </span>
            <span className="text-muted">control center</span>
          </div>
          <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-faint">
            AI field-service recovery
          </div>
        </div>
      </div>

      <div className="hidden min-[1200px]:block">
        <PipelineStrip active={activeStage} />
      </div>

      <div className="flex items-center gap-2">
        {USE_FIXTURES ? (
          <Tip label="Serving captured fixtures — no backend needed">
            <span>
              <Badge tone="warn">
                <FlaskConical className="h-3 w-3" /> Fixtures
              </Badge>
            </span>
          </Tip>
        ) : (
          <Tip label={online ? "Orchestrator reachable" : "Orchestrator unreachable — is make dev up?"}>
            <span>
              <Badge tone={online ? "ok" : "risk"}>
                <Dot tone={online ? "ok" : "risk"} pulse={online} />
                {online ? "Live" : "Offline"}
              </Badge>
            </span>
          </Tip>
        )}
        <Tip label="Polling /cases every 1.5s">
          <span className="hidden items-center gap-1 font-mono text-[10px] uppercase tracking-wider text-faint sm:flex">
            <Activity className="h-3 w-3" /> poll 1.5s
          </span>
        </Tip>
        <ThemeToggle />
      </div>
    </header>
  );
}
