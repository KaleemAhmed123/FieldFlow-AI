import type { ReactNode } from "react";

import { cn } from "@/lib/cn";
import type { Tone } from "@/lib/trace";

const toneClasses: Record<Tone, string> = {
  accent: "bg-accent/15 text-accent border-accent/30",
  ok: "bg-ok/15 text-ok border-ok/30",
  warn: "bg-warn/15 text-warn border-warn/30",
  risk: "bg-risk/15 text-risk border-risk/30",
  info: "bg-info/15 text-info border-info/30",
  muted: "bg-surface2 text-muted border-border",
};

export function Badge({
  tone = "muted",
  mono,
  className,
  children,
}: {
  tone?: Tone;
  mono?: boolean;
  className?: string;
  children: ReactNode;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded border px-2 py-0.5 text-[11px] font-medium uppercase tracking-wide",
        toneClasses[tone],
        mono && "font-mono tracking-normal normal-case",
        className,
      )}
    >
      {children}
    </span>
  );
}

/** A small pulsing status dot in a tone. */
export function Dot({ tone = "muted", pulse }: { tone?: Tone; pulse?: boolean }) {
  const color: Record<Tone, string> = {
    accent: "bg-accent",
    ok: "bg-ok",
    warn: "bg-warn",
    risk: "bg-risk",
    info: "bg-info",
    muted: "bg-faint",
  };
  return (
    <span className={cn("inline-block h-2 w-2 rounded-full", color[tone], pulse && "animate-pulse-dot")} />
  );
}
