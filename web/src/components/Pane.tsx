import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

type PaneProps = {
  title: string;
  actions?: ReactNode;
  className?: string;
  bodyClassName?: string;
  children: ReactNode;
};

// Feature Card: square, flat bone surface, hairline under the title.
export function Pane({ title, actions, className, bodyClassName, children }: PaneProps) {
  return (
    <section
      className={cn("flex min-w-0 flex-col gap-(--spacing-12) rounded-(--radius-cards) bg-bone p-(--spacing-16) lg:min-h-0", className)}
    >
      <h2 className="text-body-sm font-medium">{title}</h2>
      <hr className="border-t border-silver" />
      <div className={cn("flex min-h-0 flex-1 flex-col gap-(--spacing-12) overflow-auto", bodyClassName)}>{children}</div>
      {actions ? <div className="flex shrink-0 flex-wrap gap-(--spacing-8)">{actions}</div> : null}
    </section>
  );
}
