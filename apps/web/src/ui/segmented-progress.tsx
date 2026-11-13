import type * as React from "react";

import { cn } from "@/lib/utils";

type Segment = {
  kind: "focus" | "break";
  label: string;
  /** Its share of the bar. */
  minutes: number;
  /** How much of it has passed, 0–1. */
  filled: number;
};

/**
 * docs/DESIGN.md "Segmented progress": focus segments `ink`, breaks `line`, the
 * elapsed part filled with the module colour, labels underneath.
 */
function SegmentedProgress({
  segments,
  className,
  ...props
}: React.ComponentProps<"div"> & { segments: readonly Segment[] }) {
  return (
    <div data-slot="segmented-progress" className={cn("grid gap-2", className)} {...props}>
      <div className="flex gap-1" aria-hidden>
        {segments.map((segment, i) => (
          <div
            key={i}
            style={{ flexGrow: segment.minutes, flexBasis: 0 }}
            className={cn(
              "relative h-3 overflow-hidden rounded-md",
              segment.kind === "focus" ? "bg-ink" : "bg-line",
            )}
          >
            <div
              className="absolute inset-y-0 left-0 bg-[var(--module)] transition-[width] duration-150 ease-out"
              style={{ width: `${Math.round(segment.filled * 1000) / 10}%` }}
            />
          </div>
        ))}
      </div>
      <ol className="text-muted flex gap-1 text-xs">
        {segments.map((segment, i) => (
          <li key={i} style={{ flexGrow: segment.minutes, flexBasis: 0 }}>
            {segment.label}
            <span className="sr-only">: {Math.round(segment.filled * 100)}% done</span>
          </li>
        ))}
      </ol>
    </div>
  );
}

export { SegmentedProgress };
