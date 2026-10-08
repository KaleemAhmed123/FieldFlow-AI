import type { ReactNode } from "react";

import { cn } from "@/lib/cn";

/** A flat surface card — the base container for every grouped block. */
export function Panel({ className, children }: { className?: string; children: ReactNode }) {
  return <div className={cn("rounded-lg border border-border bg-surface", className)}>{children}</div>;
}

/** Small uppercase section label with an optional right-side slot. */
export function SectionTitle({
  children,
  right,
  className,
}: {
  children: ReactNode;
  right?: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("flex items-center justify-between gap-2", className)}>
      <h3 className="font-mono text-[11px] font-semibold uppercase tracking-[0.12em] text-faint">
        {children}
      </h3>
      {right}
    </div>
  );
}
