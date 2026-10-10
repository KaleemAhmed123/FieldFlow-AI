import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "FieldFlow Inventory",
  description: "E-com inventory source — product image, price and live stock. Admin only.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
