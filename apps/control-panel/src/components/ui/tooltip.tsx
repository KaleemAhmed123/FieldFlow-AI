import * as T from "@radix-ui/react-tooltip";
import type { ReactNode } from "react";

import { cn } from "@/lib/cn";

export const TooltipProvider = T.Provider;

/** Convenience: wrap any element to give it a tooltip. */
export function Tip({
  label,
  children,
  side = "top",
  className,
}: {
  label: ReactNode;
  children: ReactNode;
  side?: "top" | "right" | "bottom" | "left";
  className?: string;
}) {
  return (
    <T.Root>
      <T.Trigger asChild>{children}</T.Trigger>
      <T.Portal>
        <T.Content
          side={side}
          sideOffset={6}
          className={cn(
            "z-50 max-w-xs rounded border border-border bg-overlay px-2.5 py-1.5 text-xs text-fg shadow-pop",
            "animate-fade-in",
            className,
          )}
        >
          {label}
          <T.Arrow className="fill-border" />
        </T.Content>
      </T.Portal>
    </T.Root>
  );
}
