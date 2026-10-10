import { NextResponse } from "next/server";
import { stockFor } from "@/lib/supabase";

export const dynamic = "force-dynamic";

// GET /api/stock/:partNo — the orchestrator's RestInventory.find_part contract:
//   { partNo, locations: [{ location, qty }] }
export async function GET(_req: Request, { params }: { params: Promise<{ partNo: string }> }) {
  const { partNo } = await params;
  try {
    return NextResponse.json({ partNo, locations: await stockFor(partNo) });
  } catch (err) {
    return NextResponse.json({ error: String((err as Error).message ?? err) }, { status: 500 });
  }
}
