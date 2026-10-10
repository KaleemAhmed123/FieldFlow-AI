import { NextResponse } from "next/server";
import { listProducts } from "@/lib/supabase";

export const dynamic = "force-dynamic"; // always live stock, never a cached build snapshot

// GET /api/products — every product with image + price + per-location stock. Used by the dashboard
// and the MCP list_products tool.
export async function GET() {
  try {
    return NextResponse.json({ products: await listProducts() });
  } catch (err) {
    return NextResponse.json({ error: String((err as Error).message ?? err) }, { status: 500 });
  }
}
