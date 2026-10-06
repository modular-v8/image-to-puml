import type { Info } from "@/api";
import { Pill } from "@/components/Pill";

export function ModelBadge({ info }: { info: Info | null }) {
  if (!info) return null;

  return (
    <div className="flex items-center gap-(--spacing-8)">
      <Pill>{info.model_id}</Pill>
      <Pill tone="ink">{info.is_free ? "free" : "paid"}</Pill>
    </div>
  );
}
