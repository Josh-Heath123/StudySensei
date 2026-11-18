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
 * docs/DESIGN.md "Segmented progress": focus segments on a soft violet track, breaks on
 * the subtle track, the elapsed part filled with the signature gradient, labels underneath.
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
              "relative h-2 overflow-hidden rounded-full",
              segment.kind === "focus" ? "bg-accent-soft" : "bg-subtle",
            )}
          >
            <div
              className="ease-soft absolute inset-y-0 left-0 bg-[image:var(--gradient)] bg-[length:100cqw_100%] transition-[width] duration-200"
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
