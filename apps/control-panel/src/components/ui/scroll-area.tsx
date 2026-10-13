import * as S from "@radix-ui/react-scroll-area";
import { forwardRef } from "react";

import { cn } from "@/lib/cn";

export const ScrollArea = forwardRef<
  React.ElementRef<typeof S.Root>,
  React.ComponentPropsWithoutRef<typeof S.Root>
>(({ className, children, type = "auto", ...props }, ref) => (
  // type="auto" (not Radix's default "hover") so the scrollbar is always visible when content
  // overflows — people couldn't tell panes were scrollable when the bar only showed on hover.
  <S.Root ref={ref} type={type} className={cn("overflow-hidden", className)} {...props}>
    <S.Viewport className="h-full w-full [&>div]:!block">{children}</S.Viewport>
    <S.Scrollbar
      orientation="vertical"
      className="flex w-2.5 touch-none select-none bg-surface/40 p-0.5 transition-colors"
    >
      <S.Thumb className="relative flex-1 rounded-full bg-muted hover:bg-fg/70" />
    </S.Scrollbar>
    <S.Scrollbar
      orientation="horizontal"
      className="flex h-2.5 touch-none select-none bg-surface/40 p-0.5 transition-colors"
    >
      <S.Thumb className="relative flex-1 rounded-full bg-muted hover:bg-fg/70" />
    </S.Scrollbar>
    <S.Corner />
  </S.Root>
));
ScrollArea.displayName = "ScrollArea";
