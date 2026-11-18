import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

/**
 * docs/DESIGN.md "Empty state": one icon in an accent-soft well, one sentence, at most
 * one action. `title` is an optional short lead-in above the sentence.
 */
export function EmptyState({
  icon: Icon,
  title,
  children,
  action,
  className,
}: {
  icon: LucideIcon;
  title?: ReactNode;
  children: ReactNode;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "surface-card flex flex-col items-start gap-4 rounded-xl p-6 sm:flex-row sm:items-center",
        className,
      )}
    >
      <span
        aria-hidden
        className="bg-accent-soft text-link flex size-11 shrink-0 items-center justify-center rounded-lg"
      >
        <Icon className="size-5" />
      </span>
      <div className="grid min-w-0 flex-1 gap-1">
        {title && <p className="type-h3">{title}</p>}
        <p className="text-muted text-sm">{children}</p>
      </div>
      {action && <div className="shrink-0">{action}</div>}
    </div>
  );
}
