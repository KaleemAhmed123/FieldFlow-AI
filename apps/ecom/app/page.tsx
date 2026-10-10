import { listProducts } from "@/lib/supabase";
import { ProductsTable } from "./products-table";

export const dynamic = "force-dynamic"; // always show live stock

export default async function Page() {
  let products;
  try {
    products = await listProducts();
  } catch (err) {
    return (
      <main>
        <h1>FieldFlow Inventory</h1>
        <p className="sub">E-com inventory source — admin</p>
        <div className="setup">
          <p>Not connected to Supabase yet.</p>
          <ol>
            <li>
              Copy <code>.env.example</code> → <code>.env.local</code> and fill{" "}
              <code>NEXT_PUBLIC_SUPABASE_URL</code> + <code>SUPABASE_SERVICE_ROLE_KEY</code>.
            </li>
            <li>
              Run <code>supabase/schema.sql</code> in the Supabase SQL editor.
            </li>
            <li>
              <code>npm run seed</code> to load products from the catalog.
            </li>
          </ol>
          <p className="sub">{String((err as Error).message ?? err)}</p>
        </div>
      </main>
    );
  }

  return (
    <main>
      <h1>FieldFlow Inventory</h1>
      <p className="sub">
        {products.length} parts · scarce parts sit at qty 1 · &quot;Grab&quot; drops stock to 0 to
        fire the inventory race (NFR-5)
      </p>
      <ProductsTable products={products} />
    </main>
  );
}
