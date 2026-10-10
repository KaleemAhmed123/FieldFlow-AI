// Seed the e-com Supabase tables from the orchestrator's catalog.json — the single source of truth
// (Decision A). Idempotent: re-running wipes stock and re-upserts products, so it's safe to re-seed.
//
//   cd apps/ecom && npm run seed        (loads .env.local automatically)
//
// Stock rules mirror the orchestrator's app/data/catalog.py exactly, so FakeInventory (offline) and
// the real e-com start from the same world: scarce = 1 (fires the NFR-5 race), consumable = 8,
// everything else = 3; a second location "Delhi" seeded at 0 to make "stock elsewhere" visible.

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";
import { createClient } from "@supabase/supabase-js";

const __dirname = dirname(fileURLToPath(import.meta.url));

// --- tiny .env.local loader (no dependency) ---
try {
  const env = readFileSync(resolve(__dirname, "../.env.local"), "utf8");
  for (const line of env.split("\n")) {
    const m = line.match(/^\s*([A-Z0-9_]+)\s*=\s*(.*)\s*$/i);
    if (m && !process.env[m[1]]) process.env[m[1]] = m[2].replace(/^["']|["']$/g, "");
  }
} catch {
  /* no .env.local — rely on the ambient env (e.g. node --env-file or CI secrets) */
}

const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
const key = process.env.SUPABASE_SERVICE_ROLE_KEY;
if (!url || !key) {
  console.error("Set NEXT_PUBLIC_SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY in apps/ecom/.env.local");
  process.exit(1);
}
const sb = createClient(url, key, { auth: { persistSession: false } });

const SCARCE_QTY = 1;
const CONSUMABLE_QTY = 8;
const DEFAULT_QTY = 3;
const CATEGORY_COLOR = {
  "air-conditioner": "0ea5e9",
  refrigerator: "6366f1",
  "washing-machine": "10b981",
  microwave: "f59e0b",
  television: "ef4444",
};

function seedQty(part) {
  if (part.scarce) return SCARCE_QTY;
  if (part.kind === "consumable") return CONSUMABLE_QTY;
  return DEFAULT_QTY;
}

function imageUrl(model) {
  const color = CATEGORY_COLOR[model.category] ?? "111827";
  return `https://placehold.co/300x200/${color}/f9fafb/png?text=${encodeURIComponent(model.brand)}`;
}

const catalogPath = resolve(__dirname, "../../orchestrator/app/data/catalog.json");
const catalog = JSON.parse(readFileSync(catalogPath, "utf8"));

const products = [];
const stock = [];
for (const model of catalog.models) {
  for (const p of model.parts) {
    products.push({
      part_no: p.partNo,
      name: p.name,
      kind: p.kind,
      model_id: model.modelId,
      model_name: model.name,
      brand: model.brand,
      category: model.category,
      price_paise: p.pricePaise,
      warranty_covered: !!p.warrantyCovered,
      scarce: !!p.scarce,
      image_url: imageUrl(model),
    });
    const qty = seedQty(p);
    stock.push({ part_no: p.partNo, location: "Noida", qty });
    stock.push({ part_no: p.partNo, location: "Delhi", qty: 0 });
  }
}

console.log(`Seeding ${products.length} products, ${stock.length} stock rows...`);

const up = await sb.from("ecom_products").upsert(products, { onConflict: "part_no" });
if (up.error) throw up.error;

// Reset stock to the seed world (delete-all then insert). `neq part_no ''` matches every row.
const del = await sb.from("ecom_stock").delete().neq("part_no", "");
if (del.error) throw del.error;
const ins = await sb.from("ecom_stock").insert(stock);
if (ins.error) throw ins.error;

console.log("Done. Scarce parts are at qty 1 (NFR-5 race armed).");
