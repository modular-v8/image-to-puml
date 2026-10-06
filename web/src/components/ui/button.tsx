import { cva, type VariantProps } from "class-variance-authority";
import * as React from "react";

import { cn } from "@/lib/utils";

// `cta` (coral) is for Regenerate only; see web/design/README.md.
const button = cva(
  "inline-flex items-center justify-center rounded-(--radius-buttons) px-(--spacing-20) py-(--spacing-8) text-body-sm font-medium transition-colors disabled:cursor-not-allowed disabled:border-silver disabled:bg-silver disabled:text-smoke",
  {
    variants: {
      variant: {
        cta: "bg-coral-signal text-paper-white hover:opacity-90",
        ghost: "border border-ink-black bg-paper-white text-ink-black hover:bg-silver",
        dark: "bg-ink-black text-paper-white hover:bg-plum-ink",
      },
    },
    defaultVariants: { variant: "ghost" },
  },
);

type ButtonProps = React.ComponentProps<"button"> & VariantProps<typeof button>;

export function Button({ className, variant, ...props }: ButtonProps) {
  return <button className={cn(button({ variant }), className)} {...props} />;
}
