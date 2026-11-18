import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

type Props = {
  title: ReactNode;
  /** Small uppercase label above the title, e.g. the weekday. */
  eyebrow?: ReactNode;
  description?: ReactNode;
  /** Right-hand side: countdown tiles or the page's actions. */
  aside?: ReactNode;
  /** "display" for Today's editorial date; "h1" everywhere else. */
  size?: "display" | "h1";
};

/** docs/DESIGN.md "Page header": eyebrow, title, optional tiles or actions on the right. */
export function PageHeader({ title, eyebrow, description, aside, size = "h1" }: Props) {
  return (
    <header className="mb-10 flex flex-wrap items-end justify-between gap-x-10 gap-y-6">
      <div className="min-w-0">
        {eyebrow && <p className="type-label text-muted mb-3">{eyebrow}</p>}
        <h1 className={cn(size === "display" ? "type-display" : "type-h1", "break-words")}>
          {title}
        </h1>
        {description && <p className="text-muted mt-3 max-w-2xl">{description}</p>}
      </div>
      {aside && <div className="flex flex-wrap gap-3">{aside}</div>}
    </header>
  );
}
