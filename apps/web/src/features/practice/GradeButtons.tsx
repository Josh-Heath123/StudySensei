import { cn } from "@/lib/utils";

import type { Preview } from "./api";
import { GRADES, type Grade } from "./practiceText";

/**
 * Again, Hard, Good and Easy, each with the interval it would schedule (GET /preview) and
 * its key (1-4). A suggested grade (from the AI's marking or the tick list) is outlined and
 * named, never pressed for the student: they always choose.
 */
export function GradeButtons({
  preview,
  suggested,
  suggestedBy,
  disabled,
  onGrade,
}: {
  preview: Preview | undefined;
  suggested?: Grade | null;
  /** Who suggests it: "the AI" or "your ticks". */
  suggestedBy?: string;
  disabled?: boolean;
  onGrade: (grade: Grade) => void;
}) {
  return (
    <div role="group" aria-label="How well did you know it?" className="grid gap-2">
      <p className="type-label text-muted">How well did you know it?</p>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        {GRADES.map(({ grade, label }) => {
          const interval = preview?.options.find((o) => o.grade === grade)?.interval;
          const isSuggested = suggested === grade;
          const name = [
            label,
            interval && `next in ${interval}`,
            isSuggested && `suggested by ${suggestedBy ?? "the marking"}`,
          ]
            .filter(Boolean)
            .join(", ");
          return (
            <button
              key={grade}
              type="button"
              disabled={disabled}
              onClick={() => onGrade(grade)}
              aria-label={name}
              aria-keyshortcuts={String(grade)}
              className={cn(
                "border-line-strong bg-surface hover:bg-subtle focus-visible:outline-ring relative grid min-h-16 cursor-pointer content-center justify-items-center gap-0.5 rounded-md border px-2 py-2 text-center transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 disabled:pointer-events-none disabled:opacity-45",
                isSuggested && "border-primary bg-accent-soft ring-primary ring-2",
              )}
            >
              <span className="text-base font-semibold">{label}</span>
              <span className="text-muted text-xs tabular-nums">
                {interval ?? "…"} <kbd className="text-muted ml-1 font-sans">{grade}</kbd>
              </span>
              {isSuggested && (
                <span className="text-link text-[11px] font-semibold uppercase">Suggested</span>
              )}
            </button>
          );
        })}
      </div>
    </div>
  );
}
