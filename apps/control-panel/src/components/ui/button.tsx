import { Slot } from "@radix-ui/react-slot";
import { type ButtonHTMLAttributes, forwardRef } from "react";

import { cn } from "@/lib/cn";

type Variant = "default" | "accent" | "outline" | "ghost" | "danger";
type Size = "sm" | "md" | "icon";

const base =
  "inline-flex items-center justify-center gap-2 rounded font-medium whitespace-nowrap " +
  "transition-[background-color,color,transform,border-color,filter] duration-150 active:scale-[0.98] " +
  "disabled:opacity-50 disabled:pointer-events-none focus-visible:outline-none " +
  "focus-visible:ring-2 focus-visible:ring-accent/50";

const variants: Record<Variant, string> = {
  default: "bg-surface2 text-fg border border-border hover:bg-overlay",
  accent: "bg-accent text-accent-fg hover:brightness-110",
  outline: "border border-border text-fg hover:bg-surface2",
  ghost: "text-muted hover:text-fg hover:bg-surface2",
  danger: "bg-risk/15 text-risk border border-risk/30 hover:bg-risk/25",
};

const sizes: Record<Size, string> = {
  sm: "h-7 px-2.5 text-xs",
  md: "h-9 px-3.5 text-sm",
  icon: "h-8 w-8 shrink-0",
};

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  asChild?: boolean;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant = "default", size = "md", asChild, ...props }, ref) => {
    const Comp = asChild ? Slot : "button";
    return <Comp ref={ref} className={cn(base, variants[variant], sizes[size], className)} {...props} />;
  },
);
Button.displayName = "Button";
