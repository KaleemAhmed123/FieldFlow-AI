import { useEffect, useState } from "react";

import { CaseDetail } from "@/components/CaseDetail";
import { CaseList } from "@/components/CaseList";
import { OpsDock } from "@/components/OpsDock";
import { TopBar } from "@/components/TopBar";
import { TooltipProvider } from "@/components/ui/tooltip";
import { useLiveCases } from "@/hooks/useLiveCases";
import { statusMeta } from "@/lib/trace";

export default function App() {
  const { data: cases = [], isLoading } = useLiveCases();
  const [selectedId, setSelectedId] = useState<string | null>(null);

  // Auto-select the most recent case so the stage never sits empty on load.
  useEffect(() => {
    if (!selectedId && cases.length > 0) setSelectedId(cases[0].correlationId);
  }, [cases, selectedId]);

  const selected = cases.find((c) => c.correlationId === selectedId);
  const activeStage = selected ? statusMeta(selected.status).stage : undefined;

  return (
    <TooltipProvider delayDuration={200}>
      <div className="flex h-screen flex-col overflow-hidden bg-bg text-fg">
        <TopBar activeStage={activeStage} />

        <div className="min-h-0 flex-1 overflow-y-auto xl:overflow-hidden">
          <div className="xl:grid xl:h-full xl:grid-cols-[300px_1fr_360px]">
            <aside className="h-72 border-b border-border bg-surface/40 xl:h-full xl:border-b-0 xl:border-r">
              <CaseList
                cases={cases}
                selectedId={selectedId}
                onSelect={setSelectedId}
                loading={isLoading}
              />
            </aside>

            <main className="h-[76vh] xl:h-full">
              <CaseDetail c={selected} />
            </main>

            <aside className="border-t border-border bg-surface/40 xl:h-full xl:border-l xl:border-t-0">
              <div className="h-[80vh] xl:h-full">
                <OpsDock selected={selected} />
              </div>
            </aside>
          </div>
        </div>
      </div>
    </TooltipProvider>
  );
}
