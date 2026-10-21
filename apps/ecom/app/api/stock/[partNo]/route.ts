import { NextResponse } from "next/server";
import { priceFor, stockFor } from "@/lib/supabase";

export const dynamic = "force-dynamic";

// GET /api/stock/:partNo — the orchestrator's RestInventory contract:
//   { partNo, locations: [{ location, qty }], pricePaise }
// find_part reads locations; price_paise reads pricePaise (the quote's price authority).
export async function GET(_req: Request, { params }: { params: Promise<{ partNo: string }> }) {
  const { partNo } = await params;
  try {
    const [locations, pricePaise] = await Promise.all([stockFor(partNo), priceFor(partNo)]);
    return NextResponse.json({ partNo, locations, pricePaise });
  } catch (err) {
    return NextResponse.json({ error: String((err as Error).message ?? err) }, { status: 500 });
  }
}
