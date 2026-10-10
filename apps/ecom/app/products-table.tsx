"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import type { Product } from "@/lib/supabase";

const rupees = (paise: number) => `₹${(paise / 100).toLocaleString("en-IN")}`;

export function ProductsTable({ products }: { products: Product[] }) {
  const router = useRouter();
  const [busy, setBusy] = useState<string | null>(null);

  async function setStock(partNo: string, qty: number) {
    setBusy(partNo);
    try {
      const res = await fetch("/api/stock", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ partNo, qty }),
      });
      if (!res.ok) alert((await res.json()).error ?? "failed");
      router.refresh(); // re-fetch the server component's live stock
    } finally {
      setBusy(null);
    }
  }

  return (
    <table>
      <thead>
        <tr>
          <th></th>
          <th>Part</th>
          <th>Price</th>
          <th>Stock</th>
          <th>Set</th>
        </tr>
      </thead>
      <tbody>
        {products.map((p) => (
          <Row key={p.partNo} p={p} busy={busy === p.partNo} onSet={setStock} />
        ))}
      </tbody>
    </table>
  );
}

function Row({
  p,
  busy,
  onSet,
}: {
  p: Product;
  busy: boolean;
  onSet: (partNo: string, qty: number) => void;
}) {
  const [qty, setQty] = useState(p.totalQty);
  return (
    <tr>
      <td>
        {/* plain <img>: placeholder tiles, no next/image optimisation needed for an admin tool */}
        <img className="thumb" src={p.imageUrl} alt={p.brand} />
      </td>
      <td>
        <div className="part">
          {p.partNo} {p.scarce && <span className="scarce">· scarce</span>}
        </div>
        <div className="model">
          {p.name} — {p.modelName}
        </div>
      </td>
      <td>{rupees(p.pricePaise)}</td>
      <td>
        <span className={p.totalQty === 0 ? "zero" : undefined}>{p.totalQty}</span>{" "}
        <span className="loc">
          ({p.locations.map((l) => `${l.location}:${l.qty}`).join(" ")})
        </span>
      </td>
      <td>
        <input
          type="number"
          min={0}
          value={qty}
          onChange={(e) => setQty(Math.max(0, Number(e.target.value)))}
        />{" "}
        <button disabled={busy} onClick={() => onSet(p.partNo, qty)}>
          Set
        </button>{" "}
        <button className="grab" disabled={busy} onClick={() => onSet(p.partNo, 0)}>
          Grab
        </button>
      </td>
    </tr>
  );
}
