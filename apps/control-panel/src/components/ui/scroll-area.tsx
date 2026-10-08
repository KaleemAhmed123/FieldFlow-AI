import * as S from "@radix-ui/react-scroll-area";
import { forwardRef } from "react";

import { cn } from "@/lib/cn";

export const ScrollArea = forwardRef<
  React.ElementRef<typeof S.Root>,
  React.ComponentPropsWithoutRef<typeof S.Root>
>(({ className, children, ...props }, ref) => (
  <S.Root ref={ref} className={cn("overflow-hidden", className)} {...props}>
    <S.Viewport className="h-full w-full [&>div]:!block">{children}</S.Viewport>
    <S.Scrollbar
      orientation="vertical"
      className="flex w-2 touch-none select-none p-0.5 transition-colors"
    >
      <S.Thumb className="relative flex-1 rounded-full bg-border hover:bg-faint" />
    </S.Scrollbar>
    <S.Corner />
  </S.Root>
));
ScrollArea.displayName = "ScrollArea";
