import { createClient, type SupabaseClient } from "@supabase/supabase-js";

// Server-only Supabase client (service_role key → full read/write for the admin API + seed).
// Lazy + cached: env is read on first use, not at import, so `next build` works without creds set.
// NEVER import this into a client component — the service_role key must never reach the browser.

let _client: SupabaseClient | null = null;

export function getSupabase(): SupabaseClient {
  if (_client) return _client;
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const key = process.env.SUPABASE_SERVICE_ROLE_KEY;
  if (!url || !key) {
    throw new Error(
      "Supabase not configured: set NEXT_PUBLIC_SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY " +
        "in apps/ecom/.env.local (Supabase dashboard -> Settings -> API).",
    );
  }
  _client = createClient(url, key, { auth: { persistSession: false } });
  return _client;
}

export type StockRow = { location: string; qty: number };

export type Product = {
  partNo: string;
  name: string;
  kind: string;
  modelId: string;
  modelName: string;
  brand: string;
  category: string;
  pricePaise: number;
  warrantyCovered: boolean;
  scarce: boolean;
  imageUrl: string;
  locations: StockRow[];
  totalQty: number;
};

// One query for products + their stock, shaped for the dashboard and the API.
export async function listProducts(): Promise<Product[]> {
  const sb = getSupabase();
  const [{ data: products, error: pErr }, { data: stock, error: sErr }] = await Promise.all([
    sb.from("ecom_products").select("*").order("part_no"),
    sb.from("ecom_stock").select("part_no, location, qty"),
  ]);
  if (pErr) throw pErr;
  if (sErr) throw sErr;

  const byPart = new Map<string, StockRow[]>();
  for (const row of stock ?? []) {
    const list = byPart.get(row.part_no) ?? [];
    list.push({ location: row.location, qty: row.qty });
    byPart.set(row.part_no, list);
  }

  return (products ?? []).map((p) => {
    const locations = (byPart.get(p.part_no) ?? []).sort((a, b) =>
      a.location.localeCompare(b.location),
    );
    return {
      partNo: p.part_no,
      name: p.name,
      kind: p.kind,
      modelId: p.model_id,
      modelName: p.model_name,
      brand: p.brand,
      category: p.category,
      pricePaise: p.price_paise,
      warrantyCovered: p.warranty_covered,
      scarce: p.scarce,
      imageUrl: p.image_url,
      locations,
      totalQty: locations.reduce((n, l) => n + l.qty, 0),
    };
  });
}

export async function stockFor(partNo: string): Promise<StockRow[]> {
  const sb = getSupabase();
  const { data, error } = await sb
    .from("ecom_stock")
    .select("location, qty")
    .eq("part_no", partNo)
    .order("location");
  if (error) throw error;
  return (data ?? []).map((r) => ({ location: r.location, qty: r.qty }));
}

// Atomic reserve via the SQL function — the whole point is that a lost race returns false.
export async function reserve(partNo: string, qty: number): Promise<boolean> {
  const sb = getSupabase();
  const { data, error } = await sb.rpc("ecom_reserve", { p_part_no: partNo, p_qty: qty });
  if (error) throw error;
  return data === true;
}

// Demo knob: force total stock to one Noida row (mirrors FakeInventory.set_stock). Setting 0 is the
// "another case grabbed the last part" button that fires the NFR-5 race live in a demo.
export async function setStock(partNo: string, qty: number): Promise<void> {
  const sb = getSupabase();
  const del = await sb.from("ecom_stock").delete().eq("part_no", partNo);
  if (del.error) throw del.error;
  const ins = await sb.from("ecom_stock").insert({ part_no: partNo, location: "Noida", qty });
  if (ins.error) throw ins.error;
}
