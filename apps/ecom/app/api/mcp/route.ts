import { createMcpHandler } from "mcp-handler";
import { z } from "zod";
import { listProducts, stockFor } from "@/lib/supabase";

// The e-com MCP (Model Context Protocol) server — a standard way an AI copilot calls our tools.
// READ-ONLY by design: the admin copilot may look up products + stock, but the guardrail holds —
// reserve/set-stock are NOT exposed here. Inventory mutations go through the deterministic pipeline
// (orchestrator -> /api/reserve) or a human-confirmed admin action, never an LLM-invoked MCP write.
//
// Endpoint: POST/GET /api/mcp  (Streamable HTTP). The copilot (build step #4) is the consumer.

const handler = createMcpHandler((server) => {
  server.registerTool(
    "list_products",
    {
      title: "List products",
      description: "List every serviceable part: part number, model, price (paise) and live stock.",
      inputSchema: z.object({}),
    },
    async () => {
      const products = await listProducts();
      return { content: [{ type: "text", text: JSON.stringify(products) }] };
    },
  );

  server.registerTool(
    "get_stock",
    {
      title: "Get stock",
      description: "Live stock of one part across locations.",
      inputSchema: z.object({ partNo: z.string().describe("Part number, e.g. PCB-492") }),
    },
    async ({ partNo }) => {
      const locations = await stockFor(partNo);
      return { content: [{ type: "text", text: JSON.stringify({ partNo, locations }) }] };
    },
  );
});

export { handler as GET, handler as POST };
