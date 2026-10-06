import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

const TONES = {
  bone: "bg-bone text-ink-black",
  ink: "bg-ink-black text-paper-white",
};

type PillProps = {
  tone?: keyof typeof TONES;
  className?: string;
  children: ReactNode;
};

// Pill Badge: 13px/500, wide tracking, fully rounded.
export function Pill({ tone = "bone", className, children }: PillProps) {
  return (
    <span
      className={cn(
        "rounded-(--radius-tags) px-(--spacing-12) py-1 text-caption font-medium tracking-(--tracking-caption)",
        TONES[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}
