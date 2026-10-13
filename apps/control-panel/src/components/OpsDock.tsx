import { BarChart3, Bot, SlidersHorizontal, Wrench } from "lucide-react";

import { CopilotChat } from "@/components/CopilotChat";
import { FailureDeck } from "@/components/FailureDeck";
import { MetricsStrip } from "@/components/MetricsStrip";
import { ToolsSurface } from "@/components/ToolsSurface";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import type { CaseRow } from "@/lib/api";

export function OpsDock({ selected }: { selected?: CaseRow }) {
  return (
    <div className="flex h-full min-h-0 flex-col">
      <Tabs defaultValue="sim" className="flex h-full min-h-0 flex-col">
        <div className="shrink-0 border-b border-border p-3">
          <TabsList className="w-full">
            <TabsTrigger value="sim" className="flex-1">
              <SlidersHorizontal className="mr-1 h-3 w-3" /> Simulate
            </TabsTrigger>
            <TabsTrigger value="tools" className="flex-1">
              <Wrench className="mr-1 h-3 w-3" /> Tools
            </TabsTrigger>
            <TabsTrigger value="metrics" className="flex-1">
              <BarChart3 className="mr-1 h-3 w-3" /> Metrics
            </TabsTrigger>
            <TabsTrigger value="copilot" className="flex-1">
              <Bot className="mr-1 h-3 w-3" /> Copilot
            </TabsTrigger>
          </TabsList>
        </div>

        <TabsContent value="sim" className="min-h-0 flex-1">
          <ScrollArea className="h-full">
            <div className="p-3">
              <FailureDeck selected={selected} />
            </div>
          </ScrollArea>
        </TabsContent>

        <TabsContent value="tools" className="min-h-0 flex-1">
          <div className="h-full p-3">
            <ToolsSurface />
          </div>
        </TabsContent>

        <TabsContent value="metrics" className="min-h-0 flex-1">
          <ScrollArea className="h-full">
            <div className="p-3">
              <MetricsStrip />
            </div>
          </ScrollArea>
        </TabsContent>

        <TabsContent value="copilot" className="min-h-0 flex-1">
          <CopilotChat />
        </TabsContent>
      </Tabs>
    </div>
  );
}
