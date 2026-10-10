import { NextResponse } from "next/server";
import { setStock } from "@/lib/supabase";

// POST /api/stock { partNo, qty } — the demo "grab part" knob (admin only). Forces total stock to
// one Noida row. Set qty 0 to simulate "another case grabbed the last part" and fire the NFR-5 race.
export async function POST(req: Request) {
  try {
    const body = await req.json();
    const partNo = String(body?.partNo ?? "");
    const qty = Number.isFinite(body?.qty) ? Math.trunc(body.qty) : -1;
    if (!partNo || qty < 0) {
      return NextResponse.json({ error: "partNo required, qty >= 0" }, { status: 400 });
    }
    await setStock(partNo, qty);
    return NextResponse.json({ ok: true, partNo, qty });
  } catch (err) {
    return NextResponse.json({ error: String((err as Error).message ?? err) }, { status: 500 });
  }
}
