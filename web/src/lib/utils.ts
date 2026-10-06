import { clsx, type ClassValue } from "clsx";
import { extendTailwindMerge } from "tailwind-merge";

// Tilda's type steps (theme.css `--text-*`). Without this, tailwind-merge
// reads `text-caption` as a colour and drops it next to `text-ink-black`.
const TYPE_STEPS = ["caption", "body-sm", "subheading", "heading-sm", "heading", "heading-lg", "display"];

const twMerge = extendTailwindMerge({
  extend: { classGroups: { "font-size": [{ text: TYPE_STEPS }] } },
});

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
