import { NextResponse } from "next/server";
import { reserve } from "@/lib/supabase";

// POST /api/reserve { partNo, qty? } — the orchestrator's RestInventory.reserve contract.
// Atomic on the DB side: a lost race returns { ok: false } (a refusal, not an oversell — NFR-5).
export async function POST(req: Request) {
  try {
    const body = await req.json();
    const partNo = String(body?.partNo ?? "");
    const qty = Number.isFinite(body?.qty) ? Math.trunc(body.qty) : 1;
    if (!partNo || qty < 1) {
      return NextResponse.json({ error: "partNo required, qty >= 1" }, { status: 400 });
    }
    return NextResponse.json({ ok: await reserve(partNo, qty) });
  } catch (err) {
    return NextResponse.json({ error: String((err as Error).message ?? err) }, { status: 500 });
  }
}
