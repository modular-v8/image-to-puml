import type { Info } from "@/api";
import { ModelBadge } from "@/components/ModelBadge";

export function Header({ info }: { info: Info | null }) {
  return (
    <header className="shrink-0 border-b border-bone">
      <div className="mx-auto flex h-(--spacing-60) max-w-(--page-max-width) items-center justify-between px-(--spacing-16) md:px-(--spacing-32)">
        <span className="text-body-sm font-semibold">uml-regen</span>
        <ModelBadge info={info} />
      </div>
    </header>
  );
}
