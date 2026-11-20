import { Check } from "lucide-react";
import type { CSSProperties, ComponentProps } from "react";

import { cn } from "@/lib/utils";

import type { PlanBlock } from "./api";
import { blockLabel, blockTitle, isNow, measuredText, METHOD_LABELS } from "./planText";
import { clock, zoned } from "./week";

type Props = Omit<ComponentProps<"button">, "children"> & {
  block: PlanBlock;
  timeZone: string;
  now: number;
  /** Tight layout for short grid cards. */
  compact?: boolean;
  /** Only the start time (narrow grid columns: the card's height shows its length). */
  startOnly?: boolean;
  style?: CSSProperties;
};

/**
 * docs/DESIGN.md "Plan block card": a solid card with the module colour as its left edge, and
 * two rows: the topic (or "Final review · …"), then the time with the method, or the status
 * in its place: done shows a check and the measured minutes; skipped is muted and struck
 * through; missed is muted and labelled; a block happening now says "Now". It's a button: it
 * opens the block's details.
 */
export function PlanBlockCard({
  block,
  timeZone,
  now,
  compact = false,
  startOnly = false,
  className,
  style,
  ...props
}: Props) {
  const start = zoned(block.start, timeZone);
  const end = zoned(block.end, timeZone);
  const measured = measuredText(block);
  const quiet = block.status === "skipped" || block.status === "missed";
  const live = isNow(block, now);
  const title = blockTitle(block);
  return (
    <button
      type="button"
      data-block-id={block.id}
      data-status={live ? "now" : block.status}
      className={cn(
        "bg-surface border-line text-fg focus-visible:outline-ring flex w-full min-w-0 cursor-pointer flex-col items-start justify-start gap-0.5 overflow-hidden rounded-md border border-l-4 px-2.5 py-1.5 text-left shadow-sm transition-[box-shadow,opacity] hover:shadow-md focus-visible:outline-2 focus-visible:outline-offset-2",
        quiet && "text-muted opacity-75 shadow-none",
        live && "ring-ring ring-2",
        className,
      )}
      style={{ borderLeftColor: block.module_colour, ...style }}
      aria-label={blockLabel(block, timeZone, now)}
      {...props}
    >
      <span
        className={cn(
          "w-full truncate text-[13px] leading-tight font-semibold",
          block.status === "skipped" && "line-through",
        )}
      >
        {title}
      </span>
      <span className="text-muted flex w-full min-w-0 items-center gap-1 text-xs whitespace-nowrap tabular-nums">
        <span>
          {clock(start.minutes)}
          {!startOnly && <>–{clock(end.minutes)}</>}
        </span>
        {live ? (
          <span className="text-link font-semibold">· Now</span>
        ) : block.status === "done" ? (
          <span className="text-success flex min-w-0 items-center gap-0.5 font-semibold">
            <Check className="size-3.5 shrink-0" aria-hidden />
            <span className="truncate">{measured ?? "Done"}</span>
          </span>
        ) : block.status === "missed" ? (
          <span className="font-semibold">· Missed</span>
        ) : block.status === "skipped" ? (
          <span className="font-semibold">· Skipped</span>
        ) : (
          !compact && <span className="truncate">· {METHOD_LABELS[block.method]}</span>
        )}
      </span>
    </button>
  );
}
