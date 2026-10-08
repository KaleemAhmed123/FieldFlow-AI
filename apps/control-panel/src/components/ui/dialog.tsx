import * as D from "@radix-ui/react-dialog";
import { X } from "lucide-react";
import { forwardRef, type ReactNode } from "react";

import { cn } from "@/lib/cn";

export const Dialog = D.Root;
export const DialogTrigger = D.Trigger;

export const DialogContent = forwardRef<
  React.ElementRef<typeof D.Content>,
  React.ComponentPropsWithoutRef<typeof D.Content> & { title?: ReactNode }
>(({ className, children, title, ...props }, ref) => (
  <D.Portal>
    <D.Overlay className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm animate-fade-in" />
    <D.Content
      ref={ref}
      className={cn(
        "fixed left-1/2 top-1/2 z-50 w-[min(92vw,720px)] max-h-[85vh] -translate-x-1/2 -translate-y-1/2",
        "overflow-hidden rounded-lg border border-border bg-surface shadow-pop animate-fade-in",
        className,
      )}
      {...props}
    >
      <div className="flex items-center justify-between border-b border-border px-4 py-3">
        <D.Title className="font-mono text-xs font-semibold uppercase tracking-wide text-fg">
          {title}
        </D.Title>
        <D.Close className="rounded p-1 text-muted hover:bg-surface2 hover:text-fg focus-visible:outline-none">
          <X className="h-4 w-4" />
        </D.Close>
      </div>
      {children}
    </D.Content>
  </D.Portal>
));
DialogContent.displayName = "DialogContent";
